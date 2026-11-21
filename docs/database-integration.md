# Phase 2 database integration

Completed 20 November 2026. All checks use the existing exported data. No model file was changed, no training or pipeline cell was run, and no new prediction was produced.

## Configuration and lifetime

`backend/config.py` resolves paths from the project location, not the shell's current directory. `Settings.from_env()` supports:

| Environment variable | Default | Meaning |
| --- | --- | --- |
| CROWDROUTE_DATA_DIR | data/processed | Immutable export directory |
| CROWDROUTE_RUNTIME_DIR | data/runtime | Session spill directory parent |
| CROWDROUTE_MEMORY_LIMIT | 256MB | DuckDB memory limit per session |
| CROWDROUTE_THREADS | 2 | Worker threads per session, 1–32 |
| CROWDROUTE_MAX_TEMP_SIZE | 1GB | Disk spill budget per session |
| CROWDROUTE_MAX_QUERY_ROWS | 1000 | Maximum rows returned by a query, configurable up to 10000 |

Relative overrides are also anchored to the project location. Memory and spill budgets accept positive integer MB or GB values. Runtime files cannot reside inside the export directory. Importing the modules does not open a connection, create runtime folders or load datasets.

Each query owns an in-memory DuckDB connection and a unique temporary spill folder. Schema registration and query results are fully consumed before another statement executes, which is required by DuckDB 2.0. The connection closes and spill files are removed on success or exception. Independent queries can run concurrently without sharing connection state. A future API must cap simultaneous sessions: the configured RAM and disk limits apply per session, not across the entire process. DuckDB's memory limit does not cover every Python or engine allocation.

The connection creates logical views over existing Parquet files; it does not copy datasets into persistent database tables or pandas. The database catalog is writable only in memory and discarded on close. Export access uses read operations. `Database.connection()` is an internal trusted SQL interface; do not expose it as a user-submitted SQL endpoint. It can be used for a batch of internal queries that should share one session. All public query methods use fixed SQL with bound values, validate pagination, and return eagerly materialized, bounded lists of dictionaries.

## Queries

```python
from backend.database import Database, CROWDING_NOTICE

db = Database()
stops = db.stops(search='Rohini', limit=20)
routes = db.routes(stop_id=stops[0]['stop_id'], limit=20) if stops else []

# These route/pattern/time identifiers were observed in the actual exports.
patterns = db.route_patterns('1002')
ordered_stops = db.pattern_stops('1002', 9)
departures = db.trip_schedule('1002', pattern_id=9, after_seconds=18 * 3600)
profiles = db.crowding_predictions('1002', 9, False, 34)
analytics = db.analytics('1002', is_weekend=False, time_slot=34)
print(CROWDING_NOTICE)
```

- GTFS route/stop/trip identifiers remain strings. Pattern IDs and stop sequences are integers.
- Searches use literal, case-insensitive substrings; `%` and `_` do not become wildcard operators. Values are SQL parameters.
- Queries default to 100 rows and accept `limit` and `offset`. If configuring a maximum below 100, pass a limit within that maximum explicitly. Sorting is deterministic for stable pagination.
- `routes` can filter by stop using an existence check, which avoids repeating routes across patterns.
- `route_patterns` gives pattern IDs, stop counts and sequence ranges. `pattern_stops` retains pattern identity and original sequence ordering.
- `trip_schedule` requires a route and optionally filters pattern, stop, trip and inclusive departure-second bounds. The result consists of scheduled stop events, not complete journeys. Seconds above 86400 are retained. This phase does not select an active service date or implement GTFS calendar exceptions.
- `crowding_predictions` requires route, pattern, weekday/weekend flag and a slot from 0 to 47; optional segment filters include sequence and both endpoint stop IDs. It returns the exported fields and label unchanged. No match returns an empty list. Hourly fallback is already present in the export; the database does not compute another fallback.
- `analytics` returns existing route/day-type/time-slot aggregates, including insufficient-data counts, without dropping profiles.

Slot indexing is local Asia/Kolkata, with two slots per hour; the caller supplies the day type and slot. The database does not silently convert timestamps. `Insufficient Data` rows can contain numeric loads. Those numbers do not make the classification reliable and must not be presented as occupancy or seat availability. Relative historical crowding is not actual bus occupancy or guaranteed seat availability.

## Schema and relationship findings

All eight actual Parquet schemas were read through DuckDB. Their ordered names and physical types are validated whenever the views are registered. Unexpected schema changes and missing exports fail explicitly. The complete schemas, row counts, null counts and hashes are recorded in `phase2-database-verification.json`.

| View | Rows | Verified unique key |
| --- | ---: | --- |
| calendar | 1 | service_id |
| stops | 6,862 | stop_id |
| routes | 2,574 | route_id |
| route_lookup | 1,980 | ticket_route |
| route_stop_sequence | 109,660 | pattern_id, stop_sequence |
| trip_schedule | 2,737,136 | trip_id, stop_sequence |
| crowding_model | 1,063,956 | route_id, pattern_id, stop_sequence, from_stop_id, to_stop_id, is_weekend, time_slot |
| route_analytics | 50,318 | route_id, is_weekend, time_slot |

All row counts and schemas match Phase 1. No duplicate key rows were found. Pattern IDs each belong to one route; trip IDs each belong to one route, pattern and service. The following anti-join checks found zero unmatched rows:

- Pattern routes and stops exist in routes and stops; lookup routes exist in routes.
- Scheduled routes, stops and services exist; each scheduled pattern/sequence/stop matches the route pattern.
- Model routes and both segment endpoints exist. Every model segment matches consecutive stops in its ordered pattern, using `lead(stop_id)` to verify the destination.
- Analytics routes exist. Analytics groups and model groups match in both directions.

For every analytics group, total segment profiles and counts of Low, Moderate, High and Insufficient Data agree exactly with the exported crowding model. These are checks over all rows, not samples. They do not establish vehicle capacity, live operating conditions, schedule timing monotonicity, or every possible future journey-planning invariant.

## Missing values and ranges

The only null field is `crowding_model.baseline_prediction`, with 381,153 nulls. Baseline prediction is optional in the exported hierarchy and is not imputed. There are no nulls in any other field and no empty or whitespace-only strings in any view. No invalid coordinate ranges or nonfinite stop coordinates were found.

Final model predictions have no negative or nonfinite values. Time slots are all within 0–47; labels are all known. Supported classifications meet the available sample/day/reference-sample minima. The export lacks reference-day counts, so this audit cannot independently recheck that part of the notebook's classification rule.

Preserved counts are Low 571, Moderate 159,982, High 8,747 and Insufficient Data 894,656. Schedules range from 0 to 104,113 seconds, with 18,457 events at or after 86400 seconds and no negative times. Calendar dates and day flags remain VARCHAR, as in the source. There is no calendar exception export.

## Validation

Run from the project root with the existing local environment:

```powershell
& ./.venv/Scripts/python.exe -m unittest discover -s tests -v
# To regenerate the audit when needed:
& ./.venv/Scripts/python.exe -m scripts.inspect_database
```

All 19 integration tests passed. Tests verify schemas/counts, keys/relationships, explicit null handling, labels, actual query results, searches, filters, ordering/pagination, missing results, invalid inputs, after-midnight events, portable paths, memory settings, missing-file failures, cleanup after errors and concurrent queries. Samples are selected from the actual exports, not fabricated. Original and processed assets are checked against all 13 Phase 1 hashes, including a post-test check.

There is no API, routing engine or frontend implementation in Phase 2. Further phases require a new instruction.
