import { lazy, memo, Suspense, useEffect, useMemo, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import RenderProfiler from './RenderProfiler'
import SiteWorld from '../site/SiteWorld'
import LogisticsActors from '../site/LogisticsActors'
import { needsProductionDetail,siteAnchor,siteEntity } from '../site/spatial'
import { useRuntime,diagnostics,countRender } from './runtimeStore'
import { useSelection } from './selectionStore'
import { damping } from './presentation'
const ProductionDetail=lazy(()=>import('../site/ProductionDetail'))
function CameraRig({definition}) {
  const {camera,size}=useThree(),controls=useRef(),plan=useRef(),initial=useRef(true),request=useSelection(s=>s.cameraRequest)
  useEffect(()=>{
    const {selected,preset}=useSelection.getState(),runtime=useRuntime.getState().site
    const named=definition.cameras[preset],entity=siteEntity(definition,runtime,selected)
    const point=named?.target||siteAnchor(definition,runtime,selected)||definition.cameras.SITE_OVERVIEW.target
    const target=new THREE.Vector3(...point);target.y+=1
    let distance=named?.distance||(entity?.size?Math.max(14,Math.max(entity.size[0],entity.size[2])*1.75):entity?.kind==='truck'?22:15)
    distance*=Math.max(1,1.8/(size.width/size.height))
    const position=target.clone().add(new THREE.Vector3(.42,.92,1).normalize().multiplyScalar(distance))
    if(initial.current){camera.position.copy(position);camera.lookAt(target);controls.current?.target.copy(target);initial.current=false}
    plan.current={position,target,elapsed:0}
  },[definition,request,size.width,size.height,camera])
  useFrame((_,dt)=>{
    const p=plan.current;if(p&&controls.current){p.elapsed+=dt;camera.position.lerp(p.position,damping(dt,8));controls.current.target.lerp(p.target,damping(dt,8));controls.current.update();if(p.elapsed>.9){camera.position.copy(p.position);controls.current.target.copy(p.target);controls.current.update();plan.current=null}}
    if(diagnostics.enabled){diagnostics.camera.push({t:performance.now(),xyz:camera.position.toArray(),target:controls.current?.target.toArray()});if(diagnostics.camera.length>180)diagnostics.camera.shift()}
  })
  return <OrbitControls ref={controls} makeDefault enableDamping={false} minDistance={7} maxDistance={240} maxPolarAngle={Math.PI/2.13} onStart={()=>{plan.current=null}}/>
}
function Meter(){const {gl}=useThree();useFrame((_,dt)=>{if(diagnostics.enabled){diagnostics.frames.push(dt*1000);if(diagnostics.frames.length>1200)diagnostics.frames.shift();diagnostics.drawCalls=gl.info.render.calls;diagnostics.triangles=gl.info.render.triangles}});return null}
const Campus=memo(function Campus({definition,model}) {
  countRender('Campus')
  const selected=useSelection(s=>s.selected),preset=useSelection(s=>s.preset)
  const detail=needsProductionDetail(definition,selected,preset)
  return <><color attach="background" args={['#eff5f7']}/><ambientLight intensity={.8}/><hemisphereLight args={['#ffffff','#c7d7d7',.9]}/><directionalLight position={[30,70,45]} intensity={2.1}/><SiteWorld definition={definition} detail={detail}/><LogisticsActors/>{detail&&<Suspense fallback={null}><ProductionDetail model={model} origin={definition.production_origin}/></Suspense>}<CameraRig definition={definition}/><Meter/><RenderProfiler/></>
})
export default memo(function TwinViewport(){
  countRender('TwinViewport')
  const model=useRuntime(s=>s.model),definition=useRuntime(s=>s.definition)
  return <Canvas camera={{position:[50,100,125],fov:38,near:.1,far:500}} dpr={[1,1.5]} gl={{antialias:true}} onPointerMissed={()=>useSelection.getState().overview()}><Campus definition={definition} model={model}/></Canvas>
})
