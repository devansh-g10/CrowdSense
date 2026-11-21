# CrowdRoute Delhi progress

Updated: 21 November 2026 (Asia/Kolkata).

## Phase 1 — complete

- Inspected the outer workspace and identified the Git project root at `D:/CrowdSense/CrowdSense`.
- Inspected the problem statement, the completed 66-cell Colab notebook and the model metadata without executing the notebook or retraining anything.
- Confirmed with the user that `CrowdRoute_Delhi_Model/` is the already extracted ZIP contents. Reused that existing work rather than extracting again or creating a replacement archive.
- Safely staged all 13 files into `data/processed/` using exclusive creation and SHA-256 equality checks; all original files remain unchanged.
- Verified all 13 exports: eight Parquet files, four CSVs and one JSON metadata file. Every Parquet column decoded successfully; row counts match notebook cell 65's saved output. CSVs and JSON parse successfully.
- Verified 1,063,956 model profiles, no negative predicted loads, no missing crowding classifications and no invalid time slots. Preserved all 894,656 `Insufficient Data` classifications.
- Created `backend/`, `frontend/`, `data/processed/`, `notebooks/`, `tests/`, `scripts/` and `docs/`. Application directories intentionally contain only placeholders.
- Created permanent rules in `AGENTS.md`, project documentation in `README.md`, inspection findings in `docs/model-inspection.md`, and the generated verification manifest in `docs/phase1-verification.json`.
- Added `.gitignore` protections for original/staged exports, archives, notebook outputs, local environments, credentials, databases and build artifacts. No commit, push or publication performed.
- Created a local Python 3.12 environment with DuckDB 2.0.0 and pinned the Phase 1 dependency in `scripts/requirements-phase1.txt`.

## Validation and practical limits

`./.venv/Scripts/python.exe scripts/prepare_phase1.py` passed after adapting the verifier to DuckDB 2.0's result APIs. It uses a 256 MB DuckDB memory limit and two threads with local disk spill. The existing source folder and the processed folder contain exactly the same 13 named assets with matching hashes. Final structure, ignore rules and whitespace checks passed.

The notebook was inspected as text with saved outputs, not run. Model accuracy, actual occupancy and live schedule validity were not independently established. The original ZIP is unavailable in this workspace; archive CRC verification was unnecessary for the confirmed already extracted source and is not claimed. The optional ZIP import path in the verifier is provided for future use but was not exercised with the original archive.

## Phase 1 stop point (historical)

Phase 1 is finished. No backend endpoints, routing engine, frontend, new predictions, retraining or pipeline reruns were implemented. Do not begin Phase 2 without a new user instruction. Read `AGENTS.md` and reuse this evidence before doing further work.

## Phase 2 — Database Integration — complete

Authorized by the user's explicit Phase 2 instruction on 20 November 2026. Read AGENTS.md and this progress file first. Updated the current scope in AGENTS.md while preserving all permanent rules and completed Phase 1 work.

- Inspected the actual ordered schemas and DuckDB types of all eight Parquet exports; verified them against Phase 1.
- Added portable `backend/config.py` settings with project-relative default paths and environment overrides, independent of the process working directory.
- Added `backend/database.py`: isolated in-memory sessions, connection cleanup on all exit paths, unique spill directories, 256 MB default memory limit, two threads, 1 GB spill budget, and reusable validated views for all eight exports. No complete dataset is loaded into pandas or persistent database tables.
- Added bounded, parameterized query methods for stops, routes, route patterns, ordered pattern stops, trip schedules, exported crowding predictions and route analytics. Missing keys return empty results. Original classification and numeric/null fields are returned unchanged.
- Added `backend/requirements.txt`, pinned to the already installed DuckDB 2.0.0. No new dependency downloads were required.
- Added `scripts/inspect_database.py` and generated `docs/phase2-database-verification.json`, containing actual schemas, counts, hashes, missing/blank values, key checks and relationship checks.
- Added `tests/test_database.py` with 19 integration tests using the actual exported files. Ran `./.venv/Scripts/python.exe -m unittest discover -s tests -v`: **19 tests passed** in 8.050 seconds of reported unittest runtime.
- Added usage and findings in `docs/database-integration.md` and updated README.md for the current implemented state.

### Actual data-quality results

All eight row counts match Phase 1: calendar 1; stops 6,862; routes 2,574; route lookup 1,980; route stop sequence 109,660; trip schedule 2,737,136; crowding model 1,063,956; route analytics 50,318.

There are zero duplicate key rows across all eight verified keys and zero failures in 17 relationship/consistency checks. This includes route/stop/service references, exact scheduled pattern stops, consecutive crowding segment endpoints, one route per pattern, one pattern/service per trip, matching analytics/model groups and their classification counts.

The only nulls are 381,153 `baseline_prediction` values in the crowding model; they remain null. There are no other null fields or blank strings. No negative/nonfinite final predicted loads, invalid slots, unknown labels, violations of available classification minima or invalid stop coordinate ranges were found. Reference-day counts are absent from the export, so that threshold remains supported by notebook evidence rather than independently checked here.

Schedules contain 18,457 stop events at or after 24:00, with values from 0 to 104,113 seconds; queries preserve them. No negative departure times were found. All 894,656 `Insufficient Data` classifications are unchanged. Relative historical crowding remains distinct from actual occupancy or guaranteed seat availability.

All 13 original and processed export hashes match the Phase 1 manifest, including checks after the integration tests. Tests also passed for cleanup after exceptions, independently owned concurrent sessions, portable paths, pagination and input validation. No model, original metadata, notebook or Phase 1 report was modified. No commit, push or publication was performed.

## Phase 2 stop point (historical)

Phase 2 is finished. No API endpoints, journey planner or frontend were implemented. No model training, notebook execution, new predictions, source-data corrections or pipeline reruns occurred. Per-session resource budgets are implemented; a future API must additionally limit concurrent sessions. Stop here until the user authorizes the next phase.

## Phase 3 — FastAPI Backend — complete

Authorized by the user's explicit Phase 3 instruction on 20 November 2026. Read AGENTS.md and this progress file first. Reused the completed DuckDB integration and preserved permanent rules and earlier work.

- Added `backend/main.py` with an application factory, OpenAPI/Swagger documentation, consistent JSON error handling and explicit local CORS settings.
- Added modular system, transit and analytics routers under `backend/api/`, shared validated pagination and a nonblocking per-process request-capacity limit. Default maximum concurrent data requests is two, preserving the database's per-session RAM/thread/spill limits.
- Implemented all 13 requested GET endpoints: health, model-info, stops, routes, route detail, route segments, crowding, analytics overview, route analytics, heatmap, weekly, peak-hours and model-performance.
- Added Pydantic request/response contracts in `backend/schemas.py`, grounded in the real exported schemas. SQL values remain parameterized. Additive database methods provide consecutive pattern segments and aggregate/count queries; Phase 2 queries remain intact.
- Added validated reads of the five small metadata/CSV files in `backend/exports.py`. The API returns saved metrics and metadata without running evaluation or creating predictions.
- Explicitly represents unavailable crowding predictions with null and a reason. Preserves the original numeric value as `exported_predicted_load`, all original support fields/nulls and `Insufficient Data` labels. Missing keys return no invented profiles; mixed-support pages report partial availability.
- Added root `requirements.txt` and updated backend requirements. Installed FastAPI 0.165.0, Pydantic 2.14.4, Uvicorn 0.54.0 and HTTPX 0.28.1 into the existing local environment. DuckDB remains 2.0.0. `pip check` reports no broken requirements.
- Added 28 automated API integration tests in `tests/test_api.py`. The full suite, including all 19 Phase 2 database tests, passed: **47 tests in 13.980 seconds** of reported unittest runtime.
- Started Uvicorn locally at `http://127.0.0.1:8000` (verification process PID 12036). Verified all 13 endpoints over live HTTP using actual dataset keys, plus Swagger HTML and the 13-path OpenAPI document. The local CORS preflight passed. The local server was left running for review.
- Added `scripts/verify_api.py`, generated `docs/phase3-api-verification.json`, documented API contracts in `docs/api.md`, and updated README.md with launch/test commands.

### Validation and limits

Tests cover real response values and all supported crowding labels; insufficient, missing and mixed predictions; saved weekly/peak/performance reports; route patterns and consecutive stop segments; global/classification counts; search/pagination; malformed queries and oversized numeric input; SQL injection strings; local CORS; request saturation/release; missing or malformed data; sanitized 503/500 errors; and Swagger/OpenAPI schema coverage. Error tests mock exceptions only, not route/prediction data. The upstream Starlette TestClient emits an HTTPX adapter deprecation notice; all tests pass with the pinned versions.

All 13 original and processed model asset hashes still match the Phase 1 manifest after tests and live checks. No original exports, metadata, notebook, or earlier verification report were modified. Connections and spill directories were cleaned after requests. Swagger HTML and OpenAPI JSON were verified; interactive UI assets use FastAPI's default CDN and no offline UI bundle is included. Recorded HTTP durations are smoke-test observations, not performance claims.

## Phase 3 stop point (historical)

Phase 3 is complete. The local FastAPI data backend is ready for review at `/docs`. No journey routing or frontend was implemented. No model training, notebook execution, new fallback predictions, fabricated metrics, data publication, Git commit or GitHub push occurred. Stop here until the user authorizes the next phase.

## Phase 4 — GTFS Journey Planning Engine — complete

Authorized by the user's explicit Phase 4 instruction on 20 November 2026. Read AGENTS.md and this progress file first and updated the current scope while preserving permanent rules and earlier work.

- Added `backend/journey_planner.py` using the existing DuckDB database service and `backend/journey_schemas.py` for typed, explicit schedule-based results.
- Added `GET /api/journeys` through a modular router. Supports real source/destination stop IDs, local IST date/time, direct trips, one same-stop transfer, maximum initial/transfer waits, minimum transfer buffer, total duration horizon, departure/estimated arrival times, wait/duration breakdowns, full ordered stops and consecutive journey segments.
- Preserved trip service-date identity and stop-sequence occurrence identity. Repeated stop IDs are retained; source sequence must precede destination sequence. Transfer departures must follow the first leg's arrival proxy by the specified buffer and fall within maximum wait. No walking transfers or physical bus-identity guarantees are inferred.
- Verified the actual schedule has departure times only, 1,649 equal-time adjacent events and zero backwards-time events. Arrival/duration values are explicitly approximate and use alighting-stop departure proxies. No real arrival measurements were invented.
- Read actual service calendar `1`: all weekdays enabled, 1 January 2025–1 January 2040 inclusive. The maximum exported GTFS time is 104,113 seconds; earlier service dates can therefore extend past civil midnight. Correctly handles previous-day 24+ hour boarding and transfer legs on different service dates.
- Checked available calendar exception files: none exported. Responses report that holiday additions/removals and cancellations cannot be checked. Added optional validated GTFS exception-file reading without synthesizing any records. Actual exception addition/removal behavior is not claimed tested against absent data.
- Reports unsupported date/time windows separately from no feasible journey. Coverage uses the maximum initial wait window, including waits into the first service day and the final service day's spill cutoff, rather than treating a long arrival horizon as boarding coverage.
- Bounds searches to 256 initial boardings, 2,048 destination events, 8,192 first-leg transfer events, 200 candidates per kind, 512 stops per leg and at most 20 returned journeys. The export's longest trip has 183 stops. Responses disclose truncation and return `search_incomplete` for incomplete negative searches.
- Added and ran `scripts/discover_journey_cases.py`, saving actual direct, transfer-only, midnight, previous-day, cross-service-day, repeated-stop and no-direct witnesses in `docs/phase4-journey-cases.json`.
- Added 19 journey integration tests in `tests/test_journeys.py`. The final full suite passed **66 tests in 43.494 seconds**: 19 new tests plus all 47 earlier API/database tests. Updated the API schema regression test to include the new endpoint and made the earlier live API verifier accept additive endpoints.
- Added `tzdata==2026.6` to runtime requirements and installed it in the existing environment because Windows lacked the IANA timezone data required by `ZoneInfo('Asia/Kolkata')`. `pip check` passed.
- Restarted the prior local verification server using its existing managed session and launched the updated app on `http://127.0.0.1:8000` (PID 19820), version 0.4.0, with 14 documented API paths. The updated server is left running for review.
- Added and ran `scripts/verify_journeys.py`: eight actual journey scenarios, two invalid requests and three calendar-window boundaries passed over live HTTP. Updated Swagger HTML and OpenAPI checks passed. Results are in `docs/phase4-journey-verification.json`.
- Added `docs/journey-planning.md` and updated README.md and API documentation. Previous verification reports and model files remain unchanged.

### Actual discovered examples and verification

Direct: 8394 → 10079 on trip `1000_FULL_06_10`, sequences 0 → 1, 06:10:00 → 06:13:18. Transfer-only pair: 8394 → 10081, with a feasible connection from `1000_FULL_06_10` to `3684_FULL_06_15`; a discovered transfer at stop 10080 has a 329-second wait. Midnight: 10097 → 5015 on `1001_FULL_22_50`, 23:59:39 → next-day 00:00:17. Previous-service-date boarding: 5015 → 3638 on the same trip at raw GTFS time 86417. A cross-service-date transfer to `585_FULL_00_10` reaches stop 1245. Repeated-stop witness `1184_FULL_07_14` retains stop 1320 at sequences 23 and 24. No direct pattern connects 8394 → 1.

Tests compare returned leg events with actual trip rows, check weekday/date validity, sequence order, repeated boarding occurrences, transfer feasibility, all timing arithmetic, date boundaries, typed API responses, unknown stops, invalid times and truncation disclosure. All 13 original and processed export hashes still match Phase 1 after tests and live checks, and planning spill directories are cleaned. No complete dataset was loaded into pandas or persisted as a replacement database. The existing upstream TestClient HTTPX deprecation notice remains nonfatal.

## Phase 4 stop point (historical)

Phase 4 is complete. Direct and one-transfer static GTFS planning is available through `/api/journeys` and `/docs`. Journey estimates are approximate; holiday exceptions, walking transfers, live operation and physical vehicle continuity cannot be established from these exports. No crowding-based journey ranking or frontend was implemented. No fake routes/journeys, model changes, retraining, notebook execution, data publication, Git commit or GitHub push occurred. Stop here until the user authorizes the next phase.

## Phase 5 — Crowding Integration and Journey Ranking — complete

Authorized by the user's explicit Phase 5 instruction on 20 November 2026. Read AGENTS.md and this progress file first. Updated only the active scope while preserving permanent rules and earlier phase evidence.

- Added `backend/journey_crowding.py` to batch-join actual journey segments to `crowding_model.parquet` on route ID, pattern ID, from-stop sequence, both endpoint IDs, local civil weekday/weekend and the actual segment departure's 30-minute slot. Preserved service-date and repeated-stop semantics from the completed planner.
- Added typed segment evidence, coverage/support summaries and explicit policy/score schemas in `backend/crowding_schemas.py`; extended the existing journey API contracts. All four model labels remain supported and unchanged. Missing keys are explicit no-profile Insufficient Data, never Low or zero predictions. Original numeric estimates remain separately visible; usable predictions are null without reliable classification.
- Separated numeric prediction coverage from reliable classification coverage, in both segment-count and approximate in-vehicle-duration forms. Raw data support counts/durations distinguish High, Medium, Low and Missing. Medium-support Insufficient Data remains unreliable; no class is upgraded.
- Added duration-weighted relative scoring of reliable labels (Low 0, Moderate 0.5, High 1) and a separately exposed unknown-penalized score using 1.25 for unsupported/missing duration. These are ordinal product policy values, not occupancy fractions or validated model metrics. Waits are excluded from crowding duration; zero-duration repeated-stop events keep their counts without invented time weights.
- Added `backend/journey_ranking.py` orchestration and `preference=fastest|comfortable|balanced` to `GET /api/journeys`, defaulting to Balanced. Fastest minimizes total request-to-arrival time. Comfortable requires positive in-vehicle duration and at least 0.8 reliable coverage by both count and duration. Balanced cost is total duration minutes + 30 × unknown-penalized relative crowding + 5 × transfers. Returned policy and per-journey components make the choices explicit.
- The orchestration service requests at most 80 real planner candidates before applying the public result limit, preserving existing timetable-stage caps and ordinary raw-planner behavior. Responses report ranking pool limits, examined count and truncation. Exact duplicates are removed; shared preference winners merge into one recommendation. Full winning journeys remain inspectable even when outside the limited main candidate list.
- If no reliable comfort option is found, returns `insufficient_reliable_coverage` with an explanation. A requested unavailable comfort preference sets `preference_available: false` and `applied_preference: null`; feasible alternatives are not mislabeled as comfortable. No fake alternative, fallback model prediction, occupancy percentage or seat guarantee is generated.
- Added and ran `scripts/discover_crowding_cases.py`, saving actual schedule-aligned Low, Moderate, High, Insufficient Data and Medium-support Insufficient Data witnesses plus a real slot-crossing trip in `docs/phase5-crowding-cases.json`. Input hashes permit reuse of unchanged discovery evidence. Existing Phase 4 midnight, transfer and repeated-stop cases are reused.
- Added 20 real-data integration tests in `tests/test_journey_crowding.py`. The final complete suite passed **86 tests in 71.044 seconds** of reported unittest runtime: all 66 earlier tests plus the 20 new tests. No transit/model data was mocked or synthesized. A ranking-pool test changes only the policy limit, not data.
- Restarted the prior managed local server and launched app version 0.5.0 at `http://127.0.0.1:8000` (PID 25492), with the same 14 API paths and updated Swagger. It is left running for review. No dependency changes were needed.
- Added and ran `scripts/verify_crowding_ranking.py`: **14 live HTTP journey/ranking checks passed**, covering all classifications, all three preferences, explicit unavailable comfort, midnight weekday changes, per-segment slots, real transfers, unsupported dates and invalid preferences. Swagger HTML and updated OpenAPI checks passed. Evidence is in `docs/phase5-ranking-verification.json`.
- Added `docs/crowding-ranking.md` with contracts, equations, eligibility thresholds, penalties, candidate/response bounds and limitations; updated README.md, API documentation and the Phase 4 document's link to the new layer. Earlier verification reports remain untouched; the older journey smoke script accepts the additive app version.

### Actual results and limitations

For real stops 3619 → 3621, departing 20 November 2026 at 08:45:23 with 30-minute maximum wait and direct-only search, 26 unique journeys are examined. Fastest selects `2195_FULL_08_35` with 152 seconds total duration and unknown-penalized score 1.25. Comfortable and Balanced select `1011_FULL_08_50`, with 1,040 seconds total duration, full reliable classification coverage for this one-segment ride and supported Low relative score 0. The same winner carries both labels in one recommendation. These numbers describe the declared query and policy, not occupancy or a live service guarantee.

Tests independently check model matches, support preservation, coverage/weighting arithmetic and score components; verify that every segment uses its actual time rather than initial boarding time; and check that a Friday service continuing into Saturday uses Saturday profiles after midnight. They also verify repeated zero-duration segments, absent-profile penalties, no comfort claim for Medium-support Insufficient Data, stable IDs, duplicate recommendation merging, true minimum time in the bounded pool, preference validation and pool-limit disclosure.

All 13 original and processed exports still match the Phase 1 SHA-256 manifest after tests and live checks. Planning/enrichment spill directories are cleaned; there is no complete-data pandas loading or persistent replacement dataset. The existing upstream TestClient HTTPX deprecation notice remains nonfatal. Relative labels are segment-specific; reference-day counts are absent from the export, and the source classifications are preserved rather than rederived. Earlier calendar-exception, static-schedule and approximate-arrival limitations remain visible. A recommendation is only best under the declared policy among the bounded examined candidates.

## Phase 5 stop point (historical)

Phase 5 is complete. Historical crowding evidence, coverage/support and Fastest/Comfortable/Balanced ranking are available through `/api/journeys` and `/docs`. Unreliable comfort is explicitly unavailable. No frontend, source-model modification, retraining, notebook execution, fake routes/journeys, occupancy/seat guarantee, data publication, Git commit or GitHub push occurred. Stop here until the user authorizes the next phase.

## Phase 6 — Frontend foundation

Completed on 21 November 2026. The React and TypeScript application in `frontend/` uses Vite, Tailwind CSS, React Router and Lucide. Journey Planner, Operator Dashboard, Model Insights and About share responsive navigation, a footer, local fonts and persistent light/dark preferences. Shared controls cover forms, cards, buttons, badges and request feedback.

The typed client queries FastAPI for stop suggestions, journey rankings, network coverage and model metadata. The planner uses Delhi local time and shows backend warnings and unavailable preferences. All displayed transit results come from the existing API. The README documents local startup, API configuration and static hosting requirements.

### Verification

- Installed dependencies and generated the npm lockfile. The strict TypeScript check and Vite production build passed.
- Served the production bundle locally and verified that its proxy reached the FastAPI health endpoint, with database and model files ready.
- Tested in headless Edge at viewport widths of 390, 768 and 1440 pixels. The planner fit each viewport without document-level horizontal overflow. Verified the four pages, direct route loading, network and model data, and theme persistence across page loads.
- Selected C4E Janakpuri and C4H Janakpuri from actual stop suggestions. The planner rendered scheduled journey results for 20 November 2026 at 08:45 IST. An unmatched stop search displayed the empty state. Blocking the network overview request displayed the error state, and Retry loaded the data after connectivity was restored.

## Phase 6 stop point (historical)

Phase 6 completed the frontend foundation and its integration with the Phase 5 backend.

## Phase 7 — Journey Planner Frontend

Completed on 21 November 2026. The planner home searches actual stops, supports swapping selections, validates distinct endpoints and accepts travel date, Delhi departure time and ranking preference. Each search opens a dedicated `/journeys` URL. Edit search restores the endpoints and search settings.

The results page shows alternatives in API order and includes recommendation winners outside the returned candidate list. Shared winners appear once with their preference labels. Each alternative shows the bus routes, dated IST departure and estimated arrival, approximate total time, initial and transfer waits, and transfer count. Expandable legs preserve the backend stop order and repeated stop occurrences.

Historical crowding badges show segment counts for Low (green), Moderate (amber), High (red) and Insufficient Data (gray). Prediction coverage and reliable classification coverage show separate segment counts. Support counts and available segment-level samples, observed days and unavailable reasons come from the API. The page explains the historical basis, unavailable comfort recommendations, and search and timetable limits.

### Verification

- Strict TypeScript checks and the Vite production build passed. Tested the built application in Edge through the local Vite proxy to FastAPI.
- Used actual autocomplete selections for C4E Janakpuri and C4H Janakpuri, swapped them, submitted a search and restored it with Edit search. Selecting the same stop twice produced the validation message.
- Verified the home page and expanded results fit widths of 390, 768 and 1440 pixels without horizontal page overflow.
- Tested all three preference values. The 06:09 search from stop 8394 to 10081 on 20 November returned a transfer journey with two expandable legs. The 03:00 search returned no feasible journey. The 23:59:39 search from 10097 to 5015 displayed the next day's arrival.
- Verified all four badge levels on real alternatives and an unavailable Comfortable recommendation. An unsupported date displayed the API's empty state. Blocking the journey request displayed the error state, and Retry loaded real results after the connection was restored.

## Phase 7 stop point (historical)

Phase 7 completed the planner home and scheduled journey results.

## Phase 8 — Interactive route map

Completed on 21 November 2026. The first journey alternative opens with an interactive map. Each alternative has a map toggle. Leaflet and React Leaflet load with the selected map, and OpenStreetMap supplies the attributed street tiles.

The original and processed exports have no GTFS shape geometry. The map labels its route visualization as approximate and connects each segment's actual stop-sequence endpoints within the same leg. Source, destination, intermediate stops and transfer points have clickable markers. Visits sharing coordinates appear together in a popup with their scheduled stop events and routes. Segment popups show the route, historical crowding class and data support. The four-color legend preserves Insufficient Data. Route geometry fits on opening and resizing, with manual zoom and a Fit route control. A tile failure displays a retry action while the journey overlay stays available.

### Verification

- Strict TypeScript checks and the Vite production build passed. The map JavaScript and styles are loaded as separate assets.
- Tested the production build through the local API in Edge. The direct 3619 → 3621 search and the 8394 → 10081 transfer search on 20 November 2026 matched API segment colors and distinct stop-coordinate counts. Confirmed source and segment popups, both leg visits at the transfer, alternative selection, and zoom and fit controls.
- Checked all four polyline colors against actual API labels. At 390, 768 and 1440 pixels, the transfer journey markers fit inside the map with no horizontal page overflow.
- Confirmed OpenStreetMap tiles loaded and attribution was displayed. Blocking tile requests showed the fallback and retry action while the transfer marker and route overlay remained available.

## Phase 8 stop point (historical)

Phase 8 completed the interactive journey map.

## Phase 9 — Transport Operator Dashboard

Completed on 21 November 2026. The local /operator page uses Recharts and the exported DuckDB and CSV analytics. Network coverage spans 1,063,956 model profiles and 1,616 of 2,574 scheduled routes. Of all profiles, 169,300 have a reliable classification and 894,656 carry Insufficient Data. The network distribution keeps all four labels.

The explorer supports route-name and ID search over the paged route table, exact route selection, day type and half-hour IST filters. The heatmap shows High profiles divided by all profiles in each matching cell. Hatched cells denote absent groups and use a separate legend entry from measured zero. Weekday/weekend summaries use counts summed before division. The High-segment table shows up to ten matching High profiles ordered by supporting journey count.

The morning/evening report uses exported average reconstructed loads and group observation counts, with a day-type filter. The weekly report uses all five exported weeks and exposes observed days, observation counts, mean, median and 90th percentile. The weekly and peak reports retain their network-wide scope. Historical model labels and reconstructed loads do not establish actual vehicle occupancy.

The existing analytics routes and heatmap endpoints gained optional server-side search and aggregation. A bounded high-segments endpoint exposes actual stop names and supporting journeys and days. These queries reuse the read-only DuckDB layer.

### Verification

- All 87 backend tests passed, including new checks reconciling heatmap denominators and High counts with the network totals and matching actual High profiles to the crowding API.
- Strict TypeScript and Vite production builds passed. In Edge, verified network KPI values, the four-slice distribution, peak bars, weekly lines, report denominators and responsive chart dimensions at 390, 768 and 1440 pixels.
- Exercised all six dashboard API endpoints, pagination, route search and drill-down, day and slot filters, heatmap selection, reset and empty results. Compared a filtered table row and heatmap numerator/denominator to API responses. Blocked the segment endpoint and verified recovery through Retry. The final browser run reported no runtime exceptions.
- Refreshed the local FastAPI service on port 8000 and checked the production preview at /operator and its proxied High-segment endpoint.

## Phase 9 stop point (historical)

Phase 9 completed the operator dashboard.

## Phase 10 — Model Insights and Methodology

Completed on 21 November 2026. The About page explains the original Delhi bus-planning challenge, ticket preprocessing, GTFS matching, ambiguity filtering, assumed alighting and cumulative outgoing segment load. Ordered diagrams describe reconstruction and the offline-to-application architecture. The page explains how missing vehicle identifiers, unmatched stops, ambiguous assignments, unrecorded passengers, sparse profiles and unknown capacity constrain the findings.

Model Insights reads model_metadata.json and the four saved evaluation and consistency CSVs through the existing FastAPI endpoints. It presents the chronological training, validation and test dates, historical median and hourly fallback rules, support requirements and training-segment quartile labels. The comparison chart has a numeric table. Weekly and peak charts include keyboard-accessible underlying values and denominators.

### Evidence and verification

- Read the original project brief and inspected notebook source as text. Checked the route and stop matching, scheduled-trip acceptance, passenger movement calculation, chronological split, median selection, threshold rules and evaluation formulas. No notebook cells were executed.
- Held-out coverage was 84.66% (442,098 predictions across 522,214 observations). MAE was 0.4686 and RMSE was 0.9216. The 90.97% within-one-passenger figure concerns agreement with reconstructed recorded loads on evaluated segments. The separate comparison used 404,017 common observations, with baseline/final MAE of 0.4895/0.4766 and RMSE of 0.9415/0.9346.
- Verified weekly and peak values against weekly_analysis.csv and peak_analysis.csv. The view reports the weekly mean range and the partial final week, and displays separate weekday and weekend peak means and sample counts.
- Strict TypeScript checks and the production build passed. In Edge, compared rendered metadata, test scores, common-subset table rows, weekly means and peak means and observation counts with the files on disk. Verified charts, keyboard activation of the data disclosure, navigation between both pages, diagrams, all six limitations, API retry, and layouts at 390, 768 and 1440 pixels.

## Current stop point

Phase 10 is complete in the local production build. Further phases await authorization.
