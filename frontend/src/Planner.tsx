import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ArrowUpDown, Armchair, BusFront, CircleDot, Clock3, GitFork, LocateFixed, MapPin, Route, Search, SlidersHorizontal, Timer } from 'lucide-react'
import { api, type JourneyQuery, type Preference, type Stop } from './api'
import { Button, Card, Field, State, useRequest } from './ui'

function Matches({text,choose}: {text:string;choose:(s:Stop)=>void}) {
  const request=useCallback(async (signal:AbortSignal)=>{
    await new Promise(resolve=>setTimeout(resolve,250))
    signal.throwIfAborted()
    return api.stops(text,signal)
  },[text])
  const {state,retry}=useRequest(request)
  return <div className="matches" onMouseDown={e=>e.preventDefault()}>{state.kind==='loading'?<State kind="loading">Searching stops…</State>:state.kind==='error'?<State kind="error" retry={retry}>{state.message}</State>:state.data.items.length===0?<State kind="empty">No stops match this name.</State>:state.data.items.map(s=><button type="button" key={s.stop_id} onClick={()=>choose(s)}><MapPin size={16}/><span>{s.stop_name}</span><small>#{s.stop_id}</small></button>)}</div>
}
function StopField({origin,stop,onSelect}: {origin?:boolean;stop:Stop|null;onSelect:(s:Stop|null)=>void}) {
  const [text,setText]=useState(''),[open,setOpen]=useState(false)
  const id=origin?'origin':'destination', Icon=origin?CircleDot:MapPin
  return <Field id={id} label={origin?'From':'To'}><div className="stop" onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))setOpen(false)}} onKeyDown={e=>{if(e.key==='Escape'){setOpen(false);e.currentTarget.querySelector('input')?.focus()}
      if(e.key==='ArrowDown'||e.key==='ArrowUp'){
        const options=Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>('.matches button'))
        if(options.length){e.preventDefault();const index=options.indexOf(document.activeElement as HTMLButtonElement)
          options[e.key==='ArrowDown'?(index+1)%options.length:(index<=0?options.length-1:index-1)].focus()}
      }}}>
    <div className="input-icon"><Icon size={18}/><input id={id} required autoComplete="off" maxLength={256} placeholder={origin?'Search starting stop':'Search destination stop'} value={stop?.stop_name ?? text}
      onFocus={()=>setOpen(true)} onChange={e=>{setText(e.target.value);onSelect(null);setOpen(true)}}/></div>
    {open && !stop && text.trim() && <Matches key={text.trim()} text={text.trim()} choose={s=>{setText('');onSelect(s);setOpen(false)}}/>}
  </div></Field>
}
const choices=[{key:'balanced',title:'Balanced',icon:SlidersHorizontal},{key:'fastest',title:'Fastest',icon:Timer},{key:'comfortable',title:'Comfortable',icon:Armchair}] as const
export interface SearchDraft {origin:Stop; destination:Stop; query:JourneyQuery}
let lastSearch: SearchDraft | undefined
export function Planner(){
  const navigate=useNavigate()
  const draft:SearchDraft | undefined=useLocation().state?.draft || lastSearch
  const [origin,setOrigin]=useState<Stop|null>(draft?.origin ?? null),[destination,setDestination]=useState<Stop|null>(draft?.destination ?? null)
  const [version,setVersion]=useState(0),[pref,setPref]=useState<Preference>(draft?.query.preference ?? 'balanced')
  const [error,setError]=useState('')
  const [now]=useState(()=>new Date())
  const [date,setDate]=useState(()=>draft?.query.travel_date ?? new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Kolkata'}).format(now))
  const [departure,setDeparture]=useState(()=>draft?.query.departure_time ?? new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Kolkata',hour:'2-digit',minute:'2-digit'}).format(now))
  useEffect(()=>{setError('')},[origin,destination,date,departure,pref])
  function submit(e:FormEvent){
    e.preventDefault()
    if(!origin||!destination || origin.stop_id===destination.stop_id){
      setError(!origin||!destination?'Choose both stops from the search suggestions.':'Choose two different stops.');return
    }
    const query = {source_stop_id:origin.stop_id,destination_stop_id:destination.stop_id,travel_date:date,departure_time:departure,preference:pref}
    lastSearch = {origin,destination,query}
    navigate('/journeys?' + new URLSearchParams(query), {state:{draft:lastSearch}})
  }
  return <div className="planner-grid"><Card><div className="card-heading"><span className="tile"><Route/></span><div><h2>Plan your journey</h2></div></div>
    <form onSubmit={submit}><div className="stop-row"><StopField key={'a'+version} origin stop={origin} onSelect={setOrigin}/><button className="swap" type="button" aria-label="Swap stops" title="Swap stops" disabled={!origin && !destination} onClick={()=>{setOrigin(destination);setDestination(origin);setVersion(v=>v+1)}}><ArrowUpDown size={17}/></button><StopField key={'b'+version} stop={destination} onSelect={setDestination}/></div>
    <div className="two-fields"><Field label="Travel date" id="date"><input type="date" min="1900-01-01" max="2100-12-31" id="date" required value={date} onChange={e=>setDate(e.target.value)}/></Field><Field label="Departure time (IST)" id="time"><input type="time" id="time" required value={departure} onChange={e=>setDeparture(e.target.value)}/></Field></div>
    <fieldset><legend>Journey preference</legend><div className="preferences">{choices.map(({key,title,icon:Icon})=><label key={key}><input type="radio" name="preference" value={key} checked={pref===key} onChange={()=>setPref(key)}/><span><Icon size={16}/>{title}</span></label>)}</div></fieldset>
    {error && <State kind="error">{error}</State>}<Button type="submit"><Search size={18}/>Find journeys</Button></form>
    <div className="example-trip"><h3>Try a scheduled journey</h3><Link to="/journeys?source_stop_id=3619&destination_stop_id=3621&travel_date=2026-11-20&departure_time=08%3A45%3A23&preference=balanced">Compare C4E Janakpuri → C4H Janakpuri</Link><small>20 Nov 2026 · 08:45:23 IST</small></div>
    </Card>
    <aside><Card className="guide"><div className="guide-title"><span className="tile aqua"><LocateFixed/></span><h2>Choosing a preference</h2></div>
    <Guide icon={MapPin} title="Fastest" copy="Minimizes total travel and waiting time."/>
    <Guide icon={Clock3} title="Comfortable" copy="Prioritizes lower historical crowding."/>
    <Guide icon={GitFork} title="Balanced" copy="Optimizes time, crowding, and transfers."/>
    </Card></aside></div>
}
function Guide({icon:Icon,title,copy}:{icon:typeof MapPin;title:string;copy:string}){
  return <div className="guide-row"><Icon size={18}/><div><h3>{title}</h3><p>{copy}</p></div></div>
}
