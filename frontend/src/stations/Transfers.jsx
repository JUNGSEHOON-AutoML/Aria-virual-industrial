import React,{useMemo,useRef} from 'react'
import {useFrame} from '@react-three/fiber'
import {Html} from '@react-three/drei'
import * as THREE from 'three'
import T from '../brand/cnotta.tokens.json'
import {Site} from '../cnotta/Site'
import {laneZ} from '../campus/layout'
import {allowed} from '../motion/registry'
import {upperBound} from '../motion/core.mjs'
import {transferState} from './core.mjs'

export function framesFor(q,joints){
 const m=new THREE.Matrix4(),frames=[m.clone()]
 joints.forEach((joint,i)=>{
  const origin=new THREE.Matrix4().compose(new THREE.Vector3(...joint.xyz),new THREE.Quaternion().setFromEuler(new THREE.Euler(...joint.rpy,'ZYX')),new THREE.Vector3(1,1,1))
  m.multiply(origin).multiply(new THREE.Matrix4().makeRotationZ(q[i]));frames.push(m.clone())
 })
 const tool=m.clone().multiply(new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(Math.PI,-Math.PI/2,0,'ZYX')))
 const tcp=new THREE.Vector3(0,0,.12).applyMatrix4(tool)
 return {frames,tool,tcp}
}
function Arm({data,actor,clock,base,motionId='stations.transfer'}){
 const links=useRef([]),gripper=useRef(),fingers=useRef([]),object=useRef(),cargo=useRef([]),label=useRef(),audit=useRef()
 const rows=useMemo(()=>data.transfer_tasks.filter(t=>t.actor===actor),[data,actor])
 const yAxis=useMemo(()=>new THREE.Vector3(0,1,0),[])
 useFrame(()=>{
  if(!allowed(motionId))return
  const t=clock.read(),index=upperBound(rows,t,'start')-1,task=rows[index],active=task&&t<task.end
  const program=task?.grade?data.grade_programs[task.grade]:data.transfer_program
  const state=transferState(program,active?t-task.start:program.at(-1).start+program.at(-1).duration)
  const pose=framesFor(state.joints,data.robot_joints),fixture=framesFor(state.fixture,data.robot_joints)
  for(let i=0;i<links.current.length;i++){
   const a=new THREE.Vector3().setFromMatrixPosition(pose.frames[i]),b=new THREE.Vector3().setFromMatrixPosition(pose.frames[i+1]),d=b.clone().sub(a),length=d.length()
   const link=links.current[i];link.position.copy(a.add(b).multiplyScalar(.5));link.scale.set(1,Math.max(.025,length),1);if(length>1e-8)link.quaternion.setFromUnitVectors(yAxis,d.normalize())
  }
  gripper.current.matrix.copy(pose.tool);gripper.current.matrixWorldNeedsUpdate=true
  fingers.current.forEach((f,i)=>f.position.x=(i?1:-1)*(state.attached?.025:.06))
  const point=state.attached?pose.tcp:fixture.tcp
  cargo.current.forEach((o,i)=>{if(o)o.visible=i===(task?.kind==='roll'?2:task?.kind==='bin'?1:0)})
  object.current.visible=!!active;object.current.position.copy(point)
  if(label.current)label.current.textContent=active?`${state.stage} · ${task.object_id.split(':').slice(-2).join(':')}`:`${actor==='production'?'적재':'재검사 이송'} 대기`
  audit.current={time:t,actor,sourceEvent:active?task.source_event:null,objectId:active?task.object_id:null,stage:state.stage,gripper:state.gripper,attached:!!active&&state.attached,objectPosition:point.toArray(),tcp:pose.tcp.toArray(),joints:state.joints}
  window.__stations=window.__stations||{lanes:{}};window.__stations.transfers=window.__stations.transfers||{};window.__stations.transfers[data.run_id+':'+actor]=audit.current
 })
 return <group position={base} name={'transfer-arm-'+actor} userData={{representation:'generic code-generated links; no equipment likeness',program:'TRANSFER'}}>
  <mesh position={[0,-.35,0]}><cylinderGeometry args={[.32,.4,.7,10]}/><meshStandardMaterial color={T.brand.ink}/></mesh>
  <group rotation={[-Math.PI/2,0,0]}>{Array.from({length:6},(_,i)=><mesh key={i} ref={e=>links.current[i]=e}><cylinderGeometry args={[.055,.075,1,8]}/><meshStandardMaterial color={i%2?T['equip-frame']:T.brand.primary}/></mesh>)}
   <group ref={gripper} matrixAutoUpdate={false}><mesh position={[0,0,.04]}><boxGeometry args={[.09,.06,.08]}/><meshStandardMaterial color={T.brand.ink}/></mesh>{[-1,1].map((s,i)=><mesh key={s} ref={e=>fingers.current[i]=e} position={[s*.06,0,.1]}><boxGeometry args={[.015,.035,.08]}/><meshStandardMaterial color={T['text-2']}/></mesh>)}</group>
   <group ref={object}><mesh ref={e=>cargo.current[0]=e}><boxGeometry args={[.1,.1,.1]}/><meshStandardMaterial color={actor==='production'?T.cardboard:T.hold}/></mesh><mesh ref={e=>cargo.current[1]=e}><cylinderGeometry args={[.065,.05,.1,10,1,true]}/><meshStandardMaterial side={THREE.DoubleSide} color={T.brand['primary-200']}/></mesh><mesh ref={e=>cargo.current[2]=e} rotation={[Math.PI/2,0,0]}><cylinderGeometry args={[.08,.08,.18,12]}/><meshStandardMaterial color={T.cardboard}/></mesh></group>
  </group><Html position={[0,1.5,0]} center zIndexRange={[5,0]}><span ref={label} className="station-muted"/></Html>
 </group>
}
export function StationTransfers({site,catalog,records,clock}){
 return <Site origin={site.origin} rotation={site.rotation} lanes={site.lanes}>{site.lanes.map((selector,index)=>{
  const id=catalog?.sites.find(s=>s.id===site.id)?.lanes.find(l=>l.selector===selector)?.run?.run_id,data=records[id]
  if(!data)return null
  return <group key={selector} position={[0,0,laneZ(site,index)]}><Arm data={data} actor="production" clock={clock} base={[6,.75,-1]}/><Arm data={data} actor="reinspection" clock={clock} base={[11,.75,2.7]}/></group>
 })}</Site>
}
export function LiveTransfer({live}){
 const clock=useMemo(()=>({read:()=>live.store.current.snapshot?.time??0}),[live.store])
 const data=live.snapshot?.station
 if(!data)return null
 return <Arm data={data} actor="production" clock={clock} base={[6,.75,-1]} motionId="stations.live_transfer"/>
}
