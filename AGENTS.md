# CrowdRoute Delhi permanent rules

- Never retrain the existing model.
- Never repeat completed work unnecessarily. Read PROGRESS.md before starting work.
- Never overwrite original model files. Treat CrowdRoute_Delhi_Model/ and data/processed/ model assets as immutable; verify hashes before reusing copies.
- Optimize RAM usage using DuckDB. Query Parquet directly, select only needed columns, use bounded results, and configure memory limits and disk spill. Do not load entire exports into pandas.
- Never fabricate data, routes, predictions or metrics. Report unavailable evidence explicitly.
- Preserve Insufficient Data classifications; never replace them with Low or imply that missing evidence means an empty bus.
- Relative historical crowding is not actual bus occupancy or guaranteed seat availability. Carry this distinction into every future API and UI.
- Do not publish restricted data or push to GitHub without permission. Ignore private exports, notebooks with saved outputs, archives, credentials and local databases.

## Current scope

Phases 1–11 are complete. Phase 11 audited the existing application against real exports and verified targeted fixes and optimizations. See PROGRESS.md for results and limitations. Stop after Phase 11.

## Layout

The Git project root is D:/CrowdSense/CrowdSense, inside the outer workspace D:/CrowdSense. Preserve the original export directory. Read README.md and docs/model-inspection.md for provenance and limitations. Run scripts/prepare_phase1.py only when inputs or verification code change; use its existing report for routine reference.
