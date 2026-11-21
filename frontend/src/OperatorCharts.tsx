import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card, State } from './ui'
import type { Overview, Peak, SlotCounts, Week } from './api'

export const format=(n:number)=>n.toLocaleString('en-IN')
const share=(n:number,total:number)=>total ? (100*n/total).toFixed(1)+'%' : 'Unavailable'
export const startTime=(slot:number)=>String(Math.floor(slot/2)).padStart(2,'0')+':'+(slot%2?'30':'00')
export const dayType=(weekend:boolean)=>weekend?'Weekend':'Weekday'
const palette={Low:'#21825b',Moderate:'#bc820c',High:'#c24d49','Insufficient Data':'#718296'} as const
const tooltip={backgroundColor:'var(--panel)',border:'1px solid var(--line)',borderRadius:8,color:'var(--ink)'}
export function NetworkStats({overview:o}:{overview:Overview}){
  const rows=(Object.keys(palette) as (keyof typeof palette)[]).map(name=>({name,value:o.classifications[name] ?? 0,fill:palette[name]}))
  const unknown=o.classifications['Insufficient Data'] ?? 0
  const stats=[
    ['Prediction profiles',format(o.profiles),'Across the model export'],
    ['Covered routes',format(o.routes_with_profiles),'Of '+format(o.routes)+' scheduled routes'],
    ['Reliable classification',share(o.profiles-unknown,o.profiles),format(o.profiles-unknown)+' Low, Moderate or High profiles'],
    ['Insufficient data',share(unknown,o.profiles),format(unknown)+' profiles with limited evidence']
  ]
  return <><div className="operator-kpis">{stats.map(([label,value,caption])=><div key={label}><h3>{label}</h3><strong>{value}</strong><p>{caption}</p></div>)}</div>
    <Card><h2>Relative crowding distribution</h2><p className="chart-caption">Network-wide share of all {format(o.profiles)} exported segment profiles. Historical classifications describe relative crowding.</p>
    <div className="distribution"><div className="donut"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={rows} dataKey="value" nameKey="name" innerRadius="58%" outerRadius="88%" isAnimationActive={false}/><Tooltip contentStyle={tooltip}/></PieChart></ResponsiveContainer></div>
    <ul>{rows.map(row=><li key={row.name}><i style={{background:row.fill}}/>{row.name}<strong>{share(row.value,o.profiles)}</strong><span>{format(row.value)} profiles</span></li>)}</ul></div></Card></>
}
export function PeakReport({rows}:{rows:Peak[]}) {
  const peaks=rows.filter(r=>r.period!=='Other Hours')
  const days=Array.from(new Set(peaks.map(r=>r.day_type)))
  const grouped=(['Morning Peak','Evening Peak'] as const).map(period=>({period,
    ...Object.fromEntries(days.map(day=>[day,peaks.find(r=>r.day_type===day && r.period===period)?.average_load ?? null]))}))
  return <Card><h2>Morning and evening peaks</h2><p className="chart-caption">Network report by day type. Each mean uses the recorded segment observations for that period across all routes and slots in the period.</p>
    {peaks.length===0?<State kind="empty">No peak observations available.</State>:<>
    <div className="operator-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={grouped}><CartesianGrid vertical={false} stroke="var(--line)"/><XAxis dataKey="period"/><YAxis width={36}/><Tooltip contentStyle={tooltip}/><Legend/>{days.map(d=><Bar key={d} dataKey={d} fill={d==='Weekday'?'#3268b0':'#198079'} radius={[5,5,0,0]} isAnimationActive={false}/>)}</BarChart></ResponsiveContainer></div>
    <details><summary>Peak means and observation counts</summary>{peaks.map(r=><p key={r.day_type+r.period}>{r.day_type} · {r.period} · mean {r.average_load} from {format(r.segment_observations)} observations</p>)}</details></>}</Card>
}
export function WeeklyReport({rows}:{rows:Week[]}) {
  return <Card><h2>Weekly passenger load consistency</h2><p className="chart-caption">Network-wide reconstructed load per recorded segment observation. Each week uses its own observations and observed days. Covers all routes and day types.</p>
    {!rows.length?<State kind="empty">Weekly observations unavailable.</State>:<>
    <div className="operator-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={rows}><CartesianGrid vertical={false} stroke="var(--line)"/><XAxis dataKey="week_number" tickFormatter={v=>'W'+v}/><YAxis width={36}/><Tooltip contentStyle={tooltip} labelFormatter={v=>'Week '+v}/><Legend/>
      <Line dataKey="average_recorded_load" name="Mean" stroke="#3268b0" strokeWidth={3} isAnimationActive={false}/><Line dataKey="median_recorded_load" name="Median" stroke="#198079" strokeDasharray="4 3" isAnimationActive={false}/><Line dataKey="p90_recorded_load" name="90th percentile" stroke="#ae7620" strokeDasharray="6 2" isAnimationActive={false}/>
    </LineChart></ResponsiveContainer></div><details><summary>Weekly values and observation counts</summary>{rows.map(r=><p key={r.week_number}>Week {r.week_number} · {format(r.segment_observations)} observations across {r.observed_days} days · Mean {r.average_recorded_load}, median {r.median_recorded_load}, 90th percentile {r.p90_recorded_load}</p>)}</details></>}</Card>
}
export function ProfileHeatmap({cells,day,slot,onSelect}:{cells:SlotCounts[];day:string;slot:string;onSelect:(day:string,slot:string)=>void}){
  const slots=slot===''?Array.from({length:48},(_,i)=>i):[Number(slot)]
  const days=day===''?[false,true]:[day==='true']
  return <Card><h2>Time-of-day crowding heatmap</h2><p className="chart-caption">High relative crowding profiles ÷ all profiles in each 30-minute IST slot, including Insufficient Data. Select a cell to filter the explorer.</p>
    <div className="heat-key"><span>High share</span>{['0%','>0–5%','>5–20%','>20%','No profiles'].map((v,i)=><span key={v}><i className={'heat-'+i}/>{v}</span>)}</div>
    {days.map(d=><div className="heat-day" key={String(d)}><h3>{dayType(d)}</h3><div className="heat-grid">{slots.map(i=>{
      const c=cells.find(r=>r.is_weekend===d && r.time_slot===i)
      const ratio=c?.segment_profiles?c.high_crowding_segments/c.segment_profiles:null
      const bin=ratio===null?4:ratio===0?0:ratio<=0.05?1:ratio<=0.2?2:3
      const label=c?c.high_crowding_segments+' High / '+c.segment_profiles+' profiles':'No profiles'
      return <button type="button" key={i} className={'heat-'+bin} title={label} aria-label={dayType(d)+' '+startTime(i)+' · '+label} onClick={()=>onSelect(String(d),String(i))}>{startTime(i)}</button>
    })}</div></div>)}
    <h3 className="day-comparison">Weekday and weekend coverage</h3><p className="chart-caption">Reliable classifications ÷ all profiles for the selected route and time window, grouped by day type.</p>
    {days.map(d=>{const group=cells.filter(r=>r.is_weekend===d),total=group.reduce((n,r)=>n+r.segment_profiles,0),missing=group.reduce((n,r)=>n+r.insufficient_data_segments,0)
      return <p key={String(d)}>{dayType(d)} · {total?share(total-missing,total)+' reliable ('+format(total-missing)+' / '+format(total)+')':'No matching profiles'}</p>})}</Card>
}
