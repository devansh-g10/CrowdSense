import {useEffect, useState} from 'react'
import type {Feature, FeatureCollection, Geometry} from 'geojson'

export const empty:FeatureCollection={type:'FeatureCollection',features:[]}
const maxAge=60000
const nonnegative=(v:unknown)=>typeof v==='number' && Number.isFinite(v) && v>=0
export function coordinate(p:unknown):p is [number,number] {
  return Array.isArray(p) && p.length===2 && p.every(Number.isFinite) && Math.abs(p[0])<=180 && Math.abs(p[1])<=90
}
function ring(v:unknown){
  if(!Array.isArray(v)||v.length<4||!v.every(coordinate))return false
  const first=v[0],last=v[v.length-1]
  return first[0]===last[0] && first[1]===last[1]
}
function validFeature(f:Feature<Geometry>){
  const p=f?.properties,g=f?.geometry
  if(f?.type!=='Feature'||!g||!p||typeof p.name!=='string'||!p.name.trim())return false
  switch(p.kind){
    case 'zone':return g.type==='Polygon' && g.coordinates.length>0 && g.coordinates.every(ring) &&
      Number.isInteger(p.count) && nonnegative(p.count) && nonnegative(p.density) && ['low','moderate','high'].includes(p.risk)
    case 'detection':return g.type==='Point' && coordinate(g.coordinates) && nonnegative(p.density)
    case 'entry':case 'exit':case 'camera':return g.type==='Point' && coordinate(g.coordinates)
    case 'evacuation':return g.type==='LineString' && g.coordinates.length>=2 && g.coordinates.every(coordinate) && p.approved===true
    default:return false
  }
}
export function snapshot(value:unknown,now=Date.now()){
  const data=value as FeatureCollection & {observed_at?:string}
  if(data?.type!=='FeatureCollection'||!Array.isArray(data.features)||typeof data.observed_at!=='string'||
    !/(Z|[+-]\d\d:\d\d)$/.test(data.observed_at))throw Error('Invalid venue snapshot or timestamp.')
  const time=Date.parse(data.observed_at)
  if(!Number.isFinite(time)||time>now||now-time>=maxAge)throw Error('Venue observations are stale or have an invalid time.')
  if(!data.features.every(validFeature))throw Error('Venue geometry or measurements are invalid. Check the feed configuration.')
  return {data,time}
}
export function useVenueMap(){
  const url=import.meta.env.VITE_VENUE_MAP_FEED?.trim()
  const [state,setState]=useState({data:empty,message:url?'Connecting to venue feed…':'Live venue layers require a georeferenced detection feed.'})
  useEffect(()=>{
    if(!url)return
    let stopped=false,timer:ReturnType<typeof setTimeout>,expiry:ReturnType<typeof setTimeout>
    const controller=new AbortController()
    async function poll(){
      try{
        const target=new URL(url,location.origin)
        if(target.origin!==location.origin)throw Error('Configure a same-origin venue feed.')
        const response=await fetch(target,{cache:'no-store',signal:AbortSignal.any([controller.signal,AbortSignal.timeout(10000)]),headers:{Accept:'application/geo+json, application/json'}})
        if(!response.ok)throw Error('Venue feed unavailable.')
        const {data,time}=snapshot(await response.json())
        if(stopped)return
        clearTimeout(expiry)
        setState({data,message:data.features.length?'Venue observations · '+new Date(time).toLocaleTimeString('en-GB',{timeZone:'Asia/Kolkata'})+' IST':'No venue observations in the latest snapshot.'})
        expiry=setTimeout(()=>setState({data:empty,message:'Venue observations expired. Waiting for an update.'}),Math.max(0,time+maxAge-Date.now()))
      }catch(e){
        if(!stopped){clearTimeout(expiry);setState({data:empty,message:e instanceof Error && e.constructor===Error?e.message:'Venue feed unavailable or unreadable.'})}
      }finally{if(!stopped)timer=setTimeout(poll,10000)}
    }
    poll()
    return ()=>{stopped=true;controller.abort();clearTimeout(timer);clearTimeout(expiry)}
  },[url])
  return state
}
