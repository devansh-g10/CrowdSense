# Phase 4 GTFS journey planning

Completed 20 November 2026. The planner joins existing scheduled trip events, ordered route patterns, stops, routes and service calendars through the existing DuckDB service. It supports direct buses and at most one transfer at the exact same stop ID. No route, stop event, departure, arrival observation or prediction is fabricated. This document records the Phase 4 timetable engine; [Phase 5 crowding and ranking](crowding-ranking.md) now enriches its actual journeys through the API. There is no frontend.

## Endpoint and parameters

```text
GET /api/journeys?source_stop_id=8394&destination_stop_id=10081&travel_date=2026-11-20&departure_time=06:09&max_wait_minutes=30&limit=3
```

These source/destination IDs were discovered in the actual export. Swagger at `/docs` includes the validated request and response schema. The app version is 0.4.0 with 14 API paths.

| Parameter | Meaning and bounds |
| --- | --- |
| source_stop_id | Required exported stop ID, as a string |
| destination_stop_id | Required different exported stop ID |
| travel_date | Civil date in Asia/Kolkata, YYYY-MM-DD; accepted years 1900–2100, then checked against actual calendar coverage |
| departure_time | Civil IST HH:MM or HH:MM:SS, from 00:00:00 through 23:59:59; no UTC offset or fractional seconds |
| max_wait_minutes | Initial wait and transfer wait are each bounded separately; default 30, range 0–120 |
| min_transfer_minutes | Same-stop transfer buffer, default 2, range 1–30; a planning assumption, not an exported transfer rule |
| max_journey_minutes | Total request-to-arrival search horizon including all waits; default 360, range 1–720 |
| max_transfers | 0 for direct only, 1 for direct and one-transfer; default 1 |
| limit | Maximum returned journeys; default 10, range 1–20 |

If maximum wait is smaller than the minimum transfer buffer, direct journeys can still be returned; no transfer can satisfy those bounds. A zero maximum wait permits boarding exactly at the request time. Missing stops return 404, invalid requests return 422, and unsupported calendar windows return HTTP 200 with `status: unsupported_date` and no journeys. Underlying dataset failures reuse the backend's sanitized 503 errors.

## Timetable search and ordering

Each request owns one existing database-service connection, inherits its memory/thread/spill limits and participates in the backend's two-request concurrency cap. Fixed SQL and bound values are used throughout. Small temporary tables are scoped to that in-memory connection and discarded on close; original Parquet files are only read. No complete dataset enters pandas or Python lists.

The search identifies active service-day instances, bounds initial source boardings by maximum wait, and bounds destination events by the duration horizon. A direct journey joins the same trip ID and service date with the destination strictly after the boarding sequence. A transfer joins a downstream first-trip occurrence to an upstream occurrence of a destination-reaching second trip at the identical stop ID. It requires a different trip instance and an inclusive transfer-wait interval from the minimum buffer to maximum wait. No walking or nearby-stop transfers are inferred, and transfers back at the source or already at the destination are excluded.

Trip identity includes service date, so a trip ID on two consecutive service days is not mistaken for a single bus instance. Stop identity includes ordered sequence within that trip. A stop ID repeated at two sequences is retained twice, including repeated boarding choices. Returned legs read every actual scheduled intermediate event between their chosen endpoint sequences, enriched by matching pattern/sequence/stop rows. Consecutive segments refer to those exact ordered events. Negative-time legs, missing endpoints or oversized legs are excluded and disclosed. Equal departure times are preserved; the export contains 1,649 such adjacent events and no backwards-time events.

Candidates are sorted by estimated final arrival, then transfer count, initial departure and stable trip/service-date/sequence identifiers. This is earliest arrival among the examined candidates, not an assertion of globally optimal routing when limits are reached.

## Calendars, exceptions and midnight

The actual calendar has one service, ID `1`, enabled on all seven weekdays from 20250101 through 20400101 inclusive. Dates and day flags are stored as strings and explicitly parsed. The calendar period is independent of the October model training/test period. These are supplied static validity bounds, not independently established operating plans for every future date.

The planner looks for `calendar_dates.parquet`, `calendar_dates.txt` or `calendar_dates.csv` in the processed export directory. **None is available in this bundle.** Responses set `exceptions_available: false`, `exceptions_source: null` and warn that holiday additions/removals and cancellations cannot be checked. The optional reader supports the three GTFS fields `service_id`, `date` (YYYYMMDD) and `exception_type` (1 add, 2 remove), with exceptions overriding base weekday service. It rejects multiple sources, invalid rows and conflicting duplicate service/date entries. No addition/removal behavior is claimed to have been exercised against this dataset because it contains no exception records. No exception file was synthesized.

All civil timestamps are timezone-aware Asia/Kolkata values, serialized with +05:30. `tzdata==2026.6` was added because the Windows environment initially had no IANA timezone database. Raw GTFS seconds are never reduced modulo 86400 for trip timing. For example, a departure of 86417 on service date 20 November is 00:00:17 on civil date 21 November. The planner looks back by the actual schedule's spill-day range to include that previous-day service, and it includes later service dates for journeys crossing midnight. Both legs of a connection are checked on their own service dates.

The maximum exported departure is 104,113 seconds (28:55:13), so the last service date can spill into 2 January 2040. Coverage checks use the allowable **initial boarding wait window**, not the entire journey horizon: a request before service starts cannot become supported solely because a distant arrival horizon reaches the calendar. A wait crossing midnight into valid service can be supported. A previous-day 24+ hour trip remains usable at the calendar's end boundary, but not after the final possible spill time. `date_supported` indicates overlap with that declared calendar/time envelope; an individual stop may still have no feasible departure.

## Approximate times and response fields

The schedule export contains **departure_seconds only**, without arrival times, dwell observations or live vehicle positions. Estimated alighting/transfer arrival uses the departure timestamp at that stop as a proxy. Every journey sets `duration_is_approximate: true` and `arrival_time_basis: alighting_stop_departure_proxy`, with warnings. This may conservatively include destination dwell and does not predict traffic or guarantee a connection.

Each journey includes:

- `departure_at` and `estimated_arrival_at` with IST offsets.
- `initial_wait_seconds`: request time to first boarding.
- `transfer_wait_seconds`: first alighting proxy to second boarding, or zero for a direct trip.
- `in_vehicle_duration_seconds`: sum of each leg's alighting-departure minus boarding-departure times.
- `travel_duration_seconds`: departure-to-arrival elapsed time, including transfer wait.
- `total_duration_seconds`: request-to-arrival elapsed time, including initial wait.
- `legs`, each with real route/pattern/trip/service/date identity, boarding/alighting sequence, full ordered `stops`, `intermediate_stops`, and consecutive `segments` with approximate duration.

Leg stops retain `gtfs_departure_seconds` and a correctly unrolled `scheduled_departure_at`. Repeated IDs and zero-time adjacent stop events are not collapsed or given invented durations. No journey crowding prediction is generated; the existing crowding API and Insufficient Data classifications are unchanged. Relative historical crowding is not actual occupancy or guaranteed seat availability.

## Bounded search and empty responses

Default per-request candidate limits are:

| Search stage | Maximum examined/retained |
| --- | ---: |
| Initial source boardings | 256 |
| Destination stop events | 2,048 |
| First-leg downstream transfer events | 8,192 |
| Direct candidates | 200 |
| One-transfer candidates | 200 |
| Scheduled stops per reconstructed leg | 512 |
| Returned journeys | 20 (default 10) |

The actual longest exported trip has 183 scheduled stops. Every search stage requests one extra row to detect its limit where applicable. The response's `search` object reports bounds, examined counts, candidate count and truncation. `result_limit_reached` separately reports response limiting. The `status` is `ok` when journeys are returned, `no_journeys` when no feasible option is found within the declared constraints without search truncation, `search_incomplete` when a limit or excluded leg prevents a complete negative result, and `unsupported_date` when the boarding window lies outside calendar coverage. An empty result does not invent a bus or imply an empty/uncrowded bus. Even untruncated results cover only the requested duration, wait and transfer constraints and the available static data.

## Real discovered witnesses and tests

`scripts/discover_journey_cases.py` queries the actual exports and records identifiers in `phase4-journey-cases.json`. Witnesses include:

| Case | Actual schedule evidence |
| --- | --- |
| Direct | 8394 → 10079, trip 1000_FULL_06_10, sequences 0 → 1, 06:10:00 → 06:13:18 |
| Transfer-only pair | 8394 → 10081 has no forward direct pattern; 1000_FULL_06_10 can connect to 3684_FULL_06_15, including a real connection at stop 10080 with a 329-second wait |
| Midnight arrival | 10097 → 5015 on 1001_FULL_22_50, 23:59:39 → next-day 00:00:17 |
| Previous service day | 5015 → 3638 boards the same trip at raw GTFS 86417 seconds, using the preceding service date |
| Transfer across service dates | 10097 → 1245 can connect via stop 7976 from 1001_FULL_22_50 to next-service-day 585_FULL_00_10 |
| Repeated stop | 1318 → 1321 on 1184_FULL_07_14 retains stop 1320 at sequences 23 and 24, with equal departure times |
| No direct | No forward direct pattern connects 8394 → 1; direct-only search returns no journeys |

Reference travel date is 20 November 2026, inside the supplied calendar. These witnesses are examples from saved schedules, not live operating promises. Alternative equivalent connections may appear earlier in the sorted output.

The final complete suite passed **66 tests in 43.494 seconds** of reported unittest runtime: the preserved 47 API/database tests plus 19 journey tests. Journey tests independently compare returned stops and times with actual trip rows and validate calendar flags, endpoint order, leg identities, wait/duration arithmetic, midnight/service-date handling, repeated occurrences, unsupported dates, invalid input and explicit search limits. All source and staged files match the Phase 1 hashes afterward.

The running local server passed eight real-data journey scenarios, two invalid requests and three calendar-window boundary checks over HTTP. Swagger HTML and the updated 14-path OpenAPI document passed. Evidence is in `phase4-journey-verification.json`; durations there are local smoke-check observations, not benchmark claims. `pip check` passed. The existing nonfatal Starlette TestClient HTTPX deprecation notice remains.

Use the current `.venv`, launch Uvicorn as described in README.md, and run `python -m scripts.verify_journeys` for live checks. Reuse discovery evidence unless the underlying inputs change. No export/model modification, retraining, notebook execution, frontend work, publication or GitHub push occurred. Stop after Phase 4.
