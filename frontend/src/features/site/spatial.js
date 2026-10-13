export function staticEntities(definition) {
  return ['sites','zones','buildings','assets','roads','transport_nodes','docks','staging_areas'].flatMap(k=>definition?.[k] || [])
}
export function siteEntity(definition,runtime,id) {
  if(!id)return null
  const staticEntity=staticEntities(definition).find(e=>e.id===id)
  const actor=['trucks','forklifts','docks','pallets','shipments','workpieces'].flatMap(k=>runtime?.[k]||[]).find(e=>e.id===id)
  return staticEntity || actor ? {...staticEntity,...actor} : null
}
export function siteAnchor(definition,runtime,id) {
  const entity=siteEntity(definition,runtime,id)
  if(entity?.position)return entity.position
  if(entity?.pallet_id)return siteEntity(definition,runtime,entity.pallet_id)?.position || null
  if(entity?.node)return definition?.transport_nodes.find(n=>n.id===entity.node)?.position || null
  return null
}
export function ancestry(definition,id) {
  const nodes=new Map(staticEntities(definition).map(n=>[n.id,n])),chain=[],seen=new Set()
  let node=nodes.get(id)
  while(node&&!seen.has(node.id)){chain.unshift(node);seen.add(node.id);node=nodes.get(node.parent_id)}
  return chain
}
export const presetLabels={SITE_OVERVIEW:'Site',INBOUND_YARD:'Inbound yard',WAREHOUSE:'Warehouse',PRODUCTION:'Production',QUALITY_CELL:'Quality cell',OUTBOUND_YARD:'Outbound yard'}
export function needsProductionDetail(definition,selected,preset) {
  return ['PRODUCTION','QUALITY_CELL'].includes(preset) || ancestry(definition,selected).some(n=>n.id==='PRODUCTION-01')
}
