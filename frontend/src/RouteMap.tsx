import { useEffect, useMemo, useState } from 'react'
import { divIcon, latLngBounds, type LatLngTuple } from 'leaflet'
import { MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from 'react-leaflet'
import { LocateFixed } from 'lucide-react'
import { type CrowdingLevel, type Journey, type JourneyLeg } from './api'
import 'leaflet/dist/leaflet.css'
import './route-map.css'

const strokes:Record<CrowdingLevel,string> = {Low:'#16834e', Moderate:'#be7908', High:'#c43c38', 'Insufficient Data':'#687585'}
const symbols = {Source:'S',Destination:'D',Transfer:'T','Intermediate stop':'•'}
type Role = keyof typeof symbols
type StopEvent = JourneyLeg['stops'][number]
interface Visit { stop:StopEvent; role:Role; route:string; leg:number }
interface MapStop {position:LatLngTuple; visits:Visit[]}
interface MapSegment { key:string; positions:LatLngTuple[]; from:string; to:string; route:string; evidence:JourneyLeg['segments'][number]['crowding'] }

function position(stop:StopEvent):LatLngTuple|null {
  const {latitude,longitude}=stop
  if(!Number.isFinite(latitude)||!Number.isFinite(longitude)||Math.abs(latitude)>90||Math.abs(longitude)>180) return null
  return [latitude,longitude]
}
function geometry(journey:Journey) {
  const stops=new Map<string,MapStop>()
  const segments:MapSegment[]=[]
  let omitted=0
  journey.legs.forEach((leg,legIndex)=>{
    const route=leg.route_name || leg.route_id
    const bySequence=new Map(leg.stops.map(s=>[s.stop_sequence,s]))
    leg.stops.forEach((stop,index)=>{
      const point=position(stop)
      if(!point){omitted++;return}
      let role:Role='Intermediate stop'
      if(index===0) role=legIndex===0?'Source':'Transfer'
      else if(index===leg.stops.length-1) role=legIndex===journey.legs.length-1?'Destination':'Transfer'
      const key=point.join(',')
      const group=stops.get(key) ?? {position:point,visits:[]}
      group.visits.push({stop,role,route,leg:legIndex+1})
      stops.set(key,group)
    })
    for(const segment of leg.segments){
      const from=bySequence.get(segment.from_stop_sequence),to=bySequence.get(segment.to_stop_sequence)
      if(!from||!to)continue
      const a=position(from),b=position(to)
      if(a&&b) segments.push({key:legIndex+'-'+from.stop_sequence,positions:[a,b],from:from.stop_name,to:to.stop_name,route,evidence:segment.crowding})
    }
  })
  return {stops:[...stops.values()],segments,omitted}
}
function FitRoute({points}:{points:LatLngTuple[]}) {
  const map=useMap()
  useEffect(()=>{
    const fit=()=>{map.invalidateSize({pan:false});map.fitBounds(latLngBounds(points),{padding:[30,30],maxZoom:17,animate:false})}
    fit()
    const observer=new ResizeObserver(fit)
    observer.observe(map.getContainer())
    return ()=>observer.disconnect()
  },[map,points])
  return null
}
function stopRole(visits:Visit[]):Role {
  for(const role of ['Transfer','Source','Destination'] as const) if(visits.some(v=>v.role===role))return role
  return 'Intermediate stop'
}
const icons=Object.fromEntries((Object.keys(symbols) as Role[]).map(role=>{
  const small=role==='Intermediate stop'
  const size=small?16:28
  return [role,divIcon({className:'route-pin '+(small?'intermediate':role.toLowerCase()),html:symbols[role],iconSize:[size,size],iconAnchor:[size/2,size/2]})]
}))
const localTime=new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',second:'2-digit'})

export default function RouteMap({journey}:{journey:Journey}) {
  const {stops,segments,omitted}=useMemo(()=>geometry(journey),[journey])
  const points=useMemo(()=>stops.map(s=>s.position),[stops])
  const [failed,setFailed]=useState(false)
  const [attempt,setAttempt]=useState(0)
  const [fitKey,setFitKey]=useState(0)
  if(!points.length)return <p role="status">Stop coordinates are unavailable for this journey.</p>
  return <section className="route-map" aria-label="Selected journey map">
    <div className="map-heading"><div><h3>Route map</h3><p>Approximate route visualization connecting scheduled GTFS stops. Lines show historical relative crowding.</p></div>
      <button type="button" className="edit-search" onClick={()=>setFitKey(n=>n+1)}><LocateFixed size={16}/>Fit route</button></div>
    <MapContainer className="map-canvas" center={points[0]} zoom={14} maxZoom={19} scrollWheelZoom={false}>
      <FitRoute key={fitKey} points={points}/>
      <TileLayer key={attempt} url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19}
        attribution={'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'}
        eventHandlers={{tileerror:()=>setFailed(true)}}/>
      {segments.map(s=><Polyline key={s.key} positions={s.positions} pathOptions={{color:strokes[s.evidence.crowding_level],weight:7,opacity:0.95}}>
        <Popup><strong>{s.from} → {s.to}</strong><p>{s.route}</p><p>Historical crowding · {s.evidence.crowding_level}<br/>{s.evidence.data_support ?? 'Missing'} data support</p></Popup>
      </Polyline>)}
      {stops.map(({position:point,visits})=>{
        const role=stopRole(visits)
        const label=role+' · '+visits[0].stop.stop_name
        return <Marker key={point.join(',')} position={point} icon={icons[role]} title={label} alt={label} zIndexOffset={role==='Intermediate stop'?0:300}>
          <Popup><div className="map-visits">{visits.map(v=><div key={v.leg+'-'+v.stop.stop_sequence}>
            <strong>{v.role} · {v.stop.stop_name}</strong><p>Leg {v.leg} · {v.route}<br/>Stop #{v.stop.stop_id} · {localTime.format(new Date(v.stop.scheduled_departure_at))} IST</p></div>)}</div></Popup>
        </Marker>
      })}
    </MapContainer>
    {failed && <div className="map-status" role="status">Some street map tiles are unavailable. Stops and route segments remain visible. <button type="button" onClick={()=>{setFailed(false);setAttempt(n=>n+1)}}>Retry tiles</button></div>}
    {omitted>0 && <p role="status">Some stops have unavailable coordinates. Only segments with both endpoints are drawn.</p>}
    <div className="map-legend" aria-label="Historical crowding legend"><strong>Historical crowding</strong>{(Object.keys(strokes) as CrowdingLevel[]).map(level=><span key={level}><i style={{background:strokes[level]}}/>{level}</span>)}</div>
    <div className="map-symbols">S · Source　 D · Destination　 {journey.transfers>0 && 'T · Transfer　 '}● · Intermediate stop</div>
  </section>
}
