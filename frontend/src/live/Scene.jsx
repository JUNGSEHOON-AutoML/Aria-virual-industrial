import React,{Suspense,useEffect,useMemo,useRef} from 'react'
import {useFrame,useLoader,useThree} from '@react-three/fiber'
import {ColladaLoader} from 'three/examples/jsm/loaders/ColladaLoader.js'
import {mergeGeometries} from 'three/examples/jsm/utils/BufferGeometryUtils.js'
import {Html} from '@react-three/drei'
import * as THREE from 'three'
import T from '../brand/cnotta.tokens.json'
import {allowed} from '../motion/registry'
import {LiveTransfer} from '../stations/Transfers'
import {Boxes} from '../campus/Geometry'

export const ROBOT_BASE=[-4.2,.99,-.35]
const visuals=[[0,'MF0609_0_0.dae'],[1,'MF0609_1_0.dae'],[2,'MF0609_2_0.dae'],[2,'MF0609_2_1.dae'],[2,'MF0609_2_2.dae'],[3,'MF0609_3_0.dae'],[4,'MF0609_4_0.dae'],[4,'MF0609_4_1.dae'],[5,'MF0609_5_0.dae'],[6,'MF0609_6_0.dae']]
const robotState=s=>s?.metrics.resources['AI-INSPECTION']?.robot
export const sceneTCP=point=>[ROBOT_BASE[0]+point[0],ROBOT_BASE[1]+point[2],ROBOT_BASE[2]-point[1]]
// INVALID prior equipment-specific CAD visual; S3 uses generic TRANSFER links.
function CADArm({store}){
 const models=useLoader(ColladaLoader,visuals.map(([,file])=>`/robots/doosan_m0609/${file}`))
 const frames=useRef([]),tool=useRef(),fingers=useRef([])
 const scenes=useMemo(()=>models.map(model=>{const scene=model.scene.clone(true);scene.rotation.set(0,0,0);scene.scale.setScalar(.001);const extras=[];scene.traverse(o=>{if(o.isLight||o.isCamera)extras.push(o)});extras.forEach(o=>o.removeFromParent());return scene}),[models])
 useFrame(()=>{
  const state=robotState(store.current.snapshot);if(!state||!allowed('live.robot'))return
  frames.current.forEach((group,i)=>{group.matrix.fromArray(state.frames[visuals[i][0]]);group.matrixWorldNeedsUpdate=true})
  tool.current.matrix.fromArray(state.tool_frame);tool.current.matrixWorldNeedsUpdate=true
  fingers.current.forEach((finger,i)=>finger.position.x=(i?1:-1)*(state.attached?.025:.048))
 })
 return <group position={ROBOT_BASE} name="live-m0609"><group rotation={[-Math.PI/2,0,0]}>
  {scenes.map((scene,i)=><group key={i} ref={e=>frames.current[i]=e} matrixAutoUpdate={false}><primitive object={scene}/></group>)}
  <group name="live-tool" ref={tool} matrixAutoUpdate={false}><mesh position={[0,0,.035]}><boxGeometry args={[.09,.055,.07]}/><meshStandardMaterial color={T.brand.ink}/></mesh>{[-1,1].map((sign,i)=><mesh key={sign} ref={e=>fingers.current[i]=e} position={[sign*.048,0,.09]}><boxGeometry args={[.012,.035,.08]}/><meshStandardMaterial color={T.ok}/></mesh>)}</group>
 </group></group>
}
function Fixtures({store}){
 const snap=store.current.snapshot;if(!snap)return null
 const positions=snap.robot_info.fixtures
 return <group name="live-cell-fixtures">
  <Boxes color={T['equip-frame']} items={[[[ROBOT_BASE[0],.5,ROBOT_BASE[2]],[.3,.98,.3]]]}/>
  {['pick','place','ng','hold'].filter(name=>positions[name]).map(name=>{const p=sceneTCP(positions[name]),color=name==='place'?T.ok:name==='ng'?T.ng:name==='hold'?T.hold:T.brand.primary
   return <group key={name} position={p}><mesh position={[0,-.1,0]}><boxGeometry args={[.18,.035,.14]}/><meshStandardMaterial color={color}/></mesh><mesh position={[0,-.19,0]}><boxGeometry args={[.035,.16,.035]}/><meshStandardMaterial color={T['equip-frame']}/></mesh><Html position={[0,-.22,0]} center zIndexRange={[5,0]}><span className="live-fixture" style={{color}}>{name==='pick'?'IN':name==='place'?'OK':name==='ng'?'NG':'HOLD'}</span></Html></group>
  })}
  <group position={sceneTCP(positions.inspect)}><mesh position={[0,.13,-.17]}><boxGeometry args={[.18,.14,.14]}/><meshStandardMaterial color={T.brand.ink}/></mesh><mesh position={[0,.13,-.08]} rotation={[Math.PI/2,0,0]}><cylinderGeometry args={[.035,.035,.035,12]}/><meshStandardMaterial color={T.brand.primary}/></mesh></group>
 </group>
}
// INVALID legacy inspection-arm carrying visualization, retained for provenance.
function LegacyInspectionParts({store,onSelect}){
 const mesh=useRef(),ids=useRef([]),helper=useMemo(()=>new THREE.Object3D(),[]),color=useMemo(()=>new THREE.Color(),[])
 const geometry=useMemo(()=>{const body=new THREE.CylinderGeometry(.043,.045,.12,12),neck=new THREE.CylinderGeometry(.019,.027,.04,12);neck.translate(0,.08,0);const result=mergeGeometries([body,neck]);body.dispose();neck.dispose();return result},[])
 useEffect(()=>()=>geometry.dispose(),[geometry])
 useFrame(()=>{
  const s=store.current.snapshot;if(!s||!mesh.current||!allowed('live.parts'))return
  const components=Object.fromEntries(s.model.components.map(c=>[c.id,c])),counts={},audit=[]
  s.parts.forEach((part,i)=>{
   const c=components[part.component],rank=counts[c.id]||0;counts[c.id]=rank+1
   let p=[c.position[0],.83,c.position[2]+rank*.16],tcp=null
   if(part.robot){
    const fixture=part.released_tcp||s.robot_info.fixtures.pick
    p=sceneTCP(part.robot.attached?part.robot.tcp:fixture)
    if(part.robot.attached)tcp=sceneTCP(part.robot.tcp)
   }else if(c.kind==='Conveyor'){
    const f=part.due>part.entered?THREE.MathUtils.clamp((s.time-part.entered)/(part.due-part.entered),0,1):1
    p[0]+=(f-.5)*c.length
   }else p[0]-=rank*.15
   helper.position.fromArray(p);helper.rotation.set(0,0,0);helper.scale.set(1,1,1);helper.updateMatrix();mesh.current.setMatrixAt(i,helper.matrix)
   color.set(part.verdict==='NG'?T.ng:part.verdict==='OK'?T.ok:T.cardboard);mesh.current.setColorAt(i,color)
   audit.push({id:part.id,position:p,tcp,gripper:part.robot?.gripper,attached:!!part.robot?.attached,stage:part.robot?.stage,verdict:part.verdict})
  })
  ids.current=s.parts;mesh.current.count=s.parts.length;mesh.current.instanceMatrix.needsUpdate=true;if(mesh.current.instanceColor)mesh.current.instanceColor.needsUpdate=true
  window.__live={...window.__live,render:{time:s.time,parts:audit,wip:s.metrics.wip,sequence:s.sequence,robot:robotState(s)}}
 })
 return <instancedMesh name="live-parts" ref={mesh} args={[geometry,undefined,128]} frustumCulled={false} onClick={e=>{e.stopPropagation();onSelect(ids.current[e.instanceId])}}><meshStandardMaterial roughness={.3} metalness={.08}/></instancedMesh>
}
function FixedCameraParts({store,onSelect}){
 const mesh=useRef(),ids=useRef([]),helper=useMemo(()=>new THREE.Object3D(),[]),color=useMemo(()=>new THREE.Color(),[])
 const geometry=useMemo(()=>{const body=new THREE.CylinderGeometry(.043,.045,.12,12),neck=new THREE.CylinderGeometry(.019,.027,.04,12);neck.translate(0,.08,0);const result=mergeGeometries([body,neck]);body.dispose();neck.dispose();return result},[])
 useEffect(()=>()=>geometry.dispose(),[geometry])
 useFrame(()=>{
  const s=store.current.snapshot;if(!s||!mesh.current||!allowed('live.parts'))return
  const components=Object.fromEntries(s.model.components.map(c=>[c.id,c])),counts={},audit=[]
  s.parts.forEach((part,i)=>{
   const c=components[part.component],rank=counts[c.id]||0;counts[c.id]=rank+1
   let p=[c.position[0],.83,c.position[2]+rank*.16],tcp=null
   if(part.robot){p=[-3.6,.85,0]}else if(c.kind==='Conveyor'){
    const f=part.due>part.entered?THREE.MathUtils.clamp((s.time-part.entered)/(part.due-part.entered),0,1):1
    p[0]+=(f-.5)*c.length
   }else p[0]-=rank*.15
   helper.position.fromArray(p);helper.rotation.set(0,0,0);helper.scale.set(1,1,1);helper.updateMatrix();mesh.current.setMatrixAt(i,helper.matrix)
   color.set(part.verdict==='NG'?T.ng:part.verdict==='OK'?T.ok:T.cardboard);mesh.current.setColorAt(i,color)
   audit.push({id:part.id,position:p,tcp,gripper:null,attached:false,stage:part.robot?'FIXED_CAMERA':part.phase,verdict:part.verdict})
  })
  ids.current=s.parts;mesh.current.count=s.parts.length;mesh.current.instanceMatrix.needsUpdate=true;if(mesh.current.instanceColor)mesh.current.instanceColor.needsUpdate=true
  window.__live={...window.__live,render:{time:s.time,parts:audit,wip:s.metrics.wip,sequence:s.sequence,robot:robotState(s)}}
 })
 return <instancedMesh name="live-parts" ref={mesh} args={[geometry,undefined,128]} frustumCulled={false} onClick={e=>{e.stopPropagation();onSelect(ids.current[e.instanceId])}}><meshStandardMaterial roughness={.3} metalness={.08}/></instancedMesh>
}
function Patrol({store,index}){
 const root=useRef(),legs=useRef([]),arms=useRef([]),label=useRef()
 useFrame(()=>{
  const s=store.current.snapshot,r=s?.patrol.robots[index];if(!r||!allowed('live.patrol'))return
  root.current.position.fromArray(r.position);root.current.rotation.y=r.heading
  const moving=['PATROLLING','RESPONDING'].includes(r.state)
  legs.current.forEach((o,i)=>o.rotation.x=moving?Math.sin(r.phase+i*Math.PI)*.35:0)
  arms.current.forEach((o,i)=>o.rotation.x=moving?-Math.sin(r.phase+i*Math.PI)*.3:['DIAGNOSING','REPAIRING','VERIFYING'].includes(r.state)?-.7:0)
  if(label.current)label.current.textContent=`${r.id} · ${r.state}`
 })
 return <group ref={root} name={`live-patrol-${index}`}>
  <Boxes color={T['equip-frame']} items={[[[0,1.05,0],[.36,.48,.24]],[[0,1.48,0],[.24,.22,.2]]]}/><Boxes color={T.brand.ink} items={[[[0,1.48,.11],[.2,.07,.02]]]}/>
  {[-1,1].map((side,i)=><React.Fragment key={side}><group ref={e=>legs.current[i]=e} position={[side*.1,.8,0]}><Boxes color={T['text-2']} items={[[[0,-.35,0],[.13,.7,.13]],[[0,-.72,.055],[.16,.12,.25]]]}/></group><group ref={e=>arms.current[i]=e} position={[side*.24,1.25,0]}><Boxes color={T['equip-frame']} items={[[[0,-.24,0],[.12,.5,.12]]]}/></group></React.Fragment>)}
  <Html position={[0,1.9,0]} center zIndexRange={[4,0]}><span ref={label} className="live-patrol-label"/></Html>
 </group>
}
export function LiveScene({live,onSelect}){
 const {invalidate}=useThree()
 useEffect(()=>{live.store.current.listeners.add(invalidate);return()=>live.store.current.listeners.delete(invalidate)},[live.store,invalidate])
 if(!live.snapshot)return null
 return <group name="live-ops"><LiveTransfer live={live}/><FixedCameraParts store={live.store} onSelect={onSelect}/>{[0,1].map(i=><Patrol key={i} index={i} store={live.store}/>)}</group>
}
