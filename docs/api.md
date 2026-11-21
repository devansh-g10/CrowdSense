# FastAPI backend — Phases 3–9

Completed and locally verified on 20 November 2026. `backend/main.py` exposes `app` and `create_app(settings)`; modular routers are under `backend/api/`. Response models are in `backend/schemas.py`. Existing Parquet data comes through the completed DuckDB layer, with additive segment/aggregate queries. `backend/exports.py` reads only the named, small JSON/CSV exports and validates their actual fields. No notebook, training or evaluation code executes.

Phase 4 added `GET /api/journeys`, implemented through `backend/journey_planner.py` with contracts in `backend/journey_schemas.py`. Phase 5 adds historical segment evidence and Fastest/Comfortable/Balanced recommendations through `backend/journey_ranking.py`. Phase 9 adds a High-profile segment endpoint and optional route search and day/slot aggregation. The API has 15 documented paths. See [journey planning](journey-planning.md) for calendar/timing semantics and [crowding/ranking](crowding-ranking.md) for preference, coverage and recommendation contracts. Earlier Phase 3 verification results below remain historical evidence for its original 13 endpoints.

## Start and verify

Run from `D:/CrowdSense/CrowdSense`, or the relocated project root:

```powershell
& ./.venv/Scripts/python.exe -m pip install -r requirements.txt
& ./.venv/Scripts/python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In another shell:

```powershell
& ./.venv/Scripts/python.exe -m unittest discover -s tests -v
& ./.venv/Scripts/python.exe -m scripts.verify_api
```

Swagger is at `http://127.0.0.1:8000/docs`; the source schema is at `/openapi.json` and ReDoc is at `/redoc`. Swagger's default UI JavaScript/CSS comes from a CDN; the local HTML and complete OpenAPI response were verified, but no offline UI bundle is included. No external hosting or publication was performed.

## Endpoints

All application endpoints use the `/api` prefix and GET. All data is historical or from the supplied static GTFS export.

| Path | Parameters | Response |
| --- | --- | --- |
| /api/health | None | Readiness of all eight Parquet schemas and five JSON/CSV files; 503 on failure |
| /api/model-info | None | Original metadata, periods, support minima, limitations and crowding notice |
| /api/stops | search, stop_id, limit, offset | Paged stop IDs, names and coordinates |
| /api/routes | search, route_id, stop_id, limit, offset | Paged GTFS route definitions |
| /api/routes/{route_id} | limit, offset | Route definition and a paged list of its patterns |
| /api/routes/{route_id}/segments | pattern_id, limit, offset | Paged consecutive pattern stops and endpoint coordinates |
| /api/crowding | Required: route_id, pattern_id, is_weekend, time_slot. Optional: stop_sequence, from_stop_id, to_stop_id, limit, offset | Paged existing segment predictions and explicit availability |
| /api/analytics/overview | None | Global stop/route/pattern/trip/profile counts and all classification counts |
| /api/analytics/routes | search (literal route name or ID), route_id, is_weekend, time_slot, limit, offset | Per-route sums of profile counts by classification |
| /api/analytics/heatmap | aggregate_slots, route_id, is_weekend, time_slot, limit, offset | Exported route cells by default. With aggregate_slots=true, sums profiles, High counts and Insufficient Data counts by day type and slot before pagination. Absent groups have no row. |
| /api/analytics/high-segments | route_id, is_weekend, time_slot, limit, offset | High historical segment profiles with stop names and sample support, ordered by descending sample journeys. |
| /api/analytics/weekly | None | All five saved weekly_analysis.csv rows |
| /api/analytics/peak-hours | day_type: Weekday or Weekend | Saved peak_analysis.csv rows, optionally filtered |
| /api/analytics/model-performance | None | Original test_metrics.csv row and model_comparison.csv rows with denominator caveat |
| /api/journeys | source_stop_id, destination_stop_id, travel_date, departure_time; optional wait/transfer/duration/result bounds and preference | Real schedules with estimated timings, exact historical segment matches, explicit coverage, ranking components and unique recommendations |

The route-definition endpoints return dataset route definitions. Their segments are consecutive stops within an exported route pattern; no segment combines different patterns or implies a known road polyline. The journey endpoint assembles actual scheduled trips and feasible same-stop connections, then attaches exact segment/time historical evidence and ranks bounded candidates.

Query examples using identifiers observed in the actual exports:

```text
/api/stops?search=Rohini&limit=20&offset=0
/api/routes?search=871DOWN
/api/routes/1002
/api/routes/1002/segments?pattern_id=9
/api/crowding?route_id=1002&pattern_id=9&is_weekend=false&time_slot=34
/api/analytics/heatmap?route_id=1002&is_weekend=false&time_slot=34
```

IDs remain strings; pattern IDs and sequences remain integers. Time slots are integers 0–47 in Asia/Kolkata, with two slots per hour. `is_weekend` is a validated boolean. The API does not infer a service date or convert request timestamps. Numeric IDs, sequences and offsets must fit a signed 64-bit integer. No date-specific service or GTFS exception logic is implemented here.

## Pagination and unavailable predictions

Paged responses contain `items`, `limit`, `offset`, `returned` and `notice`. `returned` is the number of rows on this page, not the dataset total. Default limit is 100; API limit range is 1–1000 and is additionally bounded by the configured database result limit. Offsets are nonnegative. Each query has a deterministic order. Route detail's pagination applies to its `patterns` list. Literal case-insensitive search treats SQL wildcard and quote characters as ordinary input.

Crowding responses add `status` and `unavailable_reason`. The status describes the returned page: `available` if every profile is supported, `partial` if support is mixed, and `unavailable` if no usable profile is on the page. No matching exported key returns an empty list with `no_matching_exported_profile`; an empty page at a positive offset reports `no_profiles_on_page` instead of claiming the model has no data.

Each crowding item includes the original profile identity, samples, observed days, source, support and classification. `available` is false for `Insufficient Data`. In that case `predicted_load` is null, `unavailable_reason` is `insufficient_data`, and `exported_predicted_load` retains the exact original model value separately. For supported rows, both numeric fields equal the exported prediction. Optional baseline/threshold fields retain their original nulls. No value is replaced with zero, no classification is changed, and no fallback is recomputed. The export already contains the trained hourly fallback.

Relative historical crowding is not actual bus occupancy or guaranteed seat availability. This notice appears on crowding and analytics responses and in model info. Heatmap load fields are recorded historical aggregates, not usable journey predictions; their insufficient-data counts remain visible. Route analytics sums are counts of exported profiles, not observed bus trips or passengers. Performance metrics are the notebook's saved evaluation against reconstructed recorded loads. Their common-observation comparison and broader test evaluation use different denominators.

## Validation, errors and resources

Pydantic validates request bounds and typed response schemas. SQL uses fixed identifiers and bound values, including filter and pagination values. No HTTP input becomes SQL text or an export filename. `GET /api/health` checks view schemas and parses all metadata/report exports; it does not rerun the expensive full Phase 2 audit on every request.

Errors use `{"error": {"code": "...", "message": "..."}}`. Invalid query/path input is 422. Missing route definitions or a pattern belonging to another route are 404. Missing/incompatible files and database errors are 503. Unexpected failures are 500. Full exception details are logged locally and excluded from HTTP responses. No unavailable/error path returns a successful invented data response. CORS preflight failures are middleware-generated 400 responses.

Synchronous handlers run outside the event loop and reuse independently owned DuckDB sessions. Memory defaults remain 256 MB and two threads per database session, with a 1 GB spill budget. Connections and unique spill directories close on exceptions. A per-process nonblocking semaphore limits concurrent data requests to two by default; saturation returns 503 with `Retry-After: 1`. Each request opens at most one database session at a time. Multiple server workers would multiply these resource budgets, so the documented launch uses one local worker.

The existing `CROWDROUTE_DATA_DIR`, `CROWDROUTE_RUNTIME_DIR`, `CROWDROUTE_MEMORY_LIMIT`, `CROWDROUTE_THREADS`, `CROWDROUTE_MAX_TEMP_SIZE` and `CROWDROUTE_MAX_QUERY_ROWS` settings are reused. New settings are:

- `CROWDROUTE_MAX_CONCURRENT_QUERIES`: integer 1–8, default 2.
- `CROWDROUTE_CORS_ORIGINS`: comma-separated explicit local HTTP(S) origins. Defaults allow localhost and 127.0.0.1 on ports 3000 and 5173; an empty override disables cross-origin access. Wildcards, remote hosts, credentials, paths and query strings are rejected. Only GET is allowed cross-origin, with credentials disabled.

Settings read process environment variables; there is no implicit `.env` loader. Paths remain portable and anchored to the project root. No persistent database materialization or complete dataset-to-pandas loading is used.

## Actual verification results

At Phase 3, all 47 unittest tests passed: 28 API integration tests and the 19 preserved database integration tests. Tests use the actual exports and saved reports. Error tests mock failures only, not transit data or metrics. Covered behavior includes its endpoints, saved metric values, route pattern/segment identity, real supported labels, insufficient/missing/mixed predictions, null baselines, pagination/search, numeric bounds, SQL injection strings, local CORS, request capacity, safe failures and Swagger/OpenAPI contracts. At Phase 4, all 66 tests passed, including 19 new journey tests and the preserved suites.

The running Uvicorn server passed 15 HTTP GET checks: all 13 API endpoints plus `/docs` and `/openapi.json`. The OpenAPI document lists exactly the 13 requested API paths. Local OPTIONS preflight also passed. `scripts/verify_api.py` records these results in `phase3-api-verification.json`; recorded durations are individual local smoke checks, not a performance benchmark. Dependency validation with `pip check` passed.

Phase 5 passed all 86 tests, including 20 new real-data crowding/ranking tests and all earlier suites. Fourteen live journey/ranking checks passed, covering all labels, all preferences, unknown comfort, time-slot/weekend changes, real transfers, unsupported dates and invalid preferences. The dedicated Phase 5 report and methodology are linked from README.md.

The installed Starlette TestClient emits an upstream deprecation notice for its HTTPX adapter; tests complete successfully with the pinned HTTPX version. This does not affect the running API. All 13 original and processed file hashes still match the Phase 1 manifest. No model files, notebook or earlier verification reports were changed. No retraining, frontend implementation, Git commit, push or publication occurred.
