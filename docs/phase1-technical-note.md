# Crowdedness-aware journey planner

## From a ticket to a journey option

The October 2026 input contains 2,559,899 Delhi ticket records. The notebook uses passenger counts, matches ticket routes and ordered origin/destination stops to the static GTFS feed, and assigns tickets to plausible scheduled vehicle trips. It excludes ambiguous matches. For each usable trip it adds boardings, subtracts assumed alightings at the ticket destination and carries the running load forward to the next stop. Stop order and route pattern distinguish the direction of travel.

The model groups directed segments by weekday/weekend and half-hour in Delhi local time. It estimates the historical median recorded load, using an hourly fallback for sparse slots. Supported estimates are compared with that segment’s training quartiles to produce Low, Moderate or High. The minimum for a supported profile is five samples across three days. The segment reference requires twenty samples across five days. Missing predictions or inadequate evidence receive Insufficient Data.

The planner looks up the historical profile at each segment’s scheduled departure. A Comfortable recommendation requires reliable classifications for at least 80% of both the segments and in-vehicle time. A commuter can compare total journey time including waits, check coverage, and locate each classified stretch on the map. Operators can filter High profiles by route, day type and half-hour to identify stretches worth checking in the field.

## Evidence and limits

Training used 1–21 October, validation used 22–24 October, and testing used 25–31 October. On the held-out week the model returned numeric estimates for 442,098 of 522,214 segment observations. Mean absolute error was 0.4686 recorded passengers on the evaluated subset. Reliable crowding labels have stricter evidence requirements. Of 1,063,956 exported profiles, 894,656 were classified as Insufficient Data.

The saved weekly report shows means of 1.293–1.316 recorded passengers per observed segment over five calendar windows. The final window covers three days. Weekday morning and evening peak means were 1.347 and 1.316, respectively. Weekend morning and evening means were 1.287 and 1.303. These reports describe variation in recorded loads. The holdout evaluation measures prediction error separately.

Missing vehicle identifiers, unmatched stops, ambiguous trips, pass holders and differences between intended and actual alighting all limit the estimates. Unknown bus capacity prevents translating a relative label into a seat or overload guarantee. A month of records supports a weekly comparison and provides limited evidence for seasonal or festival travel.

## Reproduce the raw-data pipeline

1. Open the [pipeline notebook](../notebooks/CrowdRoute_Delhi_ML_Pipeline.ipynb) in a fresh Google Colab runtime. Use the October 2026 ticket archive and the matching static GTFS feed provided for the challenge. Extract the inputs before running the cells.
2. Put `October-Delhi.csv`, `stops.txt`, `routes.txt`, `trips.txt`, `stop_times.txt` and `calendar.txt` directly in `/content`. Use `/content` as the notebook working directory. The ticket reader uses a relative filename and the GTFS reader uses absolute paths.
3. Run cells 1–66 in order. Cell 1 installs analysis dependencies. The pipeline builds its intermediate DuckDB tables in the fresh runtime, then writes the model, timetables and evaluation reports to `/content/crowdroute_export`.
4. Check cell 65’s row-count assertions and download the archive produced by cell 66. Compare the inventory and evaluation with the [export inspection](model-inspection.md). Keep a reproduced archive separate from the application’s supplied model. Exact rerun results depend on using the same source data and compatible library versions.

The shipped application reads the existing exports. The recorded notebook outputs and export verification are available for inspection. This audit verified the shipped model and application without executing training on the raw inputs.
