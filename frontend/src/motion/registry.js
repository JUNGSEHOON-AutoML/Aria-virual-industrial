import registry from '../../../configs/ambient_motion.json'
import {permit} from './core.mjs'
export function allowed(id) {
  const m=registry.motions.find(row=>row.id===id)
  return m ? permit(registry,id,m.source,m.clock) : false
}
export {registry}
