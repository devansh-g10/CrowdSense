import type {Map as GLMap, GeoJSONSource} from 'mapbox-gl'
import type {FeatureCollection} from 'geojson'

export function drawLayers(map:GLMap,route:FeatureCollection,venue:FeatureCollection){
  for(const [id,data] of [['journey',route],['venue',venue]] as const){
    const source=map.getSource<GeoJSONSource>(id)
    if(source)source.setData(data)
    else map.addSource(id,{type:'geojson',data})
  }
  if(map.getLayer('bus-route'))return
  map.addLayer({id:'risk-zones',type:'fill',source:'venue',filter:['==',['get','kind'],'zone'],paint:{
    'fill-color':['match',['get','risk'],'low','#40bb74','moderate','#edc531','high','#f0524f','#828a98'],'fill-opacity':0.5}})
  map.addLayer({id:'crowd-density',type:'heatmap',source:'venue',filter:['==',['get','kind'],'detection'],paint:{
    'heatmap-weight':['get','density'],'heatmap-radius':24,'heatmap-opacity':0.7,
    'heatmap-color':['interpolate',['linear'],['heatmap-density'],0,'rgba(0,0,0,0)',0.2,'#53bf88',0.55,'#f3d94e',1,'#ea524a']}})
  map.addLayer({id:'route-outline',type:'line',source:'journey',paint:{'line-color':'#fff','line-width':8,'line-opacity':0.85}})
  map.addLayer({id:'bus-route',type:'line',source:'journey',paint:{'line-color':['get','color'],'line-width':5}})
  map.addLayer({id:'evacuation',type:'line',source:'venue',filter:['==',['get','kind'],'evacuation'],paint:{
    'line-color':'#19c8db','line-width':5,'line-dasharray':[2,1]}})
  map.addLayer({id:'venue-points',type:'circle',source:'venue',filter:['in',['get','kind'],['literal',['entry','exit','camera']]],paint:{
    'circle-color':['match',['get','kind'],'entry','#157751','exit','#9f482a','#6544ae'],'circle-radius':8,'circle-stroke-color':'#fff','circle-stroke-width':2}})
}
