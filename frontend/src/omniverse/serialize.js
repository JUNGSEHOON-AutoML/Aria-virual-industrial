import * as THREE from 'three'
import {layout} from '../campus/layout'

const id=s=>s.replace(/[^a-zA-Z0-9_]/g,'_')
const siteName=s=>s.kind==='inspection_hall'?'Hall_'+s.class:s.kind==='robot_cell'?'RobotCell':'Yard'
const bounds=b=>[b.min.toArray(),b.max.toArray()]

// Exposed separately so the gate can inspect the actual running web scene too.
export function snapshot(scene){
 scene.updateMatrixWorld(true)
 const geometries=[],materials=[],nodes=[],boxes={},geometryIds=new Map(),materialIds=new Map()
 const all=new THREE.Box3(),semantic=new Set(['MainConveyor','Booth','Diverter','Reinspection'])
 function geometry(g){
  if(geometryIds.has(g))return geometryIds.get(g)
  const n=geometries.length;geometryIds.set(g,n)
  geometries.push({points:Array.from(g.attributes.position.array),normals:g.attributes.normal?Array.from(g.attributes.normal.array):null,indices:g.index?Array.from(g.index.array):Array.from({length:g.attributes.position.count},(_,i)=>i)})
  return n
 }
 function material(m){
  if(Array.isArray(m))throw new Error('Multi-material mesh needs explicit subsets')
  if(materialIds.has(m))return materialIds.get(m)
  const n=materials.length;materialIds.set(m,n)
  materials.push({name:'Material_'+n,srgb:'#'+m.color.getHexString(),linear:m.color.toArray(),roughness:m.roughness??1,metallic:m.metalness??0,opacity:m.opacity,emissive:m.emissive?m.emissive.clone().multiplyScalar(m.emissiveIntensity??1).toArray():[0,0,0]})
  return n
 }
 function group(path,world,metadata={}){nodes.push({path,matrix:world.toArray(),metadata,kind:'group'});boxes[path]=new THREE.Box3()}
 function mesh(o,path,world){
  const b=new THREE.Box3();const p=new THREE.Vector3(),attr=o.geometry.attributes.position
  for(let i=0;i<attr.count;i++)b.expandByPoint(p.fromBufferAttribute(attr,i).applyMatrix4(world))
  for(const [parent,box] of Object.entries(boxes))if(path.startsWith(parent+'/'))box.union(b)
  all.union(b)
  nodes.push({path,kind:'mesh',matrix:world.toArray(),geometry:geometry(o.geometry),material:material(o.material),bounds:bounds(b)})
 }
 function walk(o,path){
  if(!o.visible)return
  if(o.name.startsWith('Lane_')||semantic.has(o.name)||o.name.startsWith('roof-hall-')){
   path+='/'+(o.name.startsWith('roof-')?'Roof':id(o.name));group(path,o.matrixWorld,o.userData)
  }
  if(o.isMesh){
   const base=path+'/'+id(o.name||'Mesh')+'_'+nodes.length
   if(o.isInstancedMesh){for(let i=0;i<o.count;i++){const m=new THREE.Matrix4();o.getMatrixAt(i,m);mesh(o,base+'_'+i,o.matrixWorld.clone().multiply(m))}}
   else mesh(o,base,o.matrixWorld)
  }
  // LOD uses the highest-detail existing prefab deterministically for USD.
  const children=o.isLOD?[o.levels[0].object]:o.children
  for(const child of children){if(o.isLOD){const was=child.visible;child.visible=true;walk(child,path);child.visible=was}else walk(child,path)}
 }
 for(const site of layout.sites){
  const o=scene.getObjectByName(site.kind==='inspection_hall'?site.id:'decorative-'+site.id)
  if(!o)throw new Error('Missing site '+site.id)
  const path='/World/Campus/'+siteName(site);group(path,o.matrixWorld,{siteId:site.id,kind:site.kind,...(site.kind==='robot_cell'?{robotRepresentation:'placeholder; no verified URDF to USD converter'}:{})});walk(o,path)
 }
 const landscape=scene.getObjectByName('decorative-campus')
 group('/World/Campus/Landscape',landscape.matrixWorld)
 // Decorative sites above are already exported in their proper root locations.
 for(const child of landscape.children)if(!child.children.some(c=>c.name.startsWith('decorative-')))walk(child,'/World/Campus/Landscape')
 return {schema:1,units:'m',upAxis:'Y',scope:'static campus, roof closed, highest LOD; no DOM, lights, process parts or animation',layout,nodes,geometries,materials,bounds:Object.fromEntries(Object.entries(boxes).filter(([,b])=>!b.isEmpty()).map(([p,b])=>[p,bounds(b)])),worldBounds:bounds(all)}
}
