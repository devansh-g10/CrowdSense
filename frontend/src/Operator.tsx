import { useCallback, useRef, useState, type FormEvent, type RefObject } from 'react'
import { Filter, RotateCcw } from 'lucide-react'
import { api, type RouteStats, type HighSegment, type SlotCounts } from './api'
import { Card, Field, State, useRequest } from './ui'
import { NetworkStats, PeakReport, WeeklyReport, ProfileHeatmap, startTime, dayType, format } from './OperatorCharts'
import './operator.css'

const defaults={route:'',day:'',slot:'',search:''}
type Filters=typeof defaults
const pageSize=10
async function reports(signal:AbortSignal){
  const overview=await api.overview(signal)
  const peaks=await api.peaks(signal)
  const weeks=await api.weeks(signal)
  return {overview,peaks:peaks.items,weeks:weeks.items}
}
function FiltersForm({filters,apply}:{filters:Filters;apply:(f:Filters)=>void}){
  const [draft,setDraft]=useState(filters)
  function set(key:keyof Filters,value:string){setDraft(f=>({...f,[key]:value}))}
  function submit(e:FormEvent){e.preventDefault();apply({...draft,search:draft.search.trim(),route:draft.route.trim()})}
  return <Card className="operator-controls"><h2>Explore profiles</h2>
    <form onSubmit={submit}><Field id="op-route" label="Route ID"><input id="op-route" placeholder="All routes" maxLength={256} value={draft.route} onChange={e=>set('route',e.target.value)}/></Field>
    <Field id="op-day" label="Day type"><select id="op-day" value={draft.day} onChange={e=>set('day',e.target.value)}><option value="">Both day types</option><option value="false">Weekday</option><option value="true">Weekend</option></select></Field>
    <Field id="op-slot" label="Time slot (IST)"><select id="op-slot" value={draft.slot} onChange={e=>set('slot',e.target.value)}><option value="">All slots</option>{Array.from({length:48},(_,i)=><option key={i} value={i}>{startTime(i)}–{startTime((i+1)%48)}</option>)}</select></Field>
    <Field id="op-search" label="Search route table"><input id="op-search" maxLength={256} placeholder="Route name or ID" value={draft.search} onChange={e=>set('search',e.target.value)}/></Field>
    <div className="operator-actions"><button type="submit" className="btn"><Filter size={15}/>Apply filters</button><button type="button" className="edit-search" onClick={()=>{setDraft(defaults);apply(defaults)}}><RotateCcw size={15}/>Reset</button></div></form></Card>
}
function RouteTable({rows,page,turn,choose}:{rows:RouteStats[];page:number;turn:(p:number)=>void;choose:(id:string)=>void}){
  return <Card><h2>Route-wise analytics</h2>
    {rows.length===0?<State kind="empty">No matching routes.</State>:<div className="op-table"><table><thead><tr>{['Route','Profiles','Low','Moderate','High','Insufficient Data'].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{rows.slice(0,pageSize).map(r=><tr key={r.route_id}><td><button onClick={()=>choose(r.route_id)}>{r.route_name} · #{r.route_id}</button></td>{[r.profiles,r.low_profiles,r.moderate_profiles,r.high_profiles,r.insufficient_data_profiles].map((v,i)=><td key={i}>{format(v)}</td>)}</tr>)}</tbody></table></div>}
    <div className="pager"><button disabled={!page} onClick={()=>turn(page-1)}>Previous</button><span>Page {page+1}</span><button disabled={rows.length<=pageSize} onClick={()=>turn(page+1)}>Next</button></div></Card>
}
function HighProfiles({rows}:{rows:HighSegment[]}) {
  return <Card><h2>High relative crowding segments</h2>
    {!rows.length?<State kind="empty">No matching High profiles in the export.</State>:<div className="op-table"><table><thead><tr>{['Segment','Route / pattern','Day and slot (IST)','Sample journeys','Observed days'].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{rows.map(r=><tr key={[r.route_id,r.pattern_id,r.stop_sequence,r.is_weekend,r.time_slot].join('/')}><td>{r.from_name} → {r.to_name}</td><td>#{r.route_id} / {r.pattern_id}</td><td>{dayType(r.is_weekend)} · {startTime(r.time_slot)}</td><td>{format(r.sample_journeys)}</td><td>{r.observed_days}</td></tr>)}</tbody></table></div>}</Card>
}
type ExplorerProps = {filters:Filters;page:number;turn:(p:number)=>void;apply:(f:Filters)=>void}
type ScopeData = {cells:SlotCounts[];high:HighSegment[]}
function Explorer(props:ExplorerProps){
  // The parent keys this scope by route, day and slot. Table pagination and
  // name search can reuse its heatmap and segment rows until the scope changes.
  const scope=useRef<ScopeData|null>(null)
  return <ExplorerPage key={JSON.stringify([props.filters.search,props.page])} {...props} scope={scope}/>
}
function ExplorerPage({filters,page,turn,apply,scope}:ExplorerProps & {scope:RefObject<ScopeData|null>}){
  const request=useCallback(async(signal:AbortSignal)=>{
    const params:Record<string,string>={}
    if(filters.route)params.route_id=filters.route
    if(filters.day)params.is_weekend=filters.day
    if(filters.slot)params.time_slot=filters.slot
    const routes=await api.routeStats({...params,search:filters.search,limit:String(pageSize+1),offset:String(page*pageSize)},signal)
    if(!scope.current){
      const heatmapParams = { ...params }
      delete heatmapParams.time_slot
      const cells=await api.slotCounts(heatmapParams,signal)
      const high=await api.highSegments(params,signal)
      signal.throwIfAborted()
      scope.current={cells:cells.items,high:high.items}
    }
    return {routes:routes.items,...scope.current}
  },[filters,page,scope])
  const {state,retry}=useRequest(request)
  if(state.kind==='loading')return <State kind="loading">Loading matching profiles…</State>
  if(state.kind==='error')return <State kind="error" retry={retry}>{state.message}</State>
  return <div className="profile-data"><RouteTable rows={state.data.routes} page={page} turn={turn} choose={route=>apply({...filters,route,search:''})}/>
    <ProfileHeatmap cells={state.data.cells} day={filters.day} slot={filters.slot} onSelect={(day,slot)=>apply({...filters,day,slot})}/>
    <HighProfiles rows={state.data.high}/></div>
}
export default function Operator(){
  const {state,retry}=useRequest(reports)
  const [filters,setFilters]=useState(defaults),[page,turn]=useState(0)
  function apply(next:Filters){setFilters(next);turn(0)}
  return <div className="operator">
    {state.kind==='loading' && <State kind="loading">Loading network reports…</State>}
    {state.kind==='error' && <State kind="error" retry={retry}>{state.message}</State>}
    {state.kind==='ready' && <NetworkStats overview={state.data.overview}/>}
    <FiltersForm key={JSON.stringify(filters)} filters={filters} apply={apply}/>
    <Explorer key={JSON.stringify([filters.route,filters.day])} filters={filters} page={page} turn={turn} apply={apply}/>
    {state.kind==='ready' && <div className="report-pair"><PeakReport rows={state.data.peaks.filter(r=>filters.day==='' || r.day_type===dayType(filters.day==='true'))}/><WeeklyReport rows={state.data.weeks}/></div>}
  </div>
}
