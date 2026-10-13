import { useState } from 'react'
import { Radio,ArrowUpRight } from 'lucide-react'
import { useRuntime } from '../twin/runtimeStore'
import { useSelection } from '../twin/selectionStore'
import { formatValue } from '../twin/presentation'
import { siteEntity } from '../site/spatial'
export default function EventTimeline(){
  const site=useRuntime(s=>s.site),definition=useRuntime(s=>s.definition),[source,setSource]=useState('Site')
  const items=(site?.events||[]).filter(e=>source==='Production'?e.type.startsWith('production_'):!e.type.startsWith('production_component_state')).slice(-24).reverse()
  return <section className="ct-timeline" aria-label="Event timeline"><div className="ct-timeline-title"><Radio size={16}/><b>Activity</b><span>Recorded demo events</span><select aria-label="Event source" value={source} onChange={e=>setSource(e.target.value)}><option>Site</option><option>Production</option></select></div><div className="ct-event-strip">{items.map(e=>{const id=siteEntity(definition,site,e.component)?e.component:e.shipment_id;return <button key={e.id} className="ct-event" disabled={!id} title={JSON.stringify(e,null,2)} onClick={()=>useSelection.getState().select(id)}><span><i/>{e.type.replaceAll('_',' ')}<ArrowUpRight size={12}/></span><strong>{e.component||e.shipment_id||'Site'}</strong><small>{formatValue(e.time,1)} s · {[e.state,e.pallet_id,e.verdict,e.shipment_id].filter(Boolean).join(' · ')}</small></button>})}</div></section>
}
