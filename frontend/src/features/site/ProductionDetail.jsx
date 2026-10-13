import { memo, useMemo, useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import { Equipment } from '../../hmi/factory/IndustrialEquipment'
import RollerConveyor from '../../hmi/scene/prefabs/RollerConveyor'
import { PresentationContext } from '../../hmi/factory/PresentationContext'
import { useRuntime, countRender, diagnostics } from '../twin/runtimeStore'
import { useSelection } from '../twin/selectionStore'
import { damping } from '../twin/presentation'
const Links=memo(function Links({model}) {
  countRender('Links')
  const nodes=new Map(model.components.map(c=>[c.id,c]))
  return model.connections.map((e,i)=>{
    const a=nodes.get(e.source)?.position,b=nodes.get(e.target)?.position
    if(!a||!b)return null
    const d=Math.hypot(b[0]-a[0],b[2]-a[2])
    return <group key={i} userData={{profileCategory:"conveyor",sourceModule:"RollerConveyor"}}>{d>2.6&&d<10&&<RollerConveyor length={d-2.1} width={.6} position={[(a[0]+b[0])/2,.86,(a[2]+b[2])/2]} rotation={[0,-Math.atan2(b[2]-a[2],b[0]-a[0]),0]} running={false}/>}</group>
  })
})
// Resource updates stay at the asset leaf; geometry and camera never subscribe to the full snapshot.
const Asset=memo(function Asset({component:c}) {
  countRender(`Asset:${c.id}`)
  const signature=useRuntime(s=>JSON.stringify([s.snapshot?.metrics.resources?.[c.id]?.state,s.snapshot?.metrics.resources?.[c.id]?.fault,s.snapshot?.metrics.resources?.[c.id]?.robot,s.snapshot?.parts?.find(p=>p.component===c.id),s.snapshot?.status==='running'&&s.snapshot?.parts?.some(p=>p.component===c.id)?s.snapshot?.time:0]))
  const resource=useMemo(()=>{const s=useRuntime.getState().snapshot;return {r:s.metrics.resources?.[c.id],p:s.parts.find(p=>p.component===c.id),time:s.time}},[signature,c.id])
  const selected=useSelection(s=>s.selected===c.id),[hover,setHover]=useState(false)
  return <group userData={{componentId:c.id,profileCategory:c.kind==="Conveyor"?"conveyor":"equipment",sourceModule:c.kind==="Conveyor"?"RollerConveyor":"IndustrialEquipment"}} position={c.position} rotation={[0,c.rotation,0]} onClick={e=>{e.stopPropagation();useSelection.getState().select(c.id)}} onPointerOver={e=>{e.stopPropagation();setHover(true)}} onPointerOut={()=>setHover(false)}>
    {c.kind==='Conveyor'?<RollerConveyor length={c.length} width={1.1} position={[0,.86,0]} running={false}/>:<Equipment component={c} resource={resource.r} part={resource.p} time={resource.time}/>}
    {selected&&<mesh position={[0,.045,0]} rotation={[-Math.PI/2,0,0]}><ringGeometry args={[1.7,1.76,48]}/><meshBasicMaterial color="#249bc0"/></mesh>}
    {resource.r?.fault&&<Html position={[0,3.4,0]} center zIndexRange={[8,0]}><span className="ct-fault" title={resource.r.fault.label}>!</span></Html>}
    {hover&&!selected&&<Html position={[0,['Machine','Inspection'].includes(c.kind)?3.7:2,0]} center zIndexRange={[8,0]} style={{pointerEvents:'none'}}><div className="ct-tooltip">{c.id}<small>{resource.r?.state || 'N/A'}</small></div></Html>}
  </group>
})
function ProductionParts() {
  const mesh=useRef(), positions=useRef(new Map()),lastRun=useRef(),lastTime=useRef(-1)
  const dummy=useMemo(()=>new THREE.Object3D(),[]),target=useMemo(()=>new THREE.Vector3(),[]),color=useMemo(()=>new THREE.Color(),[])
  useFrame((_,dt)=>{
    if(!mesh.current)return
    const s=useRuntime.getState(),p=s.poses,running=s.snapshot?.status==='running'
    const reset=lastRun.current!==p.run||p.time<lastTime.current
    if(reset)positions.current.clear()
    const step=!running&&p.time!==lastTime.current
    lastRun.current=p.run;lastTime.current=p.time
    const live=new Set()
    p.targets.forEach((t,i)=>{
      live.add(t.id);let pos=positions.current.get(t.id)
      if(!pos){pos=new THREE.Vector3(...(running?t.origin:t.position));positions.current.set(t.id,pos)}
      target.fromArray(t.position)
      if(step)pos.copy(target);else if(running)pos.lerp(target,damping(dt,10))
      dummy.position.copy(pos);dummy.updateMatrix();mesh.current.setMatrixAt(i,dummy.matrix)
      color.set(t.verdict==='NG'?'#e56572':t.verdict==='OK'?'#22ad98':t.verdict==='SKIPPED'?'#e5b04a':'#5b9cb8');mesh.current.setColorAt(i,color)
    })
    for(const id of positions.current.keys())if(!live.has(id))positions.current.delete(id)
    mesh.current.count=p.targets.length;mesh.current.instanceMatrix.needsUpdate=true
    if(mesh.current.instanceColor)mesh.current.instanceColor.needsUpdate=true
    if(diagnostics.enabled)diagnostics.production={time:p.time,run:p.run,positions:[...positions.current].map(([id,v])=>({id,xyz:v.toArray()}))}
  })
  return <instancedMesh ref={mesh} args={[undefined,undefined,2000]} frustumCulled={false}><boxGeometry args={[.23,.23,.23]}/><meshStandardMaterial metalness={.15} roughness={.45}/></instancedMesh>
}

const readClock=()=>{const s=useRuntime.getState().snapshot;return {time:s?.time,run:s?.run_token}}
export default function ProductionDetail({model,origin}) {
  const paused=useRuntime(s=>s.snapshot?.status!=='running')
  const context=useMemo(()=>({labels:false,smooth:true,paused,readClock}),[paused])
  return <PresentationContext.Provider value={context}><group position={origin}><Links model={model}/>{model.components.map(c=><Asset key={c.id} component={c}/>)}<ProductionParts/></group></PresentationContext.Provider>
}
