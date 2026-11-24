import type { FeatureCollection, LineString } from 'geojson'
import type { Journey } from './api'
import { position, strokes } from './routeGeometry'
import { coordinate } from './venueMap'

interface RoadLeg {
  distance: number
  duration: number
  steps: { geometry: LineString }[]
}

const metric = (n: number) => Number.isFinite(n) && n >= 0

export function fallbackDirectPath(journey: Journey): { data: FeatureCollection<LineString>; distance: number; duration: number } {
  const data: FeatureCollection<LineString> = { type: 'FeatureCollection', features: [] }
  for (const leg of journey.legs) {
    const predictions = new Map(leg.segments.map(s => [s.from_stop_sequence + '/' + s.to_stop_sequence, s.crowding]))
    for (let i = 0; i < leg.stops.length - 1; i++) {
      const from = leg.stops[i], to = leg.stops[i + 1]
      const p1 = position(from), p2 = position(to)
      if (p1 && p2) {
        const evidence = predictions.get(from.stop_sequence + '/' + to.stop_sequence)
        const level = evidence?.crowding_level ?? 'Insufficient Data'
        data.features.push({
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: [p1, p2] },
          properties: {
            name: from.stop_name + ' → ' + to.stop_name,
            color: strokes[level] ?? strokes['Insufficient Data'],
            detail: (leg.route_name || leg.route_id) + ' · ' + level + ' historical crowding'
          }
        })
      }
    }
  }
  return { data, distance: 0, duration: journey.total_duration_seconds }
}

export async function roadPath(journey: Journey, signal: AbortSignal): Promise<{ data: FeatureCollection<LineString>; distance: number; duration: number }> {
  const token = import.meta.env.VITE_MAPBOX_PUBLIC_TOKEN?.trim()
  if (!token?.startsWith('pk.')) return fallbackDirectPath(journey)

  try {
    const data: FeatureCollection<LineString> = { type: 'FeatureCollection', features: [] }
    let distance = 0, duration = 0

    for (const leg of journey.legs) {
      const points = leg.stops.map(position)
      if (points.length < 2 || points.some(p => !p)) return fallbackDirectPath(journey)
      const predictions = new Map(leg.segments.map(s => [s.from_stop_sequence + '/' + s.to_stop_sequence, s.crowding]))

      for (let start = 0; start < points.length - 1; start += 24) {
        const batch = points.slice(start, start + 25)
        const query = new URLSearchParams({
          access_token: token,
          geometries: 'geojson',
          overview: 'full',
          steps: 'true',
          radiuses: batch.map(() => 100).join(';')
        })
        const response = await fetch(
          'https://api.mapbox.com/directions/v5/mapbox/driving/' + batch.join(';') + '?' + query,
          { signal: AbortSignal.any([signal, AbortSignal.timeout(12000)]) }
        )
        if (!response.ok) return fallbackDirectPath(journey)
        const result = await response.json()
        const road = result.routes?.[0]
        if (result.code !== 'Ok' || road?.legs?.length !== batch.length - 1) return fallbackDirectPath(journey)

        for (const [i, part] of (road.legs as RoadLeg[]).entries()) {
          const from = leg.stops[start + i], to = leg.stops[start + i + 1]
          const evidence = predictions.get(from.stop_sequence + '/' + to.stop_sequence)
          const level = evidence?.crowding_level ?? 'Insufficient Data'
          if (!metric(part.distance) || !metric(part.duration) || !part.steps?.length) return fallbackDirectPath(journey)

          for (const step of part.steps) {
            const g = step.geometry
            if (g?.type !== 'LineString' || g.coordinates.length < 2 || !g.coordinates.every(coordinate)) {
              return fallbackDirectPath(journey)
            }
            data.features.push({
              type: 'Feature',
              geometry: g,
              properties: {
                name: from.stop_name + ' → ' + to.stop_name,
                color: strokes[level] ?? strokes['Insufficient Data'],
                detail: (leg.route_name || leg.route_id) + ' · ' + level + ' historical crowding · ' + (evidence?.data_support ?? 'Missing') + ' support'
              }
            })
          }
          distance += part.distance
          duration += part.duration
        }
      }
    }
    return { data, distance, duration }
  } catch {
    return fallbackDirectPath(journey)
  }
}
