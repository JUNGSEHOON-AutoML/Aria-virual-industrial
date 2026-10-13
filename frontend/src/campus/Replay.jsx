import React,{useRef,useEffect,useMemo} from 'react'
import {Html} from '@react-three/drei'
import {useFrame,useThree} from '@react-three/fiber'
import * as THREE from 'three'
import T from '../brand/cnotta.tokens.json'
import {positionAt,queueAt} from '../cnotta/replay'
import {halls,laneZ,modelName} from './layout'
import {indexedAt,upperBound} from '../motion/core.mjs'
import {useTimelineIndexes} from '../motion/indexes'
import {allowed} from '../motion/registry'
import {subscribeFrame} from '../motion/clock'
export function laneSnapshots(replay,indexes={},time=replay.clock?.read()??replay.time){return halls.flatMap(site=>site.lanes.map((selector,index)=>{const lane=replay.catalog?.sites.find(s=>s.id===site.id)?.lanes.find(l=>l.selector===selector),timeline=replay.timelines[lane?.run?.run_id],ix=indexes[lane?.run?.run_id];return {site,index,selector,lane,timeline,active:timeline?indexedAt(timeline,ix,time):[],queue:timeline?queueAt(timeline.queue,time):null,ng:ix?upperBound(ix.inspections,time,'time'):null}}))}
export function world(site,x,y,z){const c=Math.cos(site.rotation),s=Math.sin(site.rotation);return [site.origin[0]+c*x+s*z,y,site.origin[1]-s*x+c*z]}
export function CampusParts({replay,focus,onSelect}){
 const parts=useRef(),queues=useRef(),labels=useRef({}),last=useRef(''),metrics=useRef({frames:0,js_ms:[],commits:0})
 metrics.current.commits++
 const {invalidate}=useThree(),indexes=useTimelineIndexes(replay.timelines)
 const capacity=Math.max(1,Object.values(replay.timelines).reduce((n,t)=>n+t.parts.length,0)),dummy=useMemo(()=>new THREE.Object3D(),[])
 useEffect(()=>subscribeFrame(replay.clock,()=>{if(replay.clock.playing)invalidate()}),[replay.clock,invalidate])
 useEffect(()=>{last.current='';invalidate()},[indexes,focus,replay.time,replay.illustrate,invalidate])
 useFrame(()=>{
  const time=replay.clock.read(),key=`${time}:${focus}:${replay.illustrate}`;if(last.current===key)return;last.current=key
  const start=performance.now(),snapshots=laneSnapshots(replay,indexes,time);let partN=0,queueN=0;const picking=[],positions=[],audit=[]
  for(const s of snapshots){audit.push({site:s.site.id,selector:s.selector,run_id:s.lane?.run?.run_id,time,active_ids:s.active.map(p=>p.part_id),queue:s.queue,ng_count:s.ng})
   if(s.site.id!==focus)continue
   const z=laneZ(s.site,s.index)
   if(allowed('replay.parts'))for(const p of s.active){const xyz=positionAt(p,time,replay.illustrate),pos=world(s.site,xyz[0],xyz[1],z+xyz[2]*.32);dummy.position.fromArray(pos);dummy.scale.set(.25,.25,.25);dummy.rotation.set(0,s.site.rotation,0);dummy.updateMatrix();parts.current.setMatrixAt(partN,dummy.matrix);parts.current.setColorAt(partN,new THREE.Color(p.inspection_time!=null&&p.inspection_time<=time?(p.verdict==='NG'?T.ng:p.verdict==='OK'?T.ok:T.hold):T.cardboard));partN++;picking.push({part:p,timeline:s.timeline,lane:s.selector});positions.push(pos)}
   if(allowed('replay.reinspection_queue'))for(let n=0;n<(s.queue||0);n++){const overflow=n>=18,j=n-18;const x=overflow?10.3+(j%20)*.28:11.3+(n%6)*.54;const yy=overflow?.23+Math.floor(j/200)*.25:.5+Math.floor(n/6)*.72;const zz=overflow?z+3.1+Math.floor((j%200)/20)*.28:z+1.9;dummy.position.fromArray(world(s.site,x,yy,zz));dummy.scale.setScalar(overflow?.23:.43);dummy.rotation.set(0,s.site.rotation,0);dummy.updateMatrix();queues.current.setMatrixAt(queueN++,dummy.matrix)}
   const label=labels.current[s.selector];if(label)label.textContent=s.timeline?`NG ${s.ng??'—'} · 대기 ${s.queue}`:s.lane?.run?'검증·로딩 중':'완료 대기'
  }
  parts.current.count=partN;parts.current.instanceMatrix.needsUpdate=true;if(parts.current.instanceColor)parts.current.instanceColor.needsUpdate=true;queues.current.count=queueN;queues.current.instanceMatrix.needsUpdate=true;parts.current.userData.picking=picking
  metrics.current.frames++;metrics.current.js_ms.push(performance.now()-start);if(metrics.current.js_ms.length>600)metrics.current.js_ms.shift()
  window.__campus={...window.__campus,time,snapshots:audit,positions,renderedParts:partN,renderedQueue:queueN,motionMetrics:metrics.current,workerIndexed:Object.keys(indexes).length}
 })
 const site=halls.find(s=>s.id===focus)
 return <><instancedMesh ref={parts} name="campus-replay-parts" args={[undefined,undefined,capacity]} frustumCulled={false} onClick={e=>{e.stopPropagation();const p=parts.current.userData.picking[e.instanceId];if(p)onSelect(p)}}><boxGeometry/><meshStandardMaterial roughness={.85}/></instancedMesh><instancedMesh ref={queues} name="campus-queue-boxes" args={[undefined,undefined,capacity]} frustumCulled={false}><boxGeometry/><meshStandardMaterial color={T.cardboard} roughness={.85}/></instancedMesh>{site?.lanes.map((selector,i)=><Html key={selector} position={world(site,-11.5,1.4,laneZ(site,i)-1.5)} center zIndexRange={[8,1]}><div className="lane-label"><b>{modelName(selector)}</b><span ref={el=>{labels.current[selector]=el}}>검증·로딩 중</span></div></Html>)}</>
}
// INVALID legacy clock-only roller rotation. Keep the physical rollers static.
export function CampusRollers({focus}){
 const ref=useRef(),{invalidate}=useThree();const geometry=useMemo(()=>new THREE.CylinderGeometry(.045,.045,.68,6).rotateX(Math.PI/2),[])
 useEffect(()=>{const d=new THREE.Object3D();let n=0;for(const site of halls){if(site.id!==focus)continue;for(let lane=0;lane<site.lanes.length;lane++)for(let i=0;i<65;i++){d.position.fromArray(world(site,-11.85+i*.21,.745,laneZ(site,lane)));d.rotation.set(0,site.rotation,0);d.updateMatrix();ref.current.setMatrixAt(n++,d.matrix)}}ref.current.count=n;ref.current.instanceMatrix.needsUpdate=true;invalidate()},[focus,invalidate])
 return <instancedMesh ref={ref} name="campus-rollers" args={[geometry,undefined,600]} frustumCulled={false}><meshStandardMaterial color={T.line} emissive={T.line} emissiveIntensity={.3} roughness={.85}/></instancedMesh>
}
