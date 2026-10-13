import { X,Box,Sparkles } from 'lucide-react'
import { useRuntime,productionStale } from '../twin/runtimeStore'
import { useSelection } from '../twin/selectionStore'
import AssetInspector from '../twin/AssetInspector'
import { siteEntity,staticEntities } from './spatial'
import { formatValue } from '../twin/presentation'
export default function SiteInspector({onAsk}){
  const selected=useSelection(s=>s.selected),site=useRuntime(s=>s.site),d=useRuntime(s=>s.definition),stale=useRuntime(productionStale)
  if(!site||!selected)return null
  if(site.production.model.components.some(c=>c.id===selected))return <AssetInspector onAsk={onAsk}/>
  const e=siteEntity(d,site,selected);if(!e)return null
  const children=staticEntities(d).filter(c=>c.parent_id===selected&&['zone','warehouse','production','cell'].includes(c.kind))
  const rows=[['State',stale?'STALE':e.state],['Truck',e.truck_id],['Outbound truck',e.outbound_truck_id],['Shipment',e.shipment_id],['Dock',e.dock_id],['Node',e.node],['Pallet',e.pallet_id],['Material location',e.location],['Operation elapsed',e.elapsed_operation_time==null?null:formatValue(e.elapsed_operation_time,1,' s')],['Queue',e.queue?.join(', ')|| (e.queue?'None':null)],['OK units',e.good_ids?.length],['NG units',e.reject_ids?.length],['HOLD units',e.hold_ids?.length]].filter(([,v])=>v!==undefined&&v!==null)
  const events=site.events.filter(x=>x.component===selected||x.shipment_id===selected||x.pallet_id===selected).slice(-5).reverse()
  return <aside className="ct-inspector ct-card site-inspector" aria-label="Site asset inspector"><div className="ct-panel-top"><span className="ct-eyebrow">{e.kind||'SHIPMENT'} · DEMO</span><button className="ct-icon-button" aria-label="Close inspector" onClick={()=>useSelection.getState().overview()}><X size={17}/></button></div><div className="ct-asset-icon"><Box size={24}/></div><h2>{e.label||e.id}</h2><p className="ct-muted">{e.id}</p><dl>{rows.map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>{e.wait_reason&&<div className="ct-notice">{e.wait_reason}</div>}{e.unsupported&&<div className="ct-error">Unsupported: {e.unsupported}</div>}{!e.state&&<p className="ct-muted">Static site geometry. No live building utilization metric is implemented.</p>}{children.map(c=><button className="ct-button ct-wide" key={c.id} onClick={()=>useSelection.getState().select(c.id)}>Enter {c.label} →</button>)}<h3>Recorded activity</h3><ul className="ct-activity">{events.map(v=><li key={v.id}><i/><span>{v.type.replaceAll('_',' ')}<small>{v.state||v.purpose||v.verdict} · {formatValue(v.time,1)} s</small></span></li>)}</ul><button className="ct-button ct-wide" onClick={onAsk}><Sparkles size={14}/>Ask ARIA</button></aside>
}
