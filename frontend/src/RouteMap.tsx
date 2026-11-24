import {useCallback,useEffect,useMemo,useRef,useState} from 'react'
import mapboxgl from 'mapbox-gl'
import {roadPath} from './roadPath'
import {useRequest,State} from './ui'
import {LocateFixed,Map as MapIcon,Satellite} from 'lucide-react'
import type {Journey} from './api'
import {geometry,strokes,stopRole,symbols} from './routeGeometry'
import {drawLayers} from './mapLayers'
import {useVenueMap,empty} from './venueMap'
import 'mapbox-gl/dist/mapbox-gl.css'
import './route-map.css'

const styles={Satellite:'mapbox://styles/mapbox/satellite-streets-v12',Street:'mapbox://styles/mapbox/streets-v12'}
const token=import.meta.env.VITE_MAPBOX_PUBLIC_TOKEN?.trim()
const time=new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',second:'2-digit'})
function popupText(title:string,body:string){
  const box=document.createElement('div'),heading=document.createElement('strong'),text=document.createElement('p')
  heading.textContent=title;text.textContent=body;box.className='map-readout';box.append(heading,text);return box
}
export default function RouteMap({journey}:{journey:Journey}){
  const {stops,omitted}=useMemo(()=>geometry(journey),[journey])
  const request=useCallback((signal:AbortSignal)=>roadPath(journey,signal),[journey])
  const {state,retry}=useRequest(request)
  const route=state.kind==='ready'?state.data.data:empty
  const latestRoute=useRef(route)
  const selectedStyle=useRef<keyof typeof styles>('Satellite')
  const venue=useVenueMap()
  const host=useRef<HTMLDivElement>(null),instance=useRef<mapboxgl.Map|null>(null)
  const latest=useRef(venue.data),popup=useRef<mapboxgl.Popup|null>(null)
  const [style,setStyle]=useState<keyof typeof styles>('Satellite'),[attempt,setAttempt]=useState(0)
  const [imageryNotice,setImageryNotice]=useState('')
  const [status,setStatus]=useState('Loading basemap…'),[ready,setReady]=useState<mapboxgl.Map|null>(null)
  const bounds=useMemo(()=>{const b=new mapboxgl.LngLatBounds();stops.forEach(s=>b.extend(s.position));return b},[stops])
  useEffect(()=>{
    latestRoute.current=route
    instance.current?.getSource<mapboxgl.GeoJSONSource>('journey')?.setData(route)
  },[route])
  useEffect(()=>{
    latest.current=venue.data
    const map=instance.current
    map?.getSource<mapboxgl.GeoJSONSource>('venue')?.setData(venue.data)
    popup.current?.remove()
  },[venue.data])
  useEffect(()=>{
    if(!host.current||!stops.length)return
    setReady(null);setStatus('Loading basemap…')
    if(!token?.startsWith('pk.')){setStatus('Configure VITE_MAPBOX_PUBLIC_TOKEN in frontend/.env.local.');return}
    let map:mapboxgl.Map
    try{
      map=new mapboxgl.Map({container:host.current,accessToken:token,style:styles[selectedStyle.current],bounds,
        fitBoundsOptions:{padding:38,maxZoom:17},cooperativeGestures:true})
    }catch{setStatus('Map unavailable. Check WebGL 2 support and reload.');return}
    instance.current=map
    map.addControl(new mapboxgl.NavigationControl({visualizePitch:true}),'top-right')
    map.addControl(new mapboxgl.FullscreenControl(),'top-right')
    const markers=stops.map(s=>{
      const role=stopRole(s.visits),button=document.createElement('button')
      button.type='button';button.className='route-pin '+(role==='Intermediate stop'?'intermediate':role.toLowerCase())
      button.textContent=symbols[role];button.setAttribute('aria-label',role+' · '+s.visits[0].stop.stop_name)
      const content=document.createElement('div')
      for(const v of s.visits)content.append(popupText(v.role+' · '+v.stop.stop_name,'Leg '+v.leg+' · '+v.route+' · #'+v.stop.stop_id+' · '+time.format(new Date(v.stop.scheduled_departure_at))+' IST'))
      return new mapboxgl.Marker({element:button}).setLngLat(s.position).setPopup(new mapboxgl.Popup({maxWidth:'300px'}).setDOMContent(content)).addTo(map)
    })
    map.on('click',e=>{
      const layers=['venue-points','evacuation','risk-zones','bus-route'].filter(id=>map.getLayer(id))
      if(!layers.length)return
      const f=map.queryRenderedFeatures(e.point,{layers}).sort((a,b)=>layers.indexOf(a.layer!.id)-layers.indexOf(b.layer!.id))[0]
      if(!f)return
      const p=f.properties
      if(!p)return
      const detail=p.kind==='zone'?p.count+' people · '+p.density+' people/m² · '+p.risk+' risk':p.detail ??
        ({entry:'Entry gate',exit:'Exit gate',camera:'Camera location',evacuation:'Operator-approved evacuation path'} as Record<string,string>)[p.kind]
      popup.current?.remove()
      popup.current=new mapboxgl.Popup().setLngLat(e.lngLat).setDOMContent(popupText(p.name,detail)).addTo(map)
    })
    map.on('style.load',()=>{drawLayers(map,latestRoute.current,latest.current);setReady(map);setStatus(s=>s==='Loading basemap…'?'':s)})
    let failed=false
    map.on('styledataloading',()=>{failed=false})
    map.on('idle',()=>{if(!failed)setStatus('')})
    map.on('error',event=>{
      failed=true
      const code=(event.error as Error & {status?:number}).status
      const url=(event.error as Error & {url?:string}).url || ''
      if(selectedStyle.current==='Satellite' && (url.includes('/mapbox.satellite/') || ('sourceId' in event && String(event.sourceId).includes('satellite')))){
        selectedStyle.current='Street'
        setStyle('Street')
        setImageryNotice(code===429?'Mapbox is rate-limiting satellite tiles (HTTP 429). Showing streets. Select Satellite to retry later.':'Satellite imagery could not load. Showing streets. Select Satellite to retry.')
        queueMicrotask(()=>{if(instance.current===map && selectedStyle.current==='Street')map.setStyle(styles.Street,{diff:false,localFontFamily:undefined,localIdeographFontFamily:undefined})})
        return
      }
      setStatus(code===401||code===403?'Mapbox denied access. Check the public token and allowed origin.':'Basemap or tiles unavailable. Check network access and retry.')
    })
    const timer=setTimeout(()=>setStatus(s=>s==='Loading basemap…'?'Basemap is taking longer than expected. Check the connection or retry.':s),20000)
    const observer=new ResizeObserver(()=>map.resize());observer.observe(host.current)
    return ()=>{clearTimeout(timer);observer.disconnect();popup.current?.remove();markers.forEach(m=>m.remove());instance.current=null;map.remove()}
  },[bounds,stops,attempt])
  function switchStyle(key:keyof typeof styles){
    if(selectedStyle.current===key)return
    setImageryNotice('')
    selectedStyle.current=key
    setStyle(key);setStatus('Loading basemap…')
    instance.current?.setStyle(styles[key],{diff:false,localFontFamily:undefined,localIdeographFontFamily:undefined})
  }
  if(!stops.length)return <p role="status">Stop coordinates are unavailable for this journey.</p>
  return <section className="route-map" aria-label="Selected journey map"><div className="map-heading"><div><h3>Route map</h3></div>
    <button className="edit-search" disabled={!ready} onClick={()=>instance.current?.fitBounds(bounds,{padding:38,maxZoom:17,duration:350})}><LocateFixed size={16}/>Fit route</button></div>
    <div className="map-switch" aria-label="Basemap">{(['Satellite','Street'] as const).map(key=><button key={key} aria-pressed={key===style} onClick={()=>switchStyle(key)}>{key==='Satellite'?<Satellite size={15}/>:<MapIcon size={15}/>}{key}</button>)}</div>
    {state.kind==='ready'?<p className="map-status">{state.data.distance>0 && 'Road distance · '+(state.data.distance/1000).toFixed(2)+' km　'}Scheduled journey · {Math.round(journey.total_duration_seconds/60)} min</p>:state.kind==='error'?<State kind="error" retry={retry}>{state.message}</State>:<State kind="loading">Finding route through scheduled stops…</State>}
    <div ref={host} className="map-canvas" aria-label="Interactive journey map"/>
    {imageryNotice && <p className="map-status" role="status">{imageryNotice}</p>}
    {status && <p className="map-status" role="status">{status} {status!=='Loading basemap…' && <button onClick={()=>setAttempt(n=>n+1)}>Retry map</button>}</p>}
    {omitted>0 && <p className="map-status">Coordinates unavailable for {omitted} scheduled stop visits.</p>}
    <div className="map-legend"><strong>Historical crowding</strong>{Object.entries(strokes).map(([level,color])=><span key={level}><i style={{background:color}}/>{level}</span>)}</div>
    <p className="map-symbols">S · Source　 D · Destination　 {journey.transfers>0 && 'T · Transfer　'}● · Intermediate stop</p>
    {Boolean(import.meta.env.VITE_VENUE_MAP_FEED) && <p className="map-status" role="status">{venue.message}</p>}
    {venue.data!==empty && venue.data.features.length>0 && <div className="map-legend"><strong>Venue layers</strong>{[['#40bb74','Low risk'],['#edc531','Moderate risk'],['#f0524f','High risk'],['#157751','Entry'],['#9f482a','Exit'],['#6544ae','Camera'],['#19c8db','Evacuation path']].map(([color,label])=><span key={label}><i style={{background:color}}/>{label}</span>)}<span>Heat intensity · relative spatial density</span></div>}
  </section>
}
