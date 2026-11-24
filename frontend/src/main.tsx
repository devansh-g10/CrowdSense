import { lazy, Suspense, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Link, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { BusFront, CalendarDays, ChartNoAxesCombined, ChevronRight, Info, LayoutDashboard, MapPin, Menu, Moon, Brain, Route as RouteIcon, Sun, X } from 'lucide-react'
import '@fontsource-variable/inter'
import './styles.css'
import './journeys.css'
import './workspace.css'
import { JourneyResults } from './JourneyResults'
import { Planner } from './Planner'
import { api } from './api'
import { Card, State } from './ui'

const Overview=lazy(()=>import('./Overview'))
const Operator=lazy(()=>import('./Operator'))
const ModelInsights=lazy(()=>import('./ModelInsights'))
const About=lazy(()=>import('./About'))
const pages=[
  {path:'/',name:'Overview',icon:LayoutDashboard,title:'Network overview'},
  {path:'/planner',name:'Journey planner',icon:RouteIcon,title:'Journey planner'},
  {path:'/operator',name:'Operator dashboard',icon:ChartNoAxesCombined,title:'Operator dashboard'},
  {path:'/model',name:'Model insights',icon:Brain,title:'Model insights'},
  {path:'/about',name:'Methodology',icon:Info,title:'Methodology & data pipeline'},
]
function ServiceHealth(){
  const [health,setHealth]=useState<Awaited<ReturnType<typeof api.health>> | null>(null)
  const [checked,setChecked]=useState<Date | null>(null)
  const [attempt,setAttempt]=useState(0)
  const [pending,setPending]=useState(true)
  const status=health?'Service online':checked?'Service unavailable':'Checking service'
  useEffect(()=>{
    const controller=new AbortController()
    let timer:ReturnType<typeof setTimeout>
    async function check(){
      setPending(true)
      try {
        const data=await api.health(controller.signal)
        if(!controller.signal.aborted)setHealth(data)
      } catch { if(!controller.signal.aborted)setHealth(null) }
      if(!controller.signal.aborted){
        setChecked(new Date());setPending(false)
        timer=setTimeout(check,60000)
      }
    }
    check()
    return ()=>{controller.abort();clearTimeout(timer)}
  },[attempt])
  return <details className="health-monitor"><summary className="health"><i className={health?'online':checked?'offline':''}/>{status}</summary>
    <section aria-label="Live service monitor"><h2>Service monitor</h2>
      <dl><div><dt>Database</dt><dd>{health?.database ?? 'Unconfirmed'}</dd></div>
      <div><dt>Model files</dt><dd>{health?.model_files ?? 'Unconfirmed'}</dd></div></dl>
      <small role="status">{pending?'Checking service…':checked && 'Checked '+checked.toLocaleTimeString('en-GB',{timeZone:'Asia/Kolkata'})+' IST'}</small>
      <button disabled={pending} onClick={()=>setAttempt(i=>i+1)}>Check now</button></section></details>
}
function App(){
  const {pathname}=useLocation()
  const current=pathname.replace(/\/$/,'').toLowerCase() || '/'
  const page=pages.find(p=>p.path===current), results=current==='/journeys'
  const title=results?'Journey results':page?.title || 'Page not found'
  const [opened,setOpened]=useState(false)
  const [mode,setMode]=useState(document.documentElement.dataset.theme || 'light')
  function toggle(){const next=mode==='light'?'dark':'light';document.documentElement.dataset.theme=next;setMode(next);try{localStorage.setItem('crowdroute-theme',next)}catch{}}
  useEffect(()=>{document.title=title+' · CrowdSense';window.scrollTo(0,0);setOpened(false)},[pathname,title])
  useEffect(()=>{if(!opened)return;const close=(event:KeyboardEvent)=>{if(event.key==='Escape'){setOpened(false);document.getElementById('menu-toggle')?.focus()}};window.addEventListener('keydown',close);return ()=>window.removeEventListener('keydown',close)},[opened])
  return <div className="workspace"><a className="skip" href="#main">Skip to content</a>
    {opened && <button className="scrim" aria-label="Close navigation" onClick={()=>setOpened(false)}/>}
    <aside id="workspace-nav" className={'sidebar '+(opened?'open':'')}><Link to="/" className="brand" onClick={()=>setOpened(false)}><span className="brand-mark"><BusFront size={23}/></span>CrowdSense</Link>
      <div className="nav-label">Workspace</div><nav aria-label="Main navigation">{pages.map(({path,name,icon:Icon})=><NavLink key={path} end to={path} onClick={()=>setOpened(false)} className={({isActive})=>isActive || (results&&path==='/planner')?'active':''}><Icon size={18}/>{name}</NavLink>)}</nav>
      <div className="sidebar-foot"><span className="network-icon"><MapPin size={19}/></span><div><strong>Delhi network</strong><small>India · UTC +05:30</small></div></div></aside>
    <div className="stage"><header className="utility"><button id="menu-toggle" className="menu-toggle theme" aria-label="Toggle navigation" aria-controls="workspace-nav" aria-expanded={opened} onClick={()=>setOpened(!opened)}>{opened?<X/>:<Menu/>}</button>
      <div className="breadcrumb"><LayoutDashboard size={16}/>Workspace<ChevronRight size={14}/><strong>{results?title:page?.name || title}</strong></div>
      <div className="tools"><ServiceHealth/><button className="theme" aria-label={'Switch to '+(mode==='light'?'dark':'light')+' mode'} onClick={toggle}>{mode==='light'?<Moon size={17}/>:<Sun size={17}/>}</button></div></header>
    <main id="main"><div className="page-heading"><div><h1>{title}</h1></div>
      <span className="today"><CalendarDays size={15}/>{new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Kolkata',day:'numeric',month:'short',year:'numeric'}).format(new Date())}</span></div>
    <Suspense fallback={<State kind="loading">Loading workspace…</State>}><Routes><Route path="/" element={<Overview/>}/><Route path="/planner" element={<Planner/>}/><Route path="/journeys" element={<JourneyResults/>}/><Route path="/operator" element={<Operator/>}/><Route path="/model" element={<ModelInsights/>}/><Route path="/about" element={<About/>}/><Route path="*" element={<Card><Link to="/">Return to overview</Link></Card>}/></Routes></Suspense></main></div></div>
}
createRoot(document.getElementById('root')!).render(<BrowserRouter><App/></BrowserRouter>)
