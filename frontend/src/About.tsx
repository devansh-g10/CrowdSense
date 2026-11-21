import { Link } from 'react-router-dom'
import { BusFront, Database, GitMerge, Layers, ListOrdered, Monitor, Route, Tickets, type LucideIcon } from 'lucide-react'
import { Card } from './ui'
import './methodology.css'

type Stage = [LucideIcon, string, string]
const reconstruction:Stage[]=[
  [Tickets,'Prepare tickets','Parse ticket timestamps in Delhi local time, normalize route and stop names, and retain records with a positive passenger count, a vehicle number and a usable stop pair.'],
  [Route,'Match the direction','Map each ticket route to a unique GTFS route. Use an ordered stop pattern where the boarding stop comes before the ticket destination. This keeps opposite directions separate.'],
  [GitMerge,'Assign a scheduled trip','Check the service calendar and compare ticket time with candidate departures at the boarding stop. Keep a unique candidate or a closest match clearly separated from the runner-up.'],
  [ListOrdered,'Accumulate movements','Group accepted tickets by vehicle, service date, scheduled trip, route and pattern. Add each ticket’s passenger count at boarding and subtract it at the assumed destination.']
]
const architecture:Stage[]=[
  [Layers,'Offline notebook','Python, pandas and DuckDB prepare the ticket and GTFS data, reconstruct loads and evaluate historical profiles.'],
  [Database,'Read-only exports','Parquet stores schedules, stop patterns and crowding profiles. JSON describes the model and CSV files preserve the evaluation and consistency reports.'],
  [BusFront,'Journey and analytics API','FastAPI validates requests. DuckDB queries the exports. The planner finds direct and one-transfer journeys, attaches segment evidence and ranks alternatives.'],
  [Monitor,'Passenger and operator views','React, TypeScript, Vite and Tailwind CSS power the interface. Recharts displays analytics. Leaflet and OpenStreetMap display scheduled stops and approximate routes.']
]
function Flow({title,stages}:{title:string;stages:Stage[]}){
  return <figure className="method-flow"><figcaption>{title}</figcaption><ol>{stages.map(([Icon,name,body])=><li key={name}><span className="flow-icon"><Icon aria-hidden="true" size={22}/></span><h3>{name}</h3><p>{body}</p></li>)}</ol></figure>
}
const limits=[
  ['Missing vehicle numbers','A ticket without a usable vehicle identifier cannot be tied to a reconstructed vehicle journey. That removes some recorded demand from the analysis.'],
  ['Unmatched stops','A spelling or naming mismatch, or a destination outside the ordered pattern, can leave a ticket without a usable segment.'],
  ['Ambiguous assignments','Several scheduled trips can fit the same ticket time. Close competing matches are excluded. Even an accepted schedule match is an inference about the trip.'],
  ['Unrecorded passengers','Pass holders and other riders without a corresponding ticket are absent from the running total. A passenger can also alight earlier or later than the ticket destination.'],
  ['Sparse historical data','A segment may have few journeys or too few distinct days. Insufficient Data signals that the evidence cannot support a crowding label.'],
  ['Unknown bus capacity','The exports contain no calibrated capacity or independent onboard counts. A High label describes the segment’s own history. It cannot establish overload, standing room or available seats.']
]
export default function About(){return <div className="method-page">
  <Card><h2>Why compare crowding as well as time?</h2><p>Delhi’s transport hackathon asked for a bus-only planner that helps a commuter decide whether a slower trip might be more comfortable. The brief pairs conductor-issued and electronic tickets with static General Transit Feed Specification (GTFS) schedules to study crowding by direction, stretch and time of day.</p>
    <p>CrowdRoute Delhi shows the trade-off alongside each scheduled journey. Operators can inspect recurring patterns and see where too little evidence exists to draw a conclusion. <a href="https://docs.google.com/document/d/1ocS9rG4_E_Fb9DJcqTG8SClrLJJ_UJqGGAhgPbV8tr4/preview">Read the original problem statement</a>.</p></Card>
  <Card><Flow title="From ticket records to segment loads" stages={reconstruction}/>
    <div className="load-equation"><strong>Load leaving a stop</strong><span>Previous recorded load + boardings − assumed alightings</span></div>
    <p>The notebook carries this running total through the observed stop span and assigns it to the segment ending at the next stop. Historical model construction and evaluation use scheduled trip slots with one registered vehicle.</p></Card>
  <Card><h2>Where the evidence is limited</h2><dl className="method-limits">{limits.map(([title,body])=><div key={title}><dt>{title}</dt><dd>{body}</dd></div>)}</dl></Card>
  <Card><Flow title="System architecture" stages={architecture}/><p>Searches reuse the exported model. Schedule times are approximate, and the feed has no holiday exception file. <Link to="/model">Explore the held-out evaluation</Link>.</p></Card>
</div>}
