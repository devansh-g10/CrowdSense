import type { CrowdingLevel, Journey, JourneyLeg } from './api'
export const strokes:Record<CrowdingLevel|'Critical',string> = {Low:'#16834e', Moderate:'#e0b526', High:'#ed8322', Critical:'#ce3737', 'Insufficient Data':'#687585'}
export const symbols = {Source:'S',Destination:'D',Transfer:'T','Intermediate stop':'•'}
type Role = keyof typeof symbols
type StopEvent = JourneyLeg['stops'][number]
interface Visit { stop:StopEvent; role:Role; route:string; leg:number }
interface MapStop {position:[number,number]; visits:Visit[]}
export function position(stop:StopEvent):[number,number]|null {
  const {latitude,longitude}=stop
  if(!Number.isFinite(latitude)||!Number.isFinite(longitude)||Math.abs(latitude)>90||Math.abs(longitude)>180) return null
  return [longitude,latitude]
}
export function geometry(journey:Journey) {
  const stops=new Map<string,MapStop>()

  let omitted=0
  journey.legs.forEach((leg,legIndex)=>{
    const route=leg.route_name || leg.route_id

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
  })
  return {stops:[...stops.values()],omitted}
}
export function stopRole(visits:Visit[]):Role {
  for(const role of ['Transfer','Source','Destination'] as const) if(visits.some(v=>v.role===role))return role
  return 'Intermediate stop'
}
