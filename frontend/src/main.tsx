import { lazy, Suspense, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Link, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { Activity, BarChart3, BusFront, ChevronRight, Info, MapPin, Moon, Route as RouteIcon, Sun } from 'lucide-react'
import '@fontsource-variable/manrope'
import './styles.css'
import { JourneyResults } from './JourneyResults'
import './journeys.css'
import { Planner } from './Planner'
import { TransitArt } from './TransitArt'
import { Card, State } from './ui'

const pages=[
  {path:'/',name:'Journey Planner',icon:RouteIcon,description:'Compare Delhi bus journeys by travel time and historical crowding.'},
  {path:'/operator',name:'Operator Dashboard',icon:BarChart3,description:'Explore historical crowding, route coverage and recorded load across Delhi’s bus network.'},
  {path:'/model',name:'Model Insights',icon:Activity,description:'Understand the evidence behind historical crowding estimates.'},
  {path:'/about',name:'About',icon:Info,description:'How CrowdRoute Delhi helps you compare scheduled bus journeys.'}
]
function Brand(){return <Link className="brand" to="/" aria-label="CrowdRoute Delhi home"><span className="brand-mark"><BusFront size={23}/></span><span>CrowdRoute <b>Delhi</b></span></Link>}
function Header(){
  const [mode,setMode]=useState(()=>document.documentElement.dataset.theme || 'light')
  function toggle(){const next=mode==='light'?'dark':'light';document.documentElement.dataset.theme=next;setMode(next);try{localStorage.setItem('crowdroute-theme',next)}catch{}}
  return <header><div className="wrap header-inner"><Brand/><nav aria-label="Main navigation">{pages.map(({path,name,icon:Icon})=><NavLink key={path} to={path} end><Icon size={17}/>{name}</NavLink>)}</nav><button className="theme" aria-label={'Switch to '+(mode==='light'?'dark':'light')+' mode'} onClick={toggle}>{mode==='light'?<Moon size={19}/>:<Sun size={19}/>}</button></div></header>
}
const Operator=lazy(()=>import('./Operator'))
const Insights=lazy(()=>import('./ModelInsights'))
const About=lazy(()=>import('./About'))
function App(){
  const {pathname}=useLocation()
  const page=pages.find(p=>p.path.toLowerCase()===(pathname.replace(/\/$/,'')||'/').toLowerCase())
  const results=pathname.replace(/\/$/,'').toLowerCase()==='/journeys'
  const home=page?.path==='/'
  const title=results?'Journey results':page?.name||'Page not found'
  useEffect(()=>{document.title=title+' · CrowdRoute Delhi';window.scrollTo(0,0)},[title])
  return <><a className="skip" href="#main">Skip to content</a><Header/><main id="main" className="wrap"><div className="crumb"><BusFront size={15}/>CrowdRoute Delhi<ChevronRight size={14}/><strong>{title}</strong></div>
    <section className="hero"><div className="hero-copy"><span className="location"><MapPin size={14}/>Delhi, India</span><h1>{home?'Plan your Delhi bus trip':title}</h1><p>{results?'Compare scheduled routes, transfer waits and historical crowding.':page?.description||'This address is outside the planner.'}</p></div><TransitArt/></section>
    <Routes><Route path="/journeys" element={<JourneyResults/>}/><Route path="/" element={<Planner/>}/><Route path="/operator" element={<Suspense fallback={<State kind="loading">Loading dashboard…</State>}><Operator/></Suspense>}/><Route path="/model" element={<Suspense fallback={<State kind="loading">Loading model insights…</State>}><Insights/></Suspense>}/><Route path="/about" element={<Suspense fallback={<State kind="loading">Loading methodology…</State>}><About/></Suspense>}/><Route path="*" element={<Card><Link to="/">Return to Journey Planner</Link></Card>}/></Routes>
  </main><footer><div className="wrap footer-inner"><Brand/><span>Travel Smarter. Travel Comfortably.</span><Link to="/about">About CrowdRoute</Link></div></footer></>
}
createRoot(document.getElementById('root')!).render(<BrowserRouter><App/></BrowserRouter>)

