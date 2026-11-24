# Route map configuration

Set `VITE_MAPBOX_PUBLIC_TOKEN` to a Mapbox public browser token in `frontend/.env.local`. Restart Vite after changing environment settings and rebuild for production. Vite embeds public variables in the client bundle. Use a URL-restricted public token for the deployment origin. Keep private service credentials on the server. The repository already ignores local environment files and build output.

The basemap starts with Mapbox Satellite Streets v12. Street mode uses Mapbox Streets v12. Imagery detail varies by location and zoom. The current exports contain ordered stops without GTFS shape polylines. The overlay requests Mapbox driving directions for each bus leg, in batches of up to 25 waypoints with a shared stop. Each stop must snap to a road within 100 m. Distance and driving time describe the calculated road path. Scheduled journey duration includes waits. Route requests use browser HTTP caching under the response headers. Each line carries the historical crowding classification from its own journey segment. Stops sharing coordinates retain their individual visits and times.

## Optional venue observations

Set `VITE_VENUE_MAP_FEED` to a same-origin URL serving your authorized venue's current GeoJSON FeatureCollection. This project supplies GTFS and historical ticket profiles. Venue detection, surveyed gates and cameras, and a pedestrian evacuation routing service must be supplied by the venue operator. The map accepts an approved route produced by that service. A bus itinerary cannot establish a safe evacuation path.

The endpoint should return a complete snapshot with a top-level `observed_at` timestamp (ISO 8601 including timezone). Stamp it with the observation time. Repeatedly serving an old reading with a new timestamp would present stale observations as current. The map polls every ten seconds while mounted, drops failed or expired snapshots, and expires observations after sixty seconds. An empty `features` array clears venue layers.

Each feature requires a descriptive `properties.name` and one of the following `properties.kind` values.

| Kind | WGS84 geometry | Other required properties |
| --- | --- | --- |
| detection | Point at the georeferenced observation | `density` in people per square metre |
| zone | Polygon with closed boundary rings | `count` (nonnegative integer), `density` (people/m²), and `risk` (low, moderate or high) |
| camera | Point at the surveyed camera | — |
| entry or exit | Point at the surveyed gate | — |
| evacuation | LineString in travel order from the venue routing service | `approved: true` |

Use surveyed camera and gate positions and surveyed zone boundaries. Project detections onto the ground using the camera calibration or supply measured density observations at known geographic locations. Pixel coordinates and the location of the camera itself do not locate each detected person. The feed owns count deduplication, measured area, risk thresholds and route approval. The heatmap visualizes relative spatial concentration. Clicking a zone gives its actual reported count, density and risk.

