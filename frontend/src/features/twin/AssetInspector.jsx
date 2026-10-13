import { X, Sparkles, Activity } from 'lucide-react'
import { useRuntime, productionStale } from './runtimeStore'
import { useSelection } from './selectionStore'
import { formatValue } from './presentation'
export default function AssetInspector({ onAsk }) {
  const id = useSelection(s => s.selected), s = useRuntime(s => s.snapshot), stale = useRuntime(productionStale)
  const c = s?.model.components.find(c => c.id === id), r = s?.metrics.resources?.[id]
  if (!c) return null
  const parts = s.parts.filter(p => p.component === id), events = s.events.filter(e => e.component === id).slice(-3).reverse()
  const rows = [['Utilization', formatValue(r?.utilization == null ? null : r.utilization*100,1,'%')], ['Occupancy',formatValue(r?.occupancy)], ['Average queue',formatValue(r?.avg_queue,2)], ['Processing',parts.filter(p=>p.phase==='process').map(p=>p.id).join(', ') || '—'], ['Process time',formatValue(c.processing_time,2,' s')], ['Completed',formatValue(r?.completed)]]
  return <aside className="ct-inspector ct-card" aria-label="Asset inspector"><div className="ct-panel-top"><span className="ct-eyebrow">SELECTED ASSET</span><button className="ct-icon-button" aria-label="Close inspector" onClick={() => useSelection.getState().overview()}><X size={17}/></button></div><div className="ct-asset-icon"><Activity size={24}/></div><h2>{c.id}</h2><p className="ct-muted">{c.kind} · {stale ? 'STALE' : r?.state || 'N/A'}</p>
    <dl>{rows.map(([label,value]) => <div key={label}><dt>{label}</dt><dd>{stale && label !== 'Process time' ? 'STALE' : value}</dd></div>)}</dl>
    {c.kind === 'Inspection' && <div className="ct-notice">Inspection: <b>{c.inspection_mode}</b>{c.inspection_mode === 'mock' && <p>Seeded simulation verdicts. No CCIFPS inference claimed.</p>}</div>}
    <h3>Fault / interlock</h3><p className="ct-muted">{stale ? 'Unconfirmed · telemetry stale' : r?.fault ? `${r.fault.label || r.fault.cause || 'Active virtual fault'}` : 'No fault reported'}</p>
    <h3>Recent activity</h3>{events.length ? <ul className="ct-activity">{events.map((e,i) => <li key={i}><i/><span>{e.type.replaceAll('_',' ')}<small>{[e.part,e.state,e.event].filter(Boolean).join(' · ')} · {formatValue(e.time,1)} s</small></span></li>)}</ul> : <p className="ct-muted">No event for this asset in the current run.</p>}
    <button className="ct-button ct-wide" onClick={onAsk}><Sparkles size={15}/>Ask ARIA</button>
  </aside>
}
