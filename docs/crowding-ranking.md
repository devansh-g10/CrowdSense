# Phase 5 historical crowding and journey ranking

The completed GTFS planner and the existing `crowding_model.parquet` are reused. `backend/journey_crowding.py` performs bounded batch lookups; `backend/journey_ranking.py` orchestrates planning, enrichment and recommendations; `backend/crowding_schemas.py` defines evidence and policy fields. No training, notebook execution or source-model alteration occurs.

## Request and candidate scope

`GET /api/journeys` accepts all Phase 4 parameters and adds `preference=fastest|comfortable|balanced`, defaulting to `balanced`. App version is 0.5.0; the same 14 API paths remain available. For example, this real pair has different fastest and lower-relative-crowding options:

```text
/api/journeys?source_stop_id=3619&destination_stop_id=3621&travel_date=2026-11-20&departure_time=08:45:23&max_wait_minutes=30&max_transfers=0&preference=comfortable&limit=3
```

The existing bounded timetable search reconstructs at most **80 valid journey candidates for ranking before applying the public result limit**. SQL stage bounds remain 256 initial boardings, 2,048 destination events, 8,192 transfer events and 200 candidates per kind. Individual legs are still limited to 512 stops. Ordinary callers of the Phase 4 planner retain its original limit behavior; the orchestration service explicitly requests the larger internal pool.

The response reports `ranking_candidates_evaluated`, `ranking_pool_limit` and `ranking_pool_truncated` separately from SQL search truncation and the public `result_limit`. Recommendations compare only the examined pool. They are not a claim of global optimality beyond the search limits, wait/duration bounds or static schedule data. The existing resource guard covers the entire request; schedule and crowding connections open sequentially, close reliably and use the same memory/thread/spill settings. Only the bounded segment key set is inserted into a temporary in-memory relation. No complete export is loaded into pandas or Python lists.

## Exact segment evidence

Each actual journey segment is matched on all seven model dimensions:

```text
route_id, pattern_id, from_stop_sequence,
from_stop_id, to_stop_id, is_weekend, time_slot
```

`stop_sequence` in the model equals the segment's actual `from_stop_sequence`. Repeated stop IDs remain distinguished by their sequence. `is_weekend` and `time_slot = hour * 2 + minute // 30` come from the **individual segment's scheduled departure in civil Asia/Kolkata time**. They do not come from the request time, initial boarding time or the leg's service date. A Friday service continuing into Saturday consequently uses Saturday profiles for its post-midnight segments, after unrolling GTFS 24+ hour times.

All values are bound SQL parameters; batch construction changes only placeholder counts. No nearby-route, pattern, time-bin or route-average prediction is substituted. The exported model already includes its hourly fallback, so no fallback is recomputed. A missing exact profile is explicitly `profile_found: false`, `crowding_level: Insufficient Data` and `unavailable_reason: no_matching_exported_profile`. This marks absence rather than inventing a model record.

Original Low, Moderate, High and Insufficient Data labels are retained. Raw numeric estimates remain in `exported_predicted_load`; optional baseline, thresholds, support counts, observed days, source and reference samples are preserved. The usable `predicted_load` is null for unsupported classifications. A numeric exported estimate can still exist on an Insufficient Data row, so `prediction_available` and `reliable_classification` are different flags.

For this policy, a reliable classification requires a finite nonnegative exported prediction, an exported Low/Moderate/High label, Medium or High support, at least 5 samples across 3 days, and at least 20 reference samples. Medium support alone is insufficient: the actual export contains Medium-support Insufficient Data rows. Reference-day counts are absent from the export; their original classification check remains supported by notebook evidence, not rederived here. “Reliable” means supported historical classification for this policy, not verified actual occupancy or calibrated confidence.

## Journey coverage and support

The journey's `crowding` summary separates:

- `prediction_coverage`: segments with finite numeric exported predictions divided by all segments. This includes low-support estimates and is not a comfort qualification.
- `reliable_classification_coverage`: supported Low/Moderate/High segments divided by all segments.
- `duration_prediction_coverage` and `duration_reliable_classification_coverage`: the same evidence measures weighted by actual approximate in-vehicle segment seconds.
- `data_support` and `data_support_duration_seconds`: counts and durations by the original High, Medium, Low support labels, plus Missing for absent profiles. Missing support is not relabeled Low.
- `classification_counts`: counts of the preserved four classifications, including unknown/missing evidence as Insufficient Data.

These are **fractions of available evidence**, not bus occupancy percentages. Initial waiting and transfer waiting are excluded from crowding duration denominators. Zero-duration repeated-stop events retain their labels/counts but contribute zero duration; no artificial second or distance is assigned.

Relative scores are ordinal policy values: Low = 0, Moderate = 0.5, High = 1. They describe each segment relative to its own historical reference, not absolute passenger counts or bus capacity. A Low label does not mean zero passengers. In particular, a High segment on one route need not have more passengers than a Low segment on another route.

Let `d_i` be segment seconds, `D` their total, `r_i` indicate reliable classification, and `s_i` be its ordinal score. The reported known-duration mean is:

```text
duration_weighted_relative_crowding = sum(d_i * r_i * s_i) / sum(d_i * r_i)
```

It is null when no reliable positive-duration evidence exists. It must always be read with coverage, because unknown time is excluded from this diagnostic mean. For ranking, unknown/unreliable segments are penalized above the highest known ordinal label:

```text
duration_weighted_penalized_crowding =
    [sum(known_duration * ordinal_score) + 1.25 * unknown_duration] / D
```

All-unknown crowding therefore costs 1.25, rather than zero/Low; known High costs 1. If total in-vehicle duration is zero, duration-weighted summaries remain null, comfort eligibility is false, and ranking uses the explicit unknown penalty instead of inventing a duration weight. These are ranking policy units, not measured occupancy fractions, probabilities or accuracy metrics.

## Three preferences

The complete `ranking_policy` is returned with the response. The coverage thresholds and penalty weights below are explicit product choices, not fitted or validated model performance metrics.

| Preference | Rule |
| --- | --- |
| Fastest | Minimum `total_duration_seconds`, including initial wait and transfer wait; fewer transfers and lower uncertainty break ties |
| Comfortable | Among journeys with positive in-vehicle duration and at least 0.8 reliable coverage by **both segment count and duration**, minimize unknown-penalized relative crowding; total time and transfers break ties |
| Balanced | Minimize `total_duration_seconds / 60 + 30 * unknown_penalized_relative_crowding + 5 * transfers` |

Every journey exposes duration, crowding penalty and transfer penalty components plus the resulting Balanced cost. The latter is an equivalent-minute policy cost, not an estimated travel time. Transfer waiting is already part of actual total duration; the separate five-minute transfer term expresses an additional preference cost. Comfortable eligibility does not remove unknown penalties from its remaining unsupported duration.

If no examined journey meets both coverage requirements, Comfortable has no recommendation. The response includes `insufficient_reliable_coverage` with an explanation, `preference_available: false` if it was requested, and `applied_preference: null`. Feasible alternatives remain available in duration order without silently claiming that Fastest or Balanced satisfied the requested comfort preference. If there are no feasible journeys or the date is unsupported, no recommendation is fabricated.

## Deduplication and response limits

`journeys` contains at most the requested `limit` (maximum 20), ordered by the available requested preference. A stable `journey_id` is derived from actual route/pattern/trip/service-date/boarding-sequence/alighting-sequence identities. Exact duplicate journeys are removed before recommendation selection.

`recommendations` contains at most three **unique winners**, each carrying its full journey, a list of winning `preferences` and per-preference explanations. If the same journey wins Comfortable and Balanced, it appears once with both labels. No inferior alternative is selected merely to make recommendation cards different. A recommendation may fall outside the limited `journeys` list; its complete embedded journey remains inspectable, so there is no dangling ID or need to inflate the main result limit. Different valid trip instances or repeated sequence occurrences are not guessed to be the same physical bus; vehicle identity is unavailable.

All segments, journeys, recommendation costs and policy explanations remain explicit that relative historical crowding is not actual bus occupancy or guaranteed seat availability. No capacity, occupancy percentage or seat guarantee is generated. Static schedule dates, missing exception data and departure-only arrival/duration approximations retain their Phase 4 warnings.

## Reproducible real-data checks

`scripts/discover_crowding_cases.py` finds schedule-aligned Low, Moderate, High, Insufficient Data and Medium-support Insufficient Data witnesses using the actual GTFS rows and model keys. The saved `phase5-crowding-cases.json` includes input hashes, so tests reuse discovery evidence only for unchanged inputs. It also records a trip crossing the 08:30/09:00 slot boundary. Earlier Phase 4 real transfer, repeated-stop and midnight witnesses are reused.

Use the current environment and running local backend:

```powershell
# Rediscover only when inputs change:
# & ./.venv/Scripts/python.exe -m scripts.discover_crowding_cases
& ./.venv/Scripts/python.exe -m unittest discover -s tests -v
& ./.venv/Scripts/python.exe -m scripts.verify_crowding_ranking
```

The 20 new integration tests compare segment joins directly with the seven-key model query and independently check coverage, support and duration arithmetic. They exercise all labels, no-profile cases, Medium support without a reliable classification, Friday/Saturday midnight changes, repeated zero-duration segments, preference validation, true minimum total time, policy formulas, pool truncation, duplicate-label merging and explicit unavailable comfort. The final complete suite passed **86 tests in 71.044 seconds** of reported unittest runtime, including all 66 preserved tests.

Fourteen live journey/ranking checks passed, plus Swagger HTML and the 14-path OpenAPI document. The real comparison pair 3619 → 3621 at 08:45:23 on 20 November 2026 examines 26 unique journeys: Fastest selects `2195_FULL_08_35` with 152 seconds total duration and unknown-penalized relative score 1.25; Comfortable and Balanced select `1011_FULL_08_50` with 1,040 seconds total duration and supported Low relative score 0. That shared winner appears once with both preference labels. Its Low score is not zero passengers or a seat guarantee.

All 13 original and processed hashes still match Phase 1, and spill directories are cleaned. No dependencies changed in this phase; the existing nonfatal TestClient HTTPX deprecation notice remains. Measured results and live evidence are in PROGRESS.md and `phase5-ranking-verification.json`. No model/export changes, retraining, notebook execution, frontend work, publication or GitHub push occurred. Stop after Phase 5.
