import React,{useEffect,useMemo,useRef} from 'react'
import {useFrame,useThree} from '@react-three/fiber'
import {Html} from '@react-three/drei'
import * as THREE from 'three'
import T from '../brand/cnotta.tokens.json'
import geometry from '../../../configs/inspection_stations.json'
import {Boxes} from '../campus/Geometry'
import {laneZ} from '../campus/layout'
import {allowed} from '../motion/registry'
import {inspectionState,prepareStation} from './core.mjs'

const steel=T['equip-frame'],ink=T.brand.ink
function patternedBelt(){
 const pixels=new Uint8Array(32*32*4)
 for(let y=0;y<32;y++)for(let x=0;x<32;x++){const i=(y*32+x)*4,v=x%8===0?92:125;pixels.set([v,v+5,v+12,255],i)}
 const texture=new THREE.DataTexture(pixels,32,32);texture.wrapS=texture.wrapT=THREE.RepeatWrapping;texture.repeat.set(14/geometry.motion.texture_period_m,4);texture.needsUpdate=true
 return texture
}
function Camera({center,name,line=false,flash}){
 const point=[center[0],center[1]+geometry.camera.height_m,center[2]]
 return <group name="Booth">
  <Boxes color={steel} items={[[[center[0],1.6,-.9],[.12,3.2,.12]],[[center[0],3.1,-.45],[.12,.12,.95]]]}/>
  <Boxes color={ink} items={[[point,line?[.18,.2,1.5]:[.32,.24,.32]]]}/>
  <mesh position={[point[0],point[1]-.15,point[2]]}><cylinderGeometry args={[.075,.075,.09,12]}/><meshStandardMaterial color={T['text-2']}/></mesh>
  {line?<mesh position={[point[0],point[1]-.24,point[2]]}><boxGeometry args={[.08,.035,1.45]}/><meshStandardMaterial ref={flash} color={T.floor} emissive={T.floor} emissiveIntensity={.2}/></mesh>:<mesh position={[point[0],point[1]-.24,point[2]]} rotation={[-Math.PI/2,0,0]}><torusGeometry args={[.22,.035,6,20]}/><meshStandardMaterial ref={flash} color={T.floor} emissive={T.floor} emissiveIntensity={.2}/></mesh>}
  <perspectiveCamera name={name} position={point} rotation={[-Math.PI/2,0,0]} fov={geometry.camera.fov_deg} near={.05} far={5} userData={{datasetView:'top_down',enabled:true}}/>
 </group>
}
function Conveyor({texture,detailed,rollers}){
 const frame=useMemo(()=>{
  const boxes=[...[-.6,.6].map(z=>[[-5,.66,z],[14,.16,.12]]),...[-.52,.52].map(z=>[[-5,.98,z],[14,.05,.04]])]
  if(detailed)for(const x of [-11,-7,-3,1]){for(const z of [-.55,.55])boxes.push([[x,.34,z],[.1,.62,.1]],[[x,.045,z],[.24,.08,.24]]);boxes.push([[x,.25,0],[.08,.1,1.2]])}
  return boxes
 },[detailed])
 return <group name="MainConveyor"><Boxes color={steel} items={frame}/>
  <mesh position={[-5,.755,0]} rotation={[-Math.PI/2,0,0]}><planeGeometry args={[14,1.04]}/><meshStandardMaterial color={T['text-2']} map={texture} roughness={.9}/></mesh>
  {detailed&&<instancedMesh ref={rollers} name="driven-rollers" args={[undefined,undefined,8]}><cylinderGeometry args={[geometry.motion.roller_radius_m,geometry.motion.roller_radius_m,1.05,12]}/><meshStandardMaterial color={steel} metalness={.35} roughness={.6}/></instancedMesh>}
  <Boxes color={ink} items={[[[1.6,.48,.82],[.6,.35,.42]],[[1.98,.48,.82],[.18,.45,.45]]]}/>
 </group>
}
function Screw({disc,detailed}){
 return <group name="MainConveyor">
  <Boxes color={steel} items={[[[-2.5,.38,0],[3.4,.7,3.4]],[[1.3,.4,-1],[1,.8,1]],[[1.3,.4,1],[1,.8,1]],[[1.3,.4,2.3],[1,.8,1]]]}/>
  <group position={geometry.screw.center} ref={disc}><mesh><cylinderGeometry args={[1.65,1.65,.07,48]}/><meshStandardMaterial color={T.brand['primary-200']} transparent opacity={.45} roughness={.12}/></mesh><Boxes color={ink} items={[[[0,.05,0],[.045,.025,3.2]]]}/></group>
  <mesh position={[-6.3,.7,0]}><cylinderGeometry args={[1.2,.95,.7,24,1,true]}/><meshStandardMaterial color={steel} side={THREE.DoubleSide}/></mesh>
  {detailed&&[.55,.78,1.03].map(r=><mesh key={r} position={[-6.3,1.04,0]} rotation={[-Math.PI/2,0,0]}><torusGeometry args={[r,.035,6,32]}/><meshStandardMaterial color={ink}/></mesh>)}
  <Boxes color={ink} items={[[[-4.9,1.06,0],[1.2,.08,.16]]]}/>
 </group>
}
function Carpet({texture,rolls}){
 return <group name="MainConveyor">
  <Boxes color={steel} items={[-7.5,2.1].flatMap(x=>[-.85,.85].map(z=>[[x,.5,z],[.15,1,.15]]))}/>
  <mesh position={[-2.7,1.365,0]} rotation={[-Math.PI/2,0,0]}><planeGeometry args={[9.6,1.2]}/><meshStandardMaterial color={T.cardboard} map={texture} roughness={1}/></mesh>
  {[-7.5,2.1].map((x,i)=><group key={x} position={[x,.8,0]} rotation={[Math.PI/2,0,0]}><group ref={el=>rolls.current[i]=el}><mesh><cylinderGeometry args={[.56,.56,1.45,24]}/><meshStandardMaterial color={T.cardboard} roughness={1}/></mesh><Boxes color={ink} items={[[[.32,0,.4],[.12,1.5,.12]]]}/></group></group>)}
 </group>
}
function Lane({site,index,detail,data,readTime,onSelect,live}){
 const selector=site.lanes[index],lamp=useRef(),sensor=useRef(),flash=useRef(),pusher=useRef(),disc=useRef(),rolls=useRef([]),rollers=useRef(),hmi=useRef(),air=useRef(),hold=useRef()
 const texture=useMemo(patternedBelt,[]),dummy=useMemo(()=>new THREE.Object3D(),[])
 const liveCache=useRef({source:null,data:null})
 useEffect(()=>()=>texture.dispose(),[texture])
 const cls=site.class,trigger=cls==='screw'?[geometry.screw.center[0]-geometry.screw.radius_m,.85,0]:geometry[cls].trigger
 const name=`inspection-camera-${site.id}-${selector}`
 useFrame(()=>{
  const snapshot=live?.store.current.snapshot
  if(snapshot?.station&&liveCache.current.source!==snapshot.station)liveCache.current={source:snapshot.station,data:prepareStation(snapshot.station)}
  const t=live?snapshot?.time??0:readTime?.()??0,state=inspectionState(live?liveCache.current.data:data,t)
  if(!allowed(live?'stations.live_equipment':'stations.equipment'))return
  texture.offset.x=-state.distance/geometry.motion.texture_period_m
  if(lamp.current)lamp.current.color.set(state.lamp==='FAULT'?T.ng:state.lamp==='RUN'?T.ok:T['text-2'])
  if(sensor.current)sensor.current.emissiveIntensity=state.sensor?2:0
  if(flash.current)flash.current.emissiveIntensity=state.flash?2:.2
  if(pusher.current)pusher.current.position.z=(cls==='carpet'?state.mark:state.eject)?.32:0
  if(hold.current)hold.current.rotation.y=state.hold?Math.PI/3:0
  if(air.current)air.current.visible=cls==='screw'&&state.arrive
  if(disc.current)disc.current.rotation.y=state.distance/geometry.screw.radius_m
  rolls.current.forEach(o=>{if(o)o.rotation.y=state.distance/.56})
  if(rollers.current){for(let n=0;n<8;n++){dummy.position.set(2.5+n*.2,.73,0);dummy.rotation.set(Math.PI/2,state.rollerAngle,0);dummy.scale.set(1,1,1);dummy.updateMatrix();rollers.current.setMatrixAt(n,dummy.matrix)}rollers.current.instanceMatrix.needsUpdate=true}
  if(hmi.current)hmi.current.textContent=`${state.verdict??'대기'} · ${state.lamp}`
  window.__stations=window.__stations||{lanes:{}};window.__stations.lanes[site.id+':'+selector]={...state,time:t,textureOffset:texture.offset.x,camera:name,trigger,actuatorZ:pusher.current?.position.z,holdAngle:hold.current?.rotation.y,lightIntensity:flash.current?.emissiveIntensity,sensorIntensity:sensor.current?.emissiveIntensity,sourceRun:live?snapshot?.run_token:data?.run_id,mode:live?'live':'replay'}
 })
 const racks=[12,14.7].flatMap(x=>[.22,.95,1.68].map(y=>[[x,y,1.9],[2.1,.08,.9]]))
 const select=e=>{if(data||live){e.stopPropagation();onSelect?.({site,selector,data,live:!!live})}}
 return <group name={'Lane_'+selector} position={[0,0,laneZ(site,index)]} userData={{selector}} onClick={select}>
  {cls==='bottle'?<Conveyor texture={texture} detailed={detail} rollers={rollers}/>:cls==='screw'?<Screw disc={disc} detailed={detail}/>:<Carpet texture={texture} rolls={rolls}/>}
  <Camera center={trigger} name={name} line={cls==='carpet'} flash={flash}/>
  {cls==='bottle'&&<group><mesh position={[-3.6,1.45,0]}><boxGeometry args={[1.4,1.25,1.5]}/><meshStandardMaterial color={T.brand['primary-200']} transparent opacity={.18} depthWrite={false}/></mesh><Boxes color={T['text-2']} items={[[[-3.6,1.3,-.85],[.22,.15,.14]]]}/>{detail&&<Html position={[-3.6,1.6,-.9]} center><span className="station-muted">측면 카메라 비활성 · 데이터 없음</span></Html>}</group>}
  <group name="Diverter" position={cls==='screw'?[geometry.screw.center[0]+geometry.screw.radius_m,0,0]:geometry[cls][cls==='carpet'?'marker':'eject'].map((v,i)=>i===1?(cls==='carpet'?.53:0):v)}>
   <Boxes color={steel} items={[[[0,.8,-.8],[.3,.3,.55]]]}/><group ref={pusher} name="ng-pusher-or-labeler"><Boxes color={cls==='carpet'?T.hold:T.brand.primary} items={[[[0,.88,-.42],[.28,.12,.22]]]}/></group>
   <mesh ref={air} position={[0,.9,.3]} visible={false}><coneGeometry args={[.16,.7,6]}/><meshBasicMaterial color={T.hold} transparent opacity={.4}/></mesh>
   {cls!=='carpet'&&<group ref={hold} name="hold-gate" position={[.3,.95,.65]}><Boxes color={T.hold} items={[[[0,0,-.3],[.08,.12,.6]]]}/></group>}
   {cls!=='carpet'&&<Boxes color={T['text-2']} items={[[[.4,.4,1.2],[.8,.8,.8]]]}/>}
  </group>
  <group name="Reinspection"><Boxes name="waiting-racks" color={T['text-2']} items={racks}/><Boxes color={T.brand['primary-200']} items={[[[12.4,.091,1.6],[6.4,.014,3.3]]]}/></group>
  <Boxes color={steel} items={[[[-1.8,.6,-1.6],[.55,1.2,.5]],[[0,.6,-1.6],[.15,1.2,.15]],[[0,1.23,-1.6],[.26,.08,.2]]]}/>
  <mesh position={[0,1.31,-1.6]}><cylinderGeometry args={[.07,.07,.07,10]}/><meshStandardMaterial color={T.ng}/></mesh>
  <mesh position={[1.6,1.2,.8]}><sphereGeometry args={[.09,8,8]}/><meshStandardMaterial ref={lamp} color={T['text-2']}/></mesh>
  <group position={trigger}><mesh position={[0,.13,-.65]}><boxGeometry args={[.1,.1,.08]}/><meshStandardMaterial ref={sensor} color={T.hold} emissive={T.hold} emissiveIntensity={0}/></mesh><Boxes color={ink} items={[[[0,.13,.65],[.1,.1,.08]]]}/></group>
  {detail&&<><Boxes color={T.human} items={[[[-6,.4,2.6],[5,.06,.06]],...[-8.5,-6,-3.5].map(x=>[[x,.2,2.6],[.06,.4,.06]])]}/><Html position={[-1.8,1.7,-1.6]} center zIndexRange={[6,1]}><button className="station-hmi" disabled={!data&&!live} onClick={select}><b>{cls.toUpperCase()} · {selector}</b><span ref={hmi}>연결 대기</span><small>검사 근거 · 설정</small></button></Html></>}
  <mesh position={[trigger[0],1.4,trigger[2]]} visible={false} userData={{selectionOnly:true}} onClick={e=>{e.stopPropagation();onSelect?.({site,selector,data})}}><boxGeometry args={[2,2,2]}/><meshBasicMaterial transparent opacity={0}/></mesh>
 </group>
}
export function StationEquipment({site,focused=false,records={},catalog,clock,onSelect,live}){
 return <group name={'stations-'+site.id} visible={focused}>{site.lanes.map((selector,index)=>{
  const id=catalog?.sites.find(s=>s.id===site.id)?.lanes.find(l=>l.selector===selector)?.run?.run_id
  return <Lane key={selector} site={site} index={index} detail={focused} data={live?null:records[id]} readTime={()=>clock?.read()??0} onSelect={onSelect} live={live&&site.class==='bottle'&&selector==='ccifps'?live:null}/>
 })}</group>
}
