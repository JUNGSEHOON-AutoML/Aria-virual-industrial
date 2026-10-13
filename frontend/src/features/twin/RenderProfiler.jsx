import {useEffect} from 'react'
import {useThree} from '@react-three/fiber'
import {diagnostics} from './runtimeStore'
// Observe actual WebGL submissions, including multiple passes. Measurement-only.
export default function RenderProfiler(){
 const {gl,scene}=useThree()
 useEffect(()=>{
  if(!diagnostics.enabled)return
  const original=gl.renderBufferDirect;let frame=-1,rows=[]
  gl.renderBufferDirect=function(camera,s,geometry,material,object,group){
   const next=gl.info.render.frame
   if(next!==frame){
    if(rows.length){let objects=0,meshes=0;scene.traverse(o=>{objects++;if(o.isMesh)meshes++});diagnostics.profile={rows,objects,meshes}}
    rows=[];frame=next
   }
   let component='world',category='other',source='unclassified'
   for(let p=object;p;p=p.parent){const d=p.userData||{};if(d.componentId)component=d.componentId;if(category==='other'&&d.profileCategory)category=d.profileCategory;if(source==='unclassified'&&d.sourceModule)source=d.sourceModule}
   rows.push({component,category,source,geometry:geometry.type,material:material.type+':'+material.color?.getHexString(),instances:object.isInstancedMesh?object.count:1})
   return original.call(this,camera,s,geometry,material,object,group)
  }
  return ()=>{gl.renderBufferDirect=original}
 },[gl,scene]);return null
}
