import React,{useEffect,useRef} from 'react'
import {CameraControls} from '@react-three/drei'
import {useFrame,useThree} from '@react-three/fiber'
import * as THREE from 'three'
import {allowed} from '../motion/registry'
import {layout,halls,hallSize,seededDecorations} from './layout'

export default function Camera({focus,closeup=false,onFootprint}){
 const ref=useRef(),{camera,size,gl,scene,invalidate}=useThree();const last=useRef(0)
 useEffect(()=>{const c=ref.current; c.setBoundary(new THREE.Box3(new THREE.Vector3(layout.bounds.min[0],0,layout.bounds.min[1]),new THREE.Vector3(layout.bounds.max[0],20,layout.bounds.max[1])));c.smoothTime=.16
  const site=halls.find(s=>s.id===focus),target=closeup?[-4,1.1,0]:site?[site.origin[0],.3,site.origin[1]]:layout.camera.target,offset=closeup?[2.5,4,6]:site?layout.camera.hall_offset:layout.camera.offset
  if(!allowed('view.camera'))return
  c.setLookAt(...target.map((v,i)=>v+offset[i]),...target,!!window.__campus?.cameraReady);c.zoomTo((closeup?210:site?layout.camera.hall_zoom:layout.camera.zoom)*Math.min(size.width/1440,size.height/900),!!window.__campus?.cameraReady);invalidate()
  const project=p=>{const v=new THREE.Vector3(...p).project(camera);return [(v.x+1)*size.width/2,(1-v.y)*size.height/2]}
  window.__campus={...window.__campus,scene,camera,controls:c,cameraReady:true,renderer:gl.getContext().getParameter(gl.getContext().getExtension('WEBGL_debug_renderer_info').UNMASKED_RENDERER_WEBGL),audit:()=>{
   scene.updateMatrixWorld(true);camera.updateMatrixWorld();const rectangles=[];let handlers=0
   scene.traverse(o=>{if(o.name==='decorative-campus')o.traverse(n=>{handlers+=Object.keys(n.__r3f?.handlers||{}).length})})
   for(const s of halls){const {width,depth}=hallSize(s),g=scene.getObjectByName(s.id),logo=scene.getObjectByName('wordmark-'+s.id);const corners=[]
    for(const x of [-width/2,width/2])for(const y of [0,layout.design.roof_height+.5])for(const z of [-depth/2,depth/2])corners.push(project(g.localToWorld(new THREE.Vector3(x,y,z)).toArray()))
    const b=logo.geometry.boundingBox||(()=>{logo.geometry.computeBoundingBox();return logo.geometry.boundingBox})();const a=logo.localToWorld(new THREE.Vector3(0,b.min.y,b.max.z)),d=logo.localToWorld(new THREE.Vector3(0,b.max.y,b.max.z));const pa=project(a.toArray()),pb=project(d.toArray());const lp=[];for(const x of [b.min.x,b.max.x])for(const y of [b.min.y,b.max.y])for(const z of [b.min.z,b.max.z])lp.push(project(logo.localToWorld(new THREE.Vector3(x,y,z)).toArray()));rectangles.push({id:s.id,bounds:[Math.min(...corners.map(p=>p[0])),Math.min(...corners.map(p=>p[1])),Math.max(...corners.map(p=>p[0])),Math.max(...corners.map(p=>p[1]))],glyph_height_px:Math.abs(pb[1]-pa[1]),logo_bounds:[Math.min(...lp.map(p=>p[0])),Math.min(...lp.map(p=>p[1])),Math.max(...lp.map(p=>p[0])),Math.max(...lp.map(p=>p[1]))],roof_opacity:scene.getObjectByName('roof-'+s.id).userData.opacity,brand_width_ratio:layout.design.roof_brand_width_ratio,geometry:logo.geometry.type})
   }
   return {viewport:[size.width,size.height],panels:[...document.querySelectorAll('.campus-summary article')].map(e=>{const r=e.getBoundingClientRect();return [r.x,r.y,r.right,r.bottom]}),halls:rectangles,draw_calls:gl.info.render.calls,triangles:gl.info.render.triangles,decorative_handlers:handlers,foliage:seededDecorations(),focus,target:c.getTarget().toArray(),names:[...document.querySelectorAll('[data-hall-name]')].map(e=>{const r=e.getBoundingClientRect();return {id:e.dataset.hallName,text:e.textContent,bounds:[r.x,r.y,r.right,r.bottom]}})}
  }}
 },[focus,closeup,size.width,size.height,scene,camera,gl,invalidate])
 useFrame(state=>{if(state.clock.elapsedTime-last.current<.2)return;last.current=state.clock.elapsedTime;const ray=new THREE.Raycaster(),plane=new THREE.Plane(new THREE.Vector3(0,1,0),0),points=[];for(const [x,y] of [[-1,-1],[-1,1],[1,1],[1,-1]]){ray.setFromCamera(new THREE.Vector2(x,y),camera);const p=ray.ray.intersectPlane(plane,new THREE.Vector3());if(p)points.push([p.x,p.z])}const signature=JSON.stringify(points.map(p=>p.map(v=>Math.round(v*100)/100)));if(last.signature!==signature){last.signature=signature;onFootprint(points)}})
 return <CameraControls enabled={allowed('view.camera')} ref={ref} makeDefault minZoom={layout.camera.min_zoom} maxZoom={closeup?300:layout.camera.max_zoom} minPolarAngle={.35} maxPolarAngle={1.1} minAzimuthAngle={-.5} maxAzimuthAngle={.7}/>
}
