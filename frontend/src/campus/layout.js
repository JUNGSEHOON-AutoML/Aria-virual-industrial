import definition from './campus.layout.json'
import conveyor from '../../../assets/cad/conveyor/dt_v1/dims.json'
import booth from '../../../assets/cad/inspection_booth/dt_v1/dims.json'
export const layout=definition
export const halls=layout.sites.filter(s=>s.kind==='inspection_hall')
export function hallSize(site){const d=layout.design;const length=conveyor.length_mm/1000*d.conveyor_modules;const pitch=booth.width_mm/1000+d.lane_gap;return {width:length+d.side_margin*2,depth:pitch*site.lanes.length+d.front_margin+d.rear_margin,pitch,length}}
export function laneZ(site,index){const {pitch}=hallSize(site);return (index-(site.lanes.length-1)/2)*pitch}
export function seededDecorations(){let state=layout.foliage_seed>>>0;const random=()=>{state=(Math.imul(state,1664525)+1013904223)>>>0;return state/4294967296};return layout.foliage_zones.flatMap(zone=>Array.from({length:zone.count},()=>[zone.min[0]+random()*(zone.max[0]-zone.min[0]),zone.min[1]+random()*(zone.max[1]-zone.min[1])]))}
export const modelName=m=>({coreset:'코어셋',ccifps:'CCIFPS',random_same_k:'random_same_k'})[m]||m
