import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, type Evaluation, type Model, type Peak, type Week } from './api'
import { Card, State, useRequest } from './ui'
import { PeakReport, WeeklyReport, format } from './OperatorCharts'
import './operator.css'
import './methodology.css'

async function readEvidence(signal:AbortSignal) {
  const model=await api.model(signal)
  const evaluation=await api.evaluation(signal)
  const weeks=await api.weeks(signal)
  const peaks=await api.peaks(signal)
  return {model,evaluation,weeks:weeks.items,peaks:peaks.items}
}
function ModelMethod({model:m}:{model:Model}){
  const periods=[
    ['Training',m.training_period,'Build median profiles and segment reference ranges.'],
    ['Validation',m.validation_period,'Compare the exact-slot baseline with hourly fallback.'],
    ['Testing',m.testing_period,'Score predictions against later reconstructed loads.']
  ]
  return <><Card><h2>{m.model_type}</h2>
    <div className="model-rule"><h3>Exact slot</h3><p>Use slot median with ≥{m.minimum_profile_samples} samples across ≥{m.minimum_profile_days} days.</p>
    <h3>Hourly fallback</h3><p>Falls back to hourly median when slot data is sparse.</p>
    <h3>Relative label</h3><p>Low / Moderate / High based on training quartiles. Requires ≥{m.minimum_reference_samples} samples across ≥{m.minimum_reference_days} days.</p></div></Card>
    <Card><h2>Chronological evaluation</h2>
    <ol className="periods">{periods.map(([label,date,description])=><li key={label}><h3>{label}</h3><strong>{date}</strong><p>{description}</p></li>)}</ol></Card></>
}
function EvaluationReport({evaluation:e}:{evaluation:Evaluation}){
  const t=e.test_metrics
  const baseline=e.model_comparison.find(row=>row.model==='Baseline')
  const final=e.model_comparison.find(row=>row.model==='Final Model')
  return <><Card><h2>Held-out test results</h2>
    <dl className="evaluation-metrics">{[
      ['Mean absolute error',t.MAE,'Avg passenger difference per segment.'],
      ['Root mean squared error',t.RMSE,'Penalizes larger passenger errors.'],
      ['Prediction coverage',t.coverage_percentage+'%','Observations with numeric estimate.'],
      ['Mean signed error',t.prediction_bias,'Average directional prediction bias.']
    ].map(([label,value,meaning])=><div key={label}><dt>{label}</dt><dd><strong>{value}</strong><span>{meaning}</span></dd></div>)}</dl>
    <p className="method-callout"><strong>{t.within_one_passenger_percentage}% within one recorded passenger.</strong></p>
    <small>Source · test_metrics.csv</small></Card>
    <Card><h2>Does the hourly fallback improve the baseline?</h2>
    {e.model_comparison.length===0?<State kind="empty">No common-observation comparison is available.</State>:<>
    <div className="operator-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={e.model_comparison}><CartesianGrid vertical={false} stroke="var(--line)"/><XAxis dataKey="model"/><YAxis width={40}/><Tooltip contentStyle={{background:'var(--panel)',color:'var(--ink)'}}/><Legend/>
      <Bar dataKey="MAE" fill="#3466ae" isAnimationActive={false}/><Bar dataKey="RMSE" fill="#208073" isAnimationActive={false}/></BarChart></ResponsiveContainer></div>
    <div className="op-table"><table><caption>Errors on the shared test subset</caption><thead><tr><th>Model</th><th>Observations</th><th>MAE</th><th>RMSE</th></tr></thead><tbody>{e.model_comparison.map(r=><tr key={r.model}><th scope="row">{r.model}</th><td>{format(r.observations)}</td><td>{r.MAE}</td><td>{r.RMSE}</td></tr>)}</tbody></table></div></>}
    
    <small>Source · model_comparison.csv</small></Card></>
}
function Findings({weeks,peaks}:{weeks:Week[];peaks:Peak[]}){
  const means=weeks.map(w=>w.average_recorded_load)
  const last=weeks.at(-1)
  return <><Card><h2>What varied across weeks and peak periods?</h2>
    {last && <p>Weekly mean recorded loads ranged from <strong>{Math.min(...means)} to {Math.max(...means)}</strong> passengers per observed segment. Week {last.week_number} covers {last.observed_days} observed days, so its mean represents a shorter window.</p>}
    {(['Weekday','Weekend'] as const).map(day=>{
      const morning=peaks.find(p=>p.day_type===day && p.period==='Morning Peak'), evening=peaks.find(p=>p.day_type===day && p.period==='Evening Peak')
      return <p key={day}><strong>{day} peaks.</strong> {morning && evening ? 'The morning mean was '+morning.average_load+' and the evening mean was '+evening.average_load+' recorded passengers per segment observation.' : 'A paired morning and evening comparison is unavailable.'}</p>})}
    <small>Sources · weekly_analysis.csv and peak_analysis.csv</small></Card>
    <div className="report-pair"><WeeklyReport rows={weeks}/><PeakReport rows={peaks}/></div></>
}
export default function ModelInsights(){
  const {state,retry}=useRequest(readEvidence)
  if(state.kind!=='ready')return <Card>{state.kind==='loading'?<State kind="loading">Loading model metadata and evaluation reports…</State>:<State kind="error" retry={retry}>{state.message}</State>}</Card>
  const {model,evaluation,weeks,peaks}=state.data
  return <div className="method-page"><ModelMethod model={model}/><EvaluationReport evaluation={evaluation}/><Findings weeks={weeks} peaks={peaks}/>
    <Card><h2>Methodology and sources</h2><p><Link to="/about">Read how trips and segment loads were reconstructed</Link>.</p></Card></div>
}
