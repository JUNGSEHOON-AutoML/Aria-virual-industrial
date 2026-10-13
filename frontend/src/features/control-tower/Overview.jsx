import { Play, Pause, SkipForward, RotateCcw, Focus, Box, CircleDot } from 'lucide-react'
import TwinViewport from '../twin/TwinViewport'
import SiteInspector from '../site/SiteInspector'
import SiteNavigation from '../site/SiteNavigation'
import { useRuntime, productionStale } from '../twin/runtimeStore'
import { useSelection } from '../twin/selectionStore'
import { formatValue, finite } from '../twin/presentation'
import EventTimeline from '../incidents/EventTimeline'
function RuntimeHeader() {
  const status = useRuntime(s => s.snapshot?.status), time = useRuntime(s => s.snapshot?.time)
  const stale = useRuntime(productionStale), speed = useRuntime(s=>s.site?.speed)
  const busy = useRuntime(s => s.busy), action = useRuntime(s => s.action)
  return <div className="ct-runtime-header"><div><div className="ct-eyebrow">ARIA DEMO CAMPUS / SYNTHETIC SITE</div><h1>Site operations</h1><div className="ct-statuses"><span className={`ct-status ${status === 'running' && !stale ? 'green' : ''}`}><i/>{stale ? 'TELEMETRY STALE' : `SITE ${status?.toUpperCase() || 'N/A'}`}</span><span className="ct-secondary"><CircleDot size={12}/>{'LOGISTICS + PRODUCTION'}</span><span className="ct-secondary">t {formatValue(time, 1)} s</span></div></div>
    <div className="ct-controls" aria-label="Site simulation controls"><select className="site-speed" aria-label="Site speed" value={speed||1} disabled={busy||status!=='running'} onChange={e=>action('/run',{speed:Number(e.target.value)})}>{[1,2,5,20].map(v=><option key={v} value={v}>{v}× simulation</option>)}</select>
      <button className="ct-button ct-primary" disabled={busy || stale || status === 'running'} onClick={() => action(time > 0 ? '/resume' : '/run')}><Play size={14}/>{time > 0 ? 'Resume' : 'Run'}</button>
      <button className="ct-button" disabled={busy || stale || status !== 'running'} onClick={() => action('/pause')}><Pause size={14}/>Pause</button>
      <button className="ct-button" disabled={busy || stale || status === 'running'} onClick={() => action('/step')}><SkipForward size={14}/>Step</button>
      <button className="ct-button" disabled={busy || stale} onClick={() => action('/reset')}><RotateCcw size={14}/>Reset</button>
    </div></div>
}
function KPIBar() {
  const m=useRuntime(s=>s.snapshot?.metrics),l=useRuntime(s=>s.site?.metrics),stale=useRuntime(productionStale)
  const rows=[['Production throughput',m?.throughput_per_hour,1,'/h','Existing DES pipeline'],['Work in progress',m?.wip,0,'','Admitted workpieces'],['Good output',m?.counts?.OK,0,'','Inspection-accepted units'],['Active shipments',l?.active_shipments,0,'','Bounded demo: 3 shipments'],['Waiting trucks',l?.waiting_trucks,0,'','Awaiting available dock'],['Departed shipments',l?.departed_shipments,0,'','Actual loaded departures']]
  return <div className="ct-kpis">{rows.map(([label,value,digits,unit,note])=><div className="ct-kpi" key={label}><span>{label}</span><strong data-kpi={label}>{stale?'STALE':formatValue(value,digits)}<small>{finite(value)&&!stale?unit:''}</small></strong><em>{note}</em></div>)}</div>
}
export default function Overview({ onAsk }) {
  const model = useRuntime(s => s.model), error = useRuntime(s => s.error)
  const selected = useSelection(s => s.selected)
  return <section className="ct-overview" aria-label="Control Tower Overview">
    <RuntimeHeader/>
    {error && <div role="alert" className="ct-error">{error}</div>}
    <div className="ct-stage">
      <div className="ct-world" aria-label="Digital twin viewport">{model ? <TwinViewport/> : <div className="ct-loading">Connecting to factory telemetry…</div>}</div>
      <KPIBar/><SiteNavigation/>
      <div className="ct-scene-caption"><Box size={14}/> SYNTHETIC DEMO <span>·</span> Not a real factory map</div>
      <button className="ct-button ct-camera-reset" onClick={() => useSelection.getState().overview()}><Focus size={15}/>Site overview</button>
      {selected && <SiteInspector onAsk={onAsk}/>}
      <div className="ct-scene-help">Select a building or vehicle · Drill down without leaving the site</div>
      <div className="ct-legend"><span><i style={{background:'#23aa97'}}/>Processing</span><span><i style={{background:'#e2a342'}}/>Blocked</span><span><i style={{background:'#ed6471'}}/>Fault</span></div>
    </div>
    <EventTimeline/>
  </section>
}
