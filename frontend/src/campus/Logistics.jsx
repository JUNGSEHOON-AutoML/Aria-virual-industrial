import React,{useEffect,useMemo,useRef,useState} from 'react'
import {useFrame,useThree} from '@react-three/fiber'
import * as THREE from 'three'
import T from '../brand/cnotta.tokens.json'
import {compilePath,samplePath} from '../motion/core.mjs'
import {allowed} from '../motion/registry'
import {subscribeFrame} from '../motion/clock'
export function useLogistics(replay,focus){
 const [data,setData]=useState(null),[state,setState]=useState(null),[error,setError]=useState(''),[policy,setPolicy]=useState('B')
 const site=replay.catalog?.sites.find(s=>s.id===(focus||'hall-bottle')),run=site?.lanes.find(l=>l.selector==='ccifps')?.run?.run_id
 useEffect(()=>{setData(null);setState(null);setError('');if(!run)return;const c=new AbortController();fetch(`/api/dt/runs/${run}/logistics?policy=${policy}`,{signal:c.signal}).then(r=>{if(!r.ok)throw Error('물류 계산 읽기 실패');return r.json()}).then(setData).catch(e=>{if(e.name!=='AbortError')setError(e.message)});return()=>c.abort()},[run,policy])
 useEffect(()=>{if(!run)return;let active=true,timer;const c=new AbortController();async function poll(){try{const r=await fetch(`/api/dt/runs/${run}/logistics/state?policy=${policy}&t=${replay.clock.read()}`,{signal:c.signal});if(!r.ok)throw Error('물류 상태 읽기 실패');const d=await r.json();if(active)setState(d)}catch(e){if(e.name!=='AbortError')setError(e.message)}if(active)timer=setTimeout(poll,1200)}poll();return()=>{active=false;c.abort();clearTimeout(timer)}},[run,policy,replay.clock])
 return {data,state,error,policy,setPolicy,run,site:site?.name}
}
function Vehicle({kind,record,clock,motion,onSelect}){
 const group=useRef(),payload=useRef(),paths=useMemo(()=>new Map(),[record]),{invalidate}=useThree()
 const sample=(points,start,end,t)=>{const key=JSON.stringify([points,start,end]);if(!paths.has(key))paths.set(key,compilePath(points,start,end,motion));return samplePath(paths.get(key),t)}
 useEffect(()=>subscribeFrame(clock,()=>{if(clock.playing)invalidate()}),[clock,invalidate])
 useFrame(()=>{if(!group.current)return;const t=clock.read();let visible=allowed('logistics.actors')&&t>=record.start,pos,yaw=0,loaded=false
  if(kind==='forklift'){visible&&=t<record.end;if(!visible){group.current.visible=false;return;}if(t<record.pickup)({position:pos,yaw}=sample(record.approach,record.start,record.pickup,t));else if(t<record.loaded)pos=record.path[0];else if(t<record.arrived)({position:pos,yaw}=sample(record.path,record.loaded,record.arrived,t));else pos=record.path.at(-1);loaded=t>=record.loaded&&t<record.end}
  else if(kind==='truck'){visible&&=record.gate_exit==null||t<record.gate_exit;if(!visible){group.current.visible=false;return;}if(t<record.load_start)({position:pos,yaw}=sample(record.inbound_path,record.start,record.load_start,t));else if(record.departure==null||t<record.departure)pos=record.path[0];else({position:pos,yaw}=sample(record.path,record.departure,record.gate_exit,t));loaded=record.loads.some(x=>x.time<=t)}
  else {visible&&=t<record.end;if(!visible){group.current.visible=false;return;}({position:pos,yaw}=sample(record.path,record.start,record.arrival??record.end,t));loaded=true}
  group.current.visible=visible;if(pos)group.current.position.fromArray(pos);group.current.rotation.y=yaw;if(payload.current)payload.current.visible=loaded
 })
 const truck=kind==='truck'||kind==='inbound',scale=truck?1:.55
 return <group ref={group} scale={scale} name={`logistics-${record.id}`} onClick={e=>{if(kind==='truck'){e.stopPropagation();onSelect(record.id)}}}>
  <mesh position={[0,.55,0]}><boxGeometry args={[2.1,.5,truck?5.6:2.2]}/><meshStandardMaterial color={T.brand.ink}/></mesh>
  <mesh position={[0,1.35,truck?2:0]}><boxGeometry args={[2,1.3,1.5]}/><meshStandardMaterial color={kind==='forklift'?T.human:T.floor}/></mesh>
  <mesh position={[0,1.65,truck?2.77:.77]}><boxGeometry args={[1.6,.45,.03]}/><meshStandardMaterial color={T.brand['primary-200']}/></mesh>
  <group ref={payload}><mesh position={[0,1.4,truck?-.9:-1.5]}><boxGeometry args={[1.8,1.5,truck?3.5:1.3]}/><meshStandardMaterial color={T.cardboard}/></mesh></group>
  {[-1.12,1.12].flatMap(x=>[-1.8,1.7].map(z=><mesh key={`${x}:${z}`} position={[x,.4,truck?z:z*.5]} rotation={[0,0,Math.PI/2]}><cylinderGeometry args={[.4,.4,.2,10]}/><meshStandardMaterial color={T.brand.ink}/></mesh>))}
 </group>
}
function Freight({data,clock}){
 const boxes=useRef(),pallets=useRef(),d=useMemo(()=>new THREE.Object3D(),[])
 const jobs=useMemo(()=>new Map(data.forklifts.map(x=>[x.pallet,x])),[data]),loads=useMemo(()=>new Map(data.trucks.flatMap(x=>x.loads).map(x=>[x.pallet,x])),[data]);const allocation=useMemo(()=>{const map=new Map();for(const pallet of data.pallets)for(const id of pallet.boxes)map.set(id,pallet.ready);return map},[data])
 useFrame(()=>{const t=clock.read(),enabled=allowed('logistics.actors');let count=0;for(const box of data.boxes){if(!enabled||box.ready>t||(allocation.get(box.id)??Infinity)<=t)continue;d.position.set(data.layout.staging[0]+(count%5)*.6,.3+Math.floor(count/25)*.5,data.layout.staging[2]+Math.floor(count%25/5)*.6);d.scale.set(.5,.5,.5);d.rotation.set(0,0,0);d.updateMatrix();boxes.current.setMatrixAt(count++,d.matrix)}boxes.current.count=count;boxes.current.instanceMatrix.needsUpdate=true;count=0
  for(const pallet of data.pallets){const job=jobs.get(pallet.id),load=loads.get(pallet.id);if(!enabled||pallet.ready>t||job.loaded<=t&&job.end>t||load?.time<=t)continue;const position=job.end<=t?data.layout.dock:data.layout.staging;d.position.set(position[0]+(count%4)*1.3,.35+Math.floor(count/16)*.7,position[2]+Math.floor(count%16/4)*1.3);d.scale.set(1.1,.6,1.1);d.updateMatrix();pallets.current.setMatrixAt(count++,d.matrix)}pallets.current.count=count;pallets.current.instanceMatrix.needsUpdate=true
 })
 return <><instancedMesh ref={boxes} args={[undefined,undefined,Math.max(1,data.boxes.length)]} frustumCulled={false}><boxGeometry/><meshStandardMaterial color={T.cardboard}/></instancedMesh><instancedMesh ref={pallets} args={[undefined,undefined,Math.max(1,data.pallets.length)]} frustumCulled={false}><boxGeometry/><meshStandardMaterial color={T.cardboard}/></instancedMesh></>
}
export function LogisticsScene({logistics,clock,onSelect}){
 const data=logistics.data;if(!data)return null
 // Membership changes on server-state updates; transforms run only in useFrame.
 const visible=rows=>rows
 return <group name="derived-logistics"><Freight data={data} clock={clock}/>{[['forklift',visible(data.forklifts,'end')],['truck',visible(data.trucks,'gate_exit')],['inbound',visible(data.inbound,'end')],['scrap',visible(data.scrap,'end')]].flatMap(([kind,rows])=>rows.map(row=><Vehicle key={row.id} kind={kind} record={row} clock={clock} motion={data.motion} onSelect={onSelect}/>))}</group>
}
export function LogisticsPanel({logistics:l,selected,onSelect}){
 const truck=l.state?.trucks.find(t=>t.id===selected)
 return <aside className="logistics-panel card"><div><b>하류 물류 · {l.site}</b><select aria-label="물류 정책" value={l.policy} onChange={e=>l.setPolicy(e.target.value)}><option value="A">정책 A</option><option value="B">정책 B 사후</option></select></div><small>용량·속도 assumed · DES 변경 없음</small>{l.error?<p role="alert">{l.error}</p>:<><p>OK 출구 {l.state?.ok_exit_count??'—'} = 출하 {l.state?.shipped_count??'—'} + 미출하 {l.state?.unshipped_count??'—'}</p><small>서버 시각 {l.state?.time?.toFixed(2)??'—'} s · CCIFPS 레인</small><select aria-label="출하 트럭" value={selected||''} onChange={e=>onSelect(e.target.value)}><option value="">트럭을 선택하세요</option>{l.state?.trucks.slice(-30).map(t=><option key={t.id} value={t.id}>{t.actor} · {t.state} · {t.id.split(':').at(-1)}</option>)}</select>{truck&&<dl><dt>적재 팔레트</dt><dd>{truck.loaded_pallets} / {truck.capacity}</dd><dt>실린 부품</dt><dd>{truck.loaded_parts} · OK</dd><dt>유출 불량 (서버 평가)</dt><dd>{truck.escaped_defects??'출발 후 확정'}</dd><dt>출발 sim 시각</dt><dd>{truck.departure?.toFixed(2)??'적재 대기'} s</dd></dl>}</>}</aside>
}
