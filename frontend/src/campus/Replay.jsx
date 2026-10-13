import React,{useRef,useLayoutEffect,useMemo} from 'react'
import {Html} from '@react-three/drei'
import {useThree} from '@react-three/fiber'
import * as THREE from 'three'
import T from '../brand/cnotta.tokens.json'
import {activeAt,positionAt,queueAt} from '../cnotta/replay'
import {halls,laneZ,modelName} from './layout'

export function laneSnapshots(replay){return halls.flatMap(site=>site.lanes.map((selector,index)=>{const lane=replay.catalog?.sites.find(s=>s.id===site.id)?.lanes.find(l=>l.selector===selector),timeline=replay.timelines[lane?.run?.run_id];return {site,index,selector,lane,timeline,active:timeline?activeAt(timeline.parts,replay.time):[],queue:timeline?queueAt(timeline.queue,replay.time):null}}))}
function world(site,x,y,z){const c=Math.cos(site.rotation),s=Math.sin(site.rotation);return [site.origin[0]+c*x+s*z,y,site.origin[1]-s*x+c*z]}
export function CampusParts({replay,focus,onSelect}){
 const parts=useRef(),queues=useRef();const {invalidate}=useThree()
 const snapshots=useMemo(()=>laneSnapshots(replay),[replay.catalog,replay.timelines,replay.time])
 const visible=snapshots.filter(s=>s.site.id===focus)
 const capacity=Math.max(1,Object.values(replay.timelines).reduce((n,t)=>n+t.parts.length,0))
 useLayoutEffect(()=>{const d=new THREE.Object3D();let partN=0,queueN=0;const picking=[],positions=[],audit=[]
  for(const s of snapshots){audit.push({site:s.site.id,selector:s.selector,run_id:s.lane?.run?.run_id,time:replay.time,active_ids:s.active.map(p=>p.part_id),queue:s.queue,ng_count:s.timeline?.parts.filter(p=>p.inspection_time!=null&&p.inspection_time<=replay.time&&p.verdict==='NG').length??null})
   if(s.site.id!==focus)continue
   const z=laneZ(s.site,s.index)
   for(const p of s.active){const xyz=positionAt(p,replay.time,replay.illustrate);const pos=world(s.site,xyz[0],xyz[1],z+xyz[2]*.32);d.position.fromArray(pos);d.scale.set(.25,.25,.25);d.rotation.set(0,s.site.rotation,0);d.updateMatrix();parts.current.setMatrixAt(partN,d.matrix);parts.current.setColorAt(partN,new THREE.Color(p.inspection_time!=null&&p.inspection_time<=replay.time?(p.verdict==='NG'?T.ng:p.verdict==='OK'?T.ok:T.hold):T.cardboard));partN++;picking.push({part:p,timeline:s.timeline,lane:s.selector});positions.push(pos)}
   for(let n=0;n<(s.queue||0);n++){const overflow=n>=18,j=n-18;const x=overflow?10.3+(j%20)*.28:11.3+(n%6)*.54;const yy=overflow?.23+Math.floor(j/200)*.25:.5+Math.floor(n/6)*.72;const zz=overflow?z+3.1+Math.floor((j%200)/20)*.28:z+1.9;d.position.fromArray(world(s.site,x,yy,zz));d.scale.setScalar(overflow?.23:.43);d.updateMatrix();queues.current.setMatrixAt(queueN++,d.matrix)}
  }
  parts.current.count=partN;parts.current.instanceMatrix.needsUpdate=true;if(parts.current.instanceColor)parts.current.instanceColor.needsUpdate=true;queues.current.count=queueN;queues.current.instanceMatrix.needsUpdate=true;parts.current.userData.picking=picking;invalidate();window.__campus={...window.__campus,snapshots:audit,positions,renderedParts:partN,renderedQueue:queueN}
 },[snapshots,focus,replay.illustrate,capacity,invalidate])
 return <><instancedMesh ref={parts} name="campus-replay-parts" args={[undefined,undefined,capacity]} frustumCulled={false} onClick={e=>{e.stopPropagation();const p=parts.current.userData.picking[e.instanceId];if(p)onSelect(p)}}><boxGeometry/><meshStandardMaterial roughness={.85}/></instancedMesh><instancedMesh ref={queues} name="campus-queue-boxes" args={[undefined,undefined,capacity]} frustumCulled={false}><boxGeometry/><meshStandardMaterial color={T.cardboard} roughness={.85}/></instancedMesh>{visible.map(s=><Html key={s.selector} position={world(s.site,-11.5,1.4,laneZ(s.site,s.index)-1.5)} center zIndexRange={[8,1]}><div className="lane-label"><b>{modelName(s.selector)}</b><span>{s.timeline?`NG ${s.timeline.parts.filter(p=>p.verdict==='NG'&&p.inspection_time!=null&&p.inspection_time<=replay.time).length} · 대기 ${s.queue}`:s.lane?.run?'검증·로딩 중':'완료 대기'}</span></div></Html>)}</>
}

export function CampusRollers({time,focus,illustrate}){
 const ref=useRef(),{invalidate}=useThree();const geometry=useMemo(()=>new THREE.CylinderGeometry(.045,.045,.68,6).rotateX(Math.PI/2),[])
 useLayoutEffect(()=>{const d=new THREE.Object3D();let n=0
  for(const site of halls){if(site.id!==focus)continue;for(let lane=0;lane<site.lanes.length;lane++){const z=laneZ(site,lane);for(let i=0;i<65;i++){d.position.fromArray(world(site,-11.85+i*.21,.745,z));d.rotation.set(0,site.rotation,illustrate?time*2*Math.PI:0);d.updateMatrix();ref.current.setMatrixAt(n++,d.matrix)}}}
  ref.current.count=n;ref.current.instanceMatrix.needsUpdate=true;invalidate()
 },[time,focus,illustrate,invalidate])
 return <instancedMesh ref={ref} name="campus-rollers" args={[geometry,undefined,600]} frustumCulled={false}><meshStandardMaterial color={T.line} emissive={T.line} emissiveIntensity={.3} roughness={.85}/></instancedMesh>
}
