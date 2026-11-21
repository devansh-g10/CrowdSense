export interface Stop { stop_id: string; stop_name: string }
export interface Overview { profiles:number; routes:number; routes_with_profiles:number; classifications:Record<CrowdingLevel,number> }
export interface RouteStats {route_id:string;route_name:string;profiles:number;low_profiles:number;moderate_profiles:number;high_profiles:number;insufficient_data_profiles:number}
export interface SlotCounts {is_weekend:boolean;time_slot:number;segment_profiles:number;high_crowding_segments:number;insufficient_data_segments:number}
export interface Peak {day_type:'Weekday'|'Weekend';period:'Morning Peak'|'Evening Peak'|'Other Hours';segment_observations:number;average_load:number}
export interface Week {week_number:number;observed_days:number;segment_observations:number;average_recorded_load:number;median_recorded_load:number;p90_recorded_load:number}
export interface HighSegment {route_id:string;pattern_id:number;stop_sequence:number;from_name:string;to_name:string;is_weekend:boolean;time_slot:number;sample_journeys:number;observed_days:number}
type Rows<T> = {items:T[]}
type AnalyticsParams = Record<string,string>
export interface Model {
  model_type:string; version:string; final_profiles:number; time_slot_minutes:number; total_ticket_records:number
  timezone:string; training_period:string; validation_period:string; testing_period:string
  minimum_profile_samples:number; minimum_profile_days:number; minimum_reference_samples:number; minimum_reference_days:number
  limitations:string[]
}
export interface Evaluation {
  test_metrics:{total_observations:number; evaluated_observations:number; MAE:number; RMSE:number;
    prediction_bias:number; within_one_passenger_percentage:number; coverage_percentage:number}
  model_comparison:{model:string; observations:number; MAE:number; RMSE:number}[]
}
export type Preference = 'balanced' | 'fastest' | 'comfortable'
export interface JourneyQuery {
  source_stop_id: string; destination_stop_id: string; travel_date: string
  departure_time: string; preference: Preference
}
export type CrowdingLevel = 'Low' | 'Moderate' | 'High' | 'Insufficient Data'
export type Support = 'High' | 'Medium' | 'Low' | 'Missing'
export interface JourneyLeg {
  route_name: string
  route_id: string
  trip_id: string
  stops: (Stop & { latitude:number; longitude:number; stop_sequence: number; scheduled_departure_at: string })[]
  segments: { from_stop_sequence:number; to_stop_sequence:number; crowding: {
    crowding_level: CrowdingLevel; data_support: Exclude<Support,'Missing'> | null
    sample_journeys: number | null; observed_days: number | null; unavailable_reason: string | null
  } }[]
}
export interface Journey {
  journey_id: string
  total_duration_seconds: number
  initial_wait_seconds: number
  transfer_wait_seconds: number
  transfers: number
  departure_at: string
  estimated_arrival_at: string
  legs: JourneyLeg[]
  crowding: {
    total_segments: number; predicted_segments: number; reliably_classified_segments: number
    classification_counts: Record<CrowdingLevel, number>
    data_support: Record<Support, number>
  }
}
interface Results {
  status: 'ok' | 'no_journeys' | 'unsupported_date' | 'search_incomplete'
  reason: string | null; preference_unavailable_reason: string | null
  journeys: Journey[]; warnings: string[]
  search: { search_truncated: boolean; ranking_pool_truncated: boolean; result_limit_reached: boolean }
  unavailable_recommendations: {preference: Preference; explanation: string}[]
  recommendations: { preferences: Preference[]; journey: Journey }[]
}
const base = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
async function get<T>(path: string, signal: AbortSignal, params?: Record<string,string>): Promise<T> {
  const query = params ? '?' + new URLSearchParams(params) : ''
  const response = await fetch(base + path + query, {signal, headers: {Accept:'application/json'}})
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.error?.message || 'The transit service is unavailable.')
  }
  if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('The transit API could not be reached.')
  return response.json()
}
export const api = {
  stops: (text: string, signal: AbortSignal) => get<{items: Stop[]}>('/stops', signal, {search:text,limit:'6'}),
  journeys: (q: JourneyQuery, signal: AbortSignal) => get<Results>('/journeys', signal, {...q,limit:'4'}),
  overview: (signal: AbortSignal) => get<Overview>('/analytics/overview',signal),
  routeStats: (params:AnalyticsParams,signal:AbortSignal)=>get<Rows<RouteStats>>('/analytics/routes',signal,params),
  slotCounts: (params:AnalyticsParams,signal:AbortSignal)=>get<Rows<SlotCounts>>('/analytics/heatmap',signal,{...params,aggregate_slots:'true',limit:'96'}),
  peaks: (signal:AbortSignal)=>get<Rows<Peak>>('/analytics/peak-hours',signal),
  weeks: (signal:AbortSignal)=>get<Rows<Week>>('/analytics/weekly',signal),
  highSegments: (params:AnalyticsParams,signal:AbortSignal)=>get<Rows<HighSegment>>('/analytics/high-segments',signal,{...params,limit:'10'}),
  evaluation: (signal:AbortSignal)=>get<Evaluation>('/analytics/model-performance',signal),
  model: (signal: AbortSignal) => get<Model>('/model-info',signal)
}

