import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity, ArrowUpRight, BusFront, ChartColumn, CircleAlert, Layers3, MapPinned, Route, UsersRound } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, type CrowdingLevel, type SlotCounts } from './api'
import { Card, State, useRequest } from './ui'
import { TransitArt } from './TransitArt'
import { startTime, format } from './OperatorCharts'
import './operator.css'

const levels: {name:CrowdingLevel;color:string}[]=[
  {name:'Low',color:'#29946c'},{name:'Moderate',color:'#e7a531'},
  {name:'High',color:'#df615a'},{name:'Insufficient Data',color:'#a4adbd'}
]
async function readOverview(signal:AbortSignal){
  const network=await api.overview(signal)
  const slots=await api.slotCounts({},signal)
  return {network, slots:slots.items}
}
const days=['Weekday','Weekend'] as const
function CrowdingChart({slots}:{slots:SlotCounts[]}){
  const [day,setDay]=useState<typeof days[number]>('Weekday')
  const rows=Array.from({length:48},(_,i)=>{
    const cell=slots.find(r=>r.time_slot===i && r.is_weekend===(day==='Weekend'))
    return {time:startTime(i),share:cell?.segment_profiles?Number((100*cell.high_crowding_segments/cell.segment_profiles).toFixed(2)):null}
  })
  return <Card className="trend"><div className="panel-title"><span className="mini-icon"><Activity size={18}/></span><h2>Crowding by time of day</h2></div>
    
    <div className="trend-tools"><span className="series-key"><i/>High crowding</span><div className="segmented" aria-label="Day type">{days.map(d=><button key={d} aria-pressed={d===day} onClick={()=>setDay(d)}>{d}</button>)}</div></div>
    {rows.every(r=>r.share===null)?<State kind="empty">No profiles for this day type.</State>:<div className="trend-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={rows} margin={{top:8,left:0,right:12,bottom:2}}>
      <CartesianGrid vertical={false} stroke="var(--line)" strokeDasharray="3 4"/><XAxis dataKey="time" ticks={['00:00','04:00','08:00','12:00','16:00','20:00']} tickLine={false} axisLine={false} tickMargin={10} minTickGap={16}/>
      <YAxis width={42} tickFormatter={v=>v+'%'} tickLine={false} axisLine={false}/><Tooltip contentStyle={{background:'var(--panel)',border:'1px solid var(--line)',borderRadius:8}} labelFormatter={v=>v+' IST'} formatter={value=>[value+'%','High crowding']}/>
      <Area type="linear" dataKey="share" stroke="#3c56eb" strokeWidth={2.6} fill="#536bf0" fillOpacity={0.12} isAnimationActive={false}/></AreaChart></ResponsiveContainer></div>}
  </Card>
}
export default function Overview(){
  const {state,retry}=useRequest(readOverview)
  return <div className="overview"><section className="network-banner"><div className="banner-copy"><span><MapPinned size={15}/> Delhi transit network</span>
    <h2>Plan a Delhi bus journey</h2><Link to="/planner">Open journey planner <ArrowUpRight size={15}/></Link></div><TransitArt/></section>
    {state.kind==='loading'?<State kind="loading">Loading network coverage and crowding profiles…</State>:state.kind==='error'?<State kind="error" retry={retry}>{state.message}</State>:<>
      <div className="kpi-strip">{[
        {title:'Scheduled routes',value:state.data.network.routes,icon:Route,color:'blue',caption:'Published bus routes'},
        {title:'Network stops',value:state.data.network.stops,icon:BusFront,color:'purple',caption:'Stops in the timetable'},
        {title:'Crowding profiles',value:state.data.network.profiles,icon:Layers3,color:'teal',caption:'Historical segment profiles'},
        {title:'High crowding',value:state.data.network.classifications.High,icon:UsersRound,color:'orange',caption:'High relative crowding profiles'}
      ].map(({title,value,icon:Icon,color,caption})=><Card key={title} className="stat"><div><span>{title}</span><i className={'stat-icon '+color}><Icon size={18}/></i></div><strong>{format(value)}</strong><small>{caption}</small></Card>)}</div>
      <div className="overview-charts"><CrowdingChart slots={state.data.slots}/><Card className="breakdown"><div className="panel-title"><span className="mini-icon"><ChartColumn size={18}/></span><h2>Crowding distribution</h2></div>
        {state.data.network.profiles===0?<State kind="empty">No crowding profiles available.</State>:<><div className="share-bar" aria-hidden="true">{levels.map(l=><i key={l.name} style={{flexGrow:state.data.network.classifications[l.name],background:l.color}}/>)}</div>
        <ul>{levels.map(l=><li key={l.name}><i style={{background:l.color}}/><span>{l.name}</span><strong>{format(state.data.network.classifications[l.name])}</strong><small>{(100*state.data.network.classifications[l.name]/state.data.network.profiles).toFixed(1)}%</small></li>)}</ul></>}
        </Card></div></>}
    
  </div>
}
