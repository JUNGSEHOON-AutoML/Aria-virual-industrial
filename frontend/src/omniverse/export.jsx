// CPU capture entry only: no Replay/Live imports, API calls, clock or controls.
import React,{Suspense,useEffect} from 'react'
import {createRoot} from 'react-dom/client'
import {Canvas,useThree} from '@react-three/fiber'
import * as THREE from 'three'
import {Hall,LaneEquipment,Landscape} from '../campus/Geometry'
import {layout,halls} from '../campus/layout'
import T from '../brand/cnotta.tokens.json'

import {snapshot} from './serialize'

function ExportReady(){
 const {scene,camera,gl,invalidate}=useThree()
 useEffect(()=>{
  camera.position.set(...layout.camera.target.map((v,i)=>v+layout.camera.offset[i]));camera.lookAt(...layout.camera.target);camera.updateProjectionMatrix();invalidate()
  window.__usdExport={snapshot:()=>snapshot(scene),renderer:gl.getContext().getParameter(gl.getContext().getExtension('WEBGL_debug_renderer_info').UNMASKED_RENDERER_WEBGL),scene}
  return()=>{delete window.__usdExport}
 },[scene,camera,gl,invalidate])
 return null
}

createRoot(document.getElementById('root')).render(<Canvas orthographic frameloop="demand" dpr={1} camera={{near:.1,far:1000,zoom:layout.camera.zoom}} gl={{antialias:true,toneMapping:THREE.NoToneMapping}}>
 <color attach="background" args={[T.surface]}/><ambientLight intensity={.6}/><hemisphereLight args={[T.floor,T.line,.4]}/><directionalLight position={[-20,60,45]} intensity={.9}/>
 <Suspense fallback={null}><Landscape/>{halls.map(site=><Hall site={site} key={site.id} focused={false} onEnter={()=>{}}><LaneEquipment site={site}/></Hall>)}<ExportReady/></Suspense>
</Canvas>)
