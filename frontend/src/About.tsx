import { Link } from 'react-router-dom'
import { BusFront, Database, GitMerge, Layers, ListOrdered, Monitor, Route, Tickets, type LucideIcon } from 'lucide-react'
import { Card } from './ui'
import './methodology.css'

type Stage = [LucideIcon, string, string]
const reconstruction:Stage[]=[
  [Tickets,'Prepare tickets','Parse local timestamps, normalize stops, and filter valid ticket records.'],
  [Route,'Match direction','Map ticket routes to GTFS ordered stop patterns to separate directions.'],
  [GitMerge,'Assign trip','Match ticket times against candidate departures at the boarding stop.'],
  [ListOrdered,'Accumulate load','Track running passenger load from boarding to assumed destination.']
]
const architecture:Stage[]=[
  [Layers,'Data pipeline','Python, pandas and DuckDB reconstruct loads from ticket and GTFS data.'],
  [Database,'Parquet storage','Fast, immutable Parquet stores schedules, patterns and profiles.'],
  [BusFront,'FastAPI engine','Validates queries, plans 0/1-transfer trips, and ranks by crowding.'],
  [Monitor,'React dashboard','TypeScript, Vite, Tailwind CSS, Recharts and Mapbox visualization.']
]
function Flow({title,stages}:{title:string;stages:Stage[]}){
  return <figure className="method-flow"><figcaption>{title}</figcaption><ol>{stages.map(([Icon,name,body])=><li key={name}><span className="flow-icon"><Icon aria-hidden="true" size={22}/></span><h3>{name}</h3><p>{body}</p></li>)}</ol></figure>
}
const limits=[
  ['Missing vehicle IDs','Tickets without valid vehicle identifiers cannot be tied to journeys.'],
  ['Unmatched stops','Naming mismatches leave some tickets without segment attribution.'],
  ['Ambiguous assignments','Close candidate trips are excluded to preserve statistical integrity.'],
  ['Unrecorded riders','Pass holders and un-ticketed riders are not in electronic running totals.'],
  ['Sparse records','Segments with low samples receive Insufficient Data status.'],
  ['Uncalibrated capacity','Relative crowding reflects history, not physical bus overload.']
]
export default function About(){return <div className="method-page">
  <Card><h2>Why compare crowding as well as time?</h2>
    <p>Pairs electronic ticketing with GTFS schedules to estimate relative bus crowding by route, direction and time of day in Delhi.</p></Card>
  <Card><Flow title="From ticket records to segment loads" stages={reconstruction}/>
    <div className="load-equation"><strong>Load leaving a stop</strong><span>Previous recorded load + boardings − assumed alightings</span></div></Card>
  <Card><h2>Methodology boundaries</h2><dl className="method-limits">{limits.map(([title,body])=><div key={title}><dt>{title}</dt><dd>{body}</dd></div>)}</dl></Card>
  <Card><Flow title="System architecture" stages={architecture}/></Card>
</div>}
