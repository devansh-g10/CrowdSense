import { lazy, Suspense, useCallback, useMemo, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { BusFront, CalendarDays, ChevronDown, Clock3, History, MapPinned, Pencil, Route, Users } from 'lucide-react'
import { api, type CrowdingLevel, type Journey, type JourneyLeg, type JourneyQuery, type Preference } from './api'
import type { SearchDraft } from './Planner'
import { Badge, Card, State, useRequest } from './ui'

const RouteMap = lazy(() => import('./RouteMap'))

const levels: CrowdingLevel[] = ['Low','Moderate','High','Insufficient Data']
const colors = {Low:'low', Moderate:'moderate', High:'high', 'Insufficient Data':'unknown'}
const clock = new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Kolkata',hour:'2-digit',minute:'2-digit',second:'2-digit'})
const day = new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',day:'numeric',month:'short',year:'numeric'})
function timestamp(value:string) {
  const date = new Date(value)
  return clock.format(date) + ' · ' + day.format(date)
}
function duration(seconds:number) {
  const hours=Math.floor(seconds/3600), minutes=Math.floor(seconds%3600/60), remainder=seconds%60
  return [hours && hours+' h', minutes && minutes+' min', remainder && remainder+' s'].filter(Boolean).join(' ') || '0 min'
}
function Level({level,count}:{level:CrowdingLevel;count?:number}) {
  return <span className={'crowd-label '+colors[level]}>{level}{count!==undefined && ' · '+count}</span>
}
function Leg({leg,index}:{leg:JourneyLeg;index:number}) {
  return <section className="leg"><h3><BusFront size={17}/>Leg {index+1} · {leg.route_name || leg.route_id}</h3>
    <ol className="stop-list">{leg.stops.map((stop,i)=>{
      const evidence=leg.segments[i]?.crowding
      return <li key={stop.stop_sequence}><strong>{stop.stop_name}</strong><time dateTime={stop.scheduled_departure_at}>{timestamp(stop.scheduled_departure_at)} IST</time>
        {evidence && <div className="segment"><span>To {leg.stops[i+1].stop_name}</span><Level level={evidence.crowding_level}/>
        <small>{evidence.data_support ?? 'Missing'} support
        {evidence.sample_journeys!==null && ' · '+evidence.sample_journeys+' sampled journeys'}
        {evidence.observed_days!==null && ' · '+evidence.observed_days+' observed days'}</small>
        {evidence.unavailable_reason && <small>{evidence.unavailable_reason}</small>}</div>}</li>
    })}</ol></section>
}
function JourneyCard({journey:j,preferences,mapOpen,toggleMap}:{journey:Journey;preferences:Preference[];mapOpen:boolean;toggleMap:()=>void}) {
  const c=j.crowding
  return <Card className="journey-option"><div className="route-heading"><span className="tile"><BusFront/></span><h2>{j.legs.map(l=>l.route_name || l.route_id).join(' → ')}</h2>
    <div className="winner-tags">{preferences.map(p=><Badge key={p}>{p}</Badge>)}</div></div>
    <dl className="trip-facts">
      <div><dt>Scheduled departure</dt><dd>{timestamp(j.departure_at)}</dd></div>
      <div><dt>Estimated arrival</dt><dd>{timestamp(j.estimated_arrival_at)}</dd></div>
      <div><dt>Total duration</dt><dd>{duration(j.total_duration_seconds)}</dd></div>
      <div><dt>Total waiting</dt><dd>{duration(j.initial_wait_seconds+j.transfer_wait_seconds)}</dd></div>
      <div><dt>Transfers</dt><dd>{j.transfers===0?'Direct':j.transfers}</dd></div>
    </dl>
    <section className="evidence"><h3><Users size={17}/>Historical crowding by segment</h3>
      <div className="levels">{levels.filter(level=>c.classification_counts[level]>0).map(level=><Level key={level} level={level} count={c.classification_counts[level]}/>)}</div>
      <p>Prediction coverage <strong>{c.predicted_segments}/{c.total_segments}</strong> segments · Reliable classifications <strong>{c.reliably_classified_segments}/{c.total_segments}</strong></p>
      <p>Data support by segment · {Object.entries(c.data_support).filter(([,n])=>n>0).map(([level,n])=>level+' '+n).join(' · ')}</p>
    </section>
    <button type="button" className="edit-search map-toggle" aria-expanded={mapOpen} onClick={toggleMap}><MapPinned size={17}/>{mapOpen?'Hide route map':'View route map'}</button>
    {mapOpen && <Suspense fallback={<State kind="loading">Loading route map…</State>}><RouteMap journey={j}/></Suspense>}
    <details className="itinerary"><summary><Route size={18}/>Journey details and stops<ChevronDown size={17}/></summary>
      <p>Initial wait {duration(j.initial_wait_seconds)}{j.transfers>0 && ' · Transfer wait '+duration(j.transfer_wait_seconds)}</p>
      {j.legs.map((l,i)=><Leg key={i} index={i} leg={l}/>)}
    </details></Card>
}
function readQuery(params:URLSearchParams):JourneyQuery|null {
  const source=params.get('source_stop_id'), destination=params.get('destination_stop_id')
  const date=params.get('travel_date'), time=params.get('departure_time'), pref=params.get('preference')
  if(!source || !destination || source===destination || !date || !/^\d{4}-\d{2}-\d{2}$/.test(date) ||
     !time || !/^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$/.test(time) ||
     (pref!=='balanced' && pref!=='comfortable' && pref!=='fastest')) return null
  return {source_stop_id:source,destination_stop_id:destination,travel_date:date,departure_time:time,preference:pref}
}
function SearchResults({query}:{query:JourneyQuery}) {
  const request=useCallback((signal:AbortSignal)=>api.journeys(query,signal),[query])
  const {state,retry}=useRequest(request)
  const submitted:SearchDraft|undefined=useLocation().state?.draft
  const data=state.kind==='ready'?state.data:null
  const legs=data?.journeys[0]?.legs
  const origin=legs?.[0].stops[0] ?? submitted?.origin ?? {stop_id:query.source_stop_id,stop_name:'Stop #'+query.source_stop_id}
  const destination=legs?.at(-1)?.stops.at(-1) ?? submitted?.destination ?? {stop_id:query.destination_stop_id,stop_name:'Stop #'+query.destination_stop_id}
  const [mapSelection,setMapSelection]=useState<string|null|undefined>(undefined)
  const alternatives=new Map(data?.journeys.map(j=>[j.journey_id,j]))
  for(const winner of data?.recommendations ?? []) alternatives.set(winner.journey.journey_id,winner.journey)
  const mappedId = mapSelection === undefined ? alternatives.keys().next().value : mapSelection
  return <div className="search-results">
    <Card className="search-summary"><div><h2>{origin.stop_name} → {destination.stop_name}</h2>
      <p><CalendarDays size={16}/>{query.travel_date}<Clock3 size={16}/>{query.departure_time} IST · {query.preference}</p></div>
      <Link className="edit-search" to="/" state={{draft:{origin,destination,query}}}><Pencil size={16}/>Edit search</Link></Card>
    {state.kind==='loading' && <State kind="loading">Finding scheduled journeys…</State>}
    {state.kind==='error' && <State kind="error" retry={retry}>{state.message}</State>}
    {data && <>
      {data.status!=='ok' && <State kind="empty">{data.reason || 'No scheduled journeys found for this search.'}</State>}
      {data.unavailable_recommendations.map(r=><p className="availability" key={r.preference}><strong>{r.preference} unavailable.</strong> {r.explanation}</p>)}
      {alternatives.size>0 && <><div className="alternatives-heading"><h2>Scheduled alternatives</h2><span>{alternatives.size} shown</span></div>
        <div className="note"><History size={18}/><p>Times are approximate and shown in IST. Crowding estimates come from historical trips. Live occupancy and seat availability are unknown.</p></div>
        {[...alternatives.values()].map(j=><JourneyCard key={j.journey_id} journey={j} mapOpen={mappedId===j.journey_id} toggleMap={()=>setMapSelection(mappedId===j.journey_id?null:j.journey_id)} preferences={data.recommendations.find(r=>r.journey.journey_id===j.journey_id)?.preferences ?? []}/>)}</>}
      {(data.search.search_truncated || data.search.ranking_pool_truncated || data.search.result_limit_reached) && <p className="availability">Search or display limits apply. Additional scheduled alternatives may exist.</p>}
      {data.warnings.length>0 && <details className="source-notes"><summary>Timetable and search limitations</summary><ul>{data.warnings.map(w=><li key={w}>{w}</li>)}</ul></details>}
    </>}
  </div>
}
export function JourneyResults(){
  const [params]=useSearchParams()
  const query=useMemo(()=>readQuery(params),[params])
  if(!query) return <Card><State kind="empty">Choose two stops, a date, a time and a preference to see scheduled journeys.</State><Link className="edit-search" to="/">Open Journey Planner</Link></Card>
  return <SearchResults key={params.toString()} query={query}/>
}
