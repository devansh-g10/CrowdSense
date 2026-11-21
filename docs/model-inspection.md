# Phase 1 inspection — 20 November 2026

## Provenance

The initial repository contained a minimal README and the untracked `CrowdRoute_Delhi_Model/` directory with exactly 13 exported files. No local ZIP, notebook, application, tests or agent instructions were present. The user confirmed the folder was already unzipped from the model archive. Original assets were left in place and copied with exclusive file creation to `data/processed/`; source and destination SHA-256 hashes match. The ZIP itself was not supplied, so no archive CRC or original archive hash is claimed.

The linked problem statement was read through the connected Google Docs tool. It requests a bus-only planner based on static GTFS and ticket-derived crowding, with clear assumptions and reliability information. Its illustrative seat availability language is not supported by this model's metadata; future product copy must describe relative historical crowding instead.

The linked Colab notebook was retrieved through Google Drive and saved in `notebooks/CrowdRoute_Delhi_ML_Pipeline.ipynb`, including existing outputs. Its 66 code cells were inspected as text; no cells were executed. It has no saved error outputs. This does not independently establish that the pipeline can be rerun, and rerunning it is outside the authorized scope. The notebook and saved outputs remain private and ignored by Git.

## Completed notebook workflow

The notebook cleans ticket data and timestamps, creates time features, inspects demand and vehicle coverage, integrates GTFS, matches route and stop names, and uses DuckDB to manage the processing tables. It reconstructs scheduled trips, filters ambiguous assignments, constructs passenger boarding/alighting events and cumulative segment loads, and checks those outputs.

Cells 41–51 build a route/pattern/segment/day-type/time-slot historical median with hourly fallback. Supported 30-minute estimates take priority; supported hourly estimates follow; low-support values can remain numerically present, so the exported classification must always accompany the numeric prediction. Cells 52–57 contain saved test evaluation, fair model comparison, weekly consistency and peak analysis. Cells 58–60 establish relative thresholds and final classifications. Cells 61–66 generate analytics, export files, verify counts, and package the ZIP. These completed operations were not repeated.

## Metadata and classification

- Version: 1.0; model: Historical Median with Hourly Fallback.
- Timezone: Asia/Kolkata; slot duration: 30 minutes; slot index: 0–47.
- Training period: 1–21 October 2026; validation: 22–24 October; test: 25–31 October.
- Metadata records 2,559,899 ticket records and 1,063,956 final profiles.
- Profile support minimum: 5 samples across 3 days. High support: 20 samples across 7 days.
- Threshold reference minimum: 20 samples across 5 days. Thresholds use training-period segment load quartiles, Q25 and Q75.
- Insufficient support/reference evidence or missing prediction produces `Insufficient Data`. Otherwise values below Q25 are Low, above Q75 are High, and values between thresholds, including equality, are Moderate.
- Final exports do not contain `reference_days`, although the notebook uses it for classification. Preserve the existing labels; the export alone cannot fully rederive that rule.
- The metadata explicitly sets `actual_occupancy_validated` and `capacity_calibration_available` to false.

The metadata lists missing vehicle numbers, unmatched ticket stops, partial assignment coverage, schedule-based reconstruction, unrecorded passengers/pass holders, assumed alighting at ticket destination, and unknown bus capacity. Numeric loads are estimates based on recorded tickets, not verified total occupancy.

## Verified inventory

| Export | Rows | Purpose |
| --- | ---: | --- |
| calendar.parquet | 1 | GTFS service calendar |
| crowding_model.parquet | 1,063,956 | Final predictions, support and classification |
| route_analytics.parquet | 50,318 | Aggregated route/day-type/time-slot analytics |
| route_lookup.parquet | 1,980 | Ticket route to GTFS route mapping |
| route_stop_sequence.parquet | 109,660 | Pattern-specific ordered stops and coordinates |
| routes.parquet | 2,574 | GTFS route definitions |
| stops.parquet | 6,862 | Stop lookup with coordinates |
| trip_schedule.parquet | 2,737,136 | Scheduled stop departures in seconds |
| model_comparison.csv | 2 | Saved fair test-set model comparison |
| test_metrics.csv | 1 | Saved held-out evaluation metrics |
| peak_analysis.csv | 6 | Weekday/weekend peak summaries |
| weekly_analysis.csv | 5 | Saved weekly stability summaries |
| model_metadata.json | — | Model identity, periods, support rules, limitations |

All eight Parquet counts match notebook cell 65's saved output. Verification also fully decoded all Parquet columns, parsed all CSVs and metadata, and checked for negative predicted loads, missing classifications and invalid time slots. None were found. File sizes, hashes and schemas appear in `phase1-verification.json`. This verifies the exports' readability and consistency, not ground-truth accuracy or all future route joins.

| Preserved classification | Profiles |
| --- | ---: |
| Low | 571 |
| Moderate | 159,982 |
| High | 8,747 |
| Insufficient Data | 894,656 |

The crowding lookup key is `(route_id, pattern_id, stop_sequence, from_stop_id, to_stop_id, is_weekend, time_slot)`. Future routing must retain the pattern and segment identities. Schedule departure times are seconds, and the calendar's day flags/dates are strings. Its one service runs all seven weekdays with encoded bounds 20250101–20400101; this describes the supplied static feed, not independently verified current service. No `calendar_dates` exception export exists in this 13-file bundle. These are integration notes for a later phase.

## Existing evaluation, not new results

`test_metrics.csv` reports 522,214 total observations, 442,098 evaluated observations, MAE 0.4686, RMSE 0.9216, prediction bias -0.1388, within-one-passenger percentage 90.97, and coverage percentage 84.66. These are saved estimates against the notebook's reconstructed recorded loads; they are not independent occupancy measurements.

`model_comparison.csv` compares 404,017 common observations: baseline MAE/RMSE 0.4895/0.9415, final model 0.4766/0.9346. Its evaluation denominator differs from the broader test metrics and must not be conflated with them. No evaluation or prediction was rerun during Phase 1.
