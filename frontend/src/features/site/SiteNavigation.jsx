import { useRuntime } from '../twin/runtimeStore'
import { useSelection } from '../twin/selectionStore'
import { ancestry,presetLabels,staticEntities } from './spatial'
const EMPTY=[]
export default function SiteNavigation(){
  const d=useRuntime(s=>s.definition),shipments=useRuntime(s=>s.site?.shipments||EMPTY),selected=useSelection(s=>s.selected),preset=useSelection(s=>s.preset)
  const effective=selected||({WAREHOUSE:'WAREHOUSE-01',PRODUCTION:'PRODUCTION-01',QUALITY_CELL:'CELL-01',INBOUND_YARD:'ZONE-INBOUND',OUTBOUND_YARD:'ZONE-OUTBOUND'}[preset])||'SITE-DEMO-01'
  const chain=ancestry(d,effective),children=staticEntities(d).filter(e=>e.parent_id===effective&&['zone','warehouse','production','cell','Machine','Inspection','Buffer','Source','Sink','Conveyor','Diverter'].includes(e.kind))
  return <div className="site-navigation"><div className="site-presets">{Object.entries(presetLabels).map(([id,label])=><button key={id} className={preset===id?'active':''} onClick={()=>useSelection.getState().setPreset(id)}>{label}</button>)}<select aria-label="Find shipment" value={shipments.some(s=>s.id===selected)?selected:''} onChange={e=>e.target.value&&useSelection.getState().select(e.target.value)}><option value="">Shipments…</option>{shipments.map(s=><option key={s.id} value={s.id}>{s.id} · {s.state}</option>)}</select></div><div className="site-breadcrumb" aria-label="Spatial hierarchy">{chain.map((n,i)=><span key={n.id}>{i>0&&<i>›</i>}<button onClick={()=>n.kind==='site'?useSelection.getState().overview():useSelection.getState().select(n.id)}>{n.label}</button></span>)}{children.length>0&&<select aria-label="Drill down" value="" onChange={e=>e.target.value&&useSelection.getState().select(e.target.value)}><option value="">Enter {effective==='CELL-01'?'asset':'area'}…</option>{children.map(c=><option key={c.id} value={c.id}>{c.label}</option>)}</select>}</div></div>
}
