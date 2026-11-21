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
  return <><Card><h2>{m.model_type}</h2><p>Version {m.version} draws on {format(m.total_ticket_records)} input ticket records. The export contains {format(m.final_profiles)} profiles. Each profile identifies a directed segment, its stop sequence and pattern, a weekday or weekend, and a local time slot.</p>
    <div className="model-rule"><h3>Exact slot</h3><p>Use the training median for the {m.time_slot_minutes}-minute slot when it has at least {m.minimum_profile_samples} samples across {m.minimum_profile_days} days.</p>
    <h3>Hourly fallback</h3><p>If the slot is sparse, use the same segment and day type’s hourly median when it meets the support minimum. A low-support numeric estimate may still exist in the export.</p>
    <h3>Relative label</h3><p>The segment reference needs at least {m.minimum_reference_samples} samples across {m.minimum_reference_days} days. A supported prediction below the lower training quartile is Low, above the upper quartile is High, and between them, including the boundaries, is Moderate. Missing predictions or inadequate evidence receive Insufficient Data.</p></div></Card>
    <Card><h2>Chronological evaluation</h2><p>Local travel dates in {m.timezone}. The notebook held later days out of model construction.</p>
    <ol className="periods">{periods.map(([label,date,description])=><li key={label}><h3>{label}</h3><strong>{date}</strong><p>{description}</p></li>)}</ol></Card></>
}
function EvaluationReport({evaluation:e}:{evaluation:Evaluation}){
  const t=e.test_metrics
  const baseline=e.model_comparison.find(row=>row.model==='Baseline')
  const final=e.model_comparison.find(row=>row.model==='Final Model')
  return <><Card><h2>Held-out test results</h2><p>The target is the passenger load reconstructed from recorded tickets on each segment. The model produced a numeric prediction for <strong>{format(t.evaluated_observations)} of {format(t.total_observations)}</strong> test observations.</p>
    <dl className="evaluation-metrics">{[
      ['Mean absolute error',t.MAE,'Mean absolute difference in recorded passengers per evaluated segment.'],
      ['Root mean squared error',t.RMSE,'Passenger-scale error that gives larger misses more weight.'],
      ['Prediction coverage',t.coverage_percentage+'%','Share of all test observations with a numeric estimate, including low-support estimates.'],
      ['Mean signed error',t.prediction_bias,'Prediction minus reconstructed load, averaged over evaluated observations.']
    ].map(([label,value,meaning])=><div key={label}><dt>{label}</dt><dd><strong>{value}</strong><span>{meaning}</span></dd></div>)}</dl>
    <p className="method-callout"><strong>{t.within_one_passenger_percentage}% within one recorded passenger.</strong> Among evaluated observations, this share had an absolute error of at most one passenger against the ticket-derived count. Actual onboard occupancy was never independently measured.</p>
    <small>Source · test_metrics.csv</small></Card>
    <Card><h2>Does the hourly fallback improve the baseline?</h2><p>This comparison uses only observations with predictions from both models. Lower error means closer agreement with the recorded segment load.</p>
    {e.model_comparison.length===0?<State kind="empty">No common-observation comparison is available.</State>:<>
    <div className="operator-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={e.model_comparison}><CartesianGrid vertical={false} stroke="var(--line)"/><XAxis dataKey="model"/><YAxis width={40}/><Tooltip contentStyle={{background:'var(--panel)',color:'var(--ink)'}}/><Legend/>
      <Bar dataKey="MAE" fill="#3466ae" isAnimationActive={false}/><Bar dataKey="RMSE" fill="#208073" isAnimationActive={false}/></BarChart></ResponsiveContainer></div>
    <div className="op-table"><table><caption>Errors on the shared test subset</caption><thead><tr><th>Model</th><th>Observations</th><th>MAE</th><th>RMSE</th></tr></thead><tbody>{e.model_comparison.map(r=><tr key={r.model}><th scope="row">{r.model}</th><td>{format(r.observations)}</td><td>{r.MAE}</td><td>{r.RMSE}</td></tr>)}</tbody></table></div></>}
    {baseline && final && baseline.observations===final.observations && <p>On the {format(final.observations)} shared observations, mean absolute error went from {baseline.MAE} for the baseline to {final.MAE} with hourly fallback. Measurements on this shared subset use a different denominator from the full held-out results above.</p>}
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
    <Card><h2>Methodology and sources</h2><p>Model identity, periods and support rules come from model_metadata.json. Evaluation and consistency figures come from saved CSV reports. The methodology follows the completed CrowdRoute Delhi notebook. <Link to="/about">Read how trips and segment loads were reconstructed</Link>.</p></Card></div>
}
