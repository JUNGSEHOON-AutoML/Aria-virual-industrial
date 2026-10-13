import React,{useMemo,useRef} from 'react'
import {useFrame} from '@react-three/fiber'
import {Html} from '@react-three/drei'
import * as THREE from 'three'
import {Site} from '../cnotta/Site'
import {laneZ} from '../campus/layout'
import {allowed} from '../motion/registry'
import {framesFor} from './Transfers'
import T from '../brand/cnotta.tokens.json'

function Products({data,clock}){
 const marks=useRef(),stock=useRef(),d=useMemo(()=>new THREE.Object3D(),[])
 const labels=useMemo(()=>data.parts.filter(p=>p.verdict==='NG'&&p.decision!=null&&p.arrival!=null&&p.decision<=p.arrival),[data])
 const finished=useMemo(()=>data.transfer_tasks.filter(t=>t.actor==='production'),[data])
 useFrame(()=>{
  if(!allowed('stations.products'))return
  const t=clock.read();let n=0;const represented=new Set()
  // Labels travel from the recorded marker arrival to the rewinder. The
  // assumed visual segment length never retimes a DES part or decision.
  for(const p of labels){if(p.arrival>t)break;const age=t-p.arrival;if(age>2.8/data.visual_feed_speed_mps)continue;d.position.set(-.7+age*data.visual_feed_speed_mps,1.4,.58);d.rotation.set(0,0,0);d.scale.set(.08,.02,.12);d.updateMatrix();marks.current.setMatrixAt(n++,d.matrix)}
  marks.current.count=data.class_name==='carpet'?n:0;marks.current.instanceMatrix.needsUpdate=true;n=0
  for(const task of finished){const rows=task.grade?data.grade_programs[task.grade]:data.transfer_program;const release=task.start+rows.find(r=>r.stage==='RELEASE').start;if(release>t)continue
   const slot=task.grade||'default';if(represented.has(slot))continue;represented.add(slot)
   const point=framesFor(rows[4].target,data.robot_joints).tcp
   // Same release fixture as the robot; grade pallets are distinct.
   d.position.set(6+point.x,.75+point.z,-1-point.y);d.rotation.set(Math.PI/2,0,0);d.scale.set(.16,.16,.16);d.updateMatrix();stock.current.setMatrixAt(n,d.matrix);stock.current.setColorAt(n,new THREE.Color(task.grade==='C'?T.ng:task.grade==='B'?T.hold:T.ok));n++
  }
  // Completed IDs at each fixture form an inventory, not overlapping copies.
  // A single instanced representative per grade is rendered; exact inventory
  // is supplied by the server in the station detail card.
  stock.current.count=n;stock.current.instanceMatrix.needsUpdate=true;if(stock.current.instanceColor)stock.current.instanceColor.needsUpdate=true
 })
 return <><instancedMesh name="carpet-edge-labels" ref={marks} args={[undefined,undefined,Math.max(1,labels.length)]} frustumCulled={false}><boxGeometry/><meshStandardMaterial color={T.hold}/></instancedMesh><instancedMesh name="station-completed-products" ref={stock} args={[undefined,undefined,Math.max(1,finished.length)]} frustumCulled={false}>{data.class_name==='carpet'?<cylinderGeometry args={[.55,.55,1.4,16]}/>:<boxGeometry/>}<meshStandardMaterial color={T.cardboard}/></instancedMesh>
 {data.class_name==='carpet'&&['A','B','C'].map(g=>{const p=framesFor(data.grade_programs[g][4].target,data.robot_joints).tcp;return <group key={g} position={[6+p.x,.65+p.z,-1-p.y]}><mesh><boxGeometry args={[.24,.06,.24]}/><meshStandardMaterial color={T['equip-frame']}/></mesh><Html position={[0,-.2,0]} center zIndexRange={[2,0]}><span className="station-muted">{g}</span></Html></group>})}</>
}
export function StationProducts({site,catalog,records,clock}){
 return <Site origin={site.origin} rotation={site.rotation} lanes={site.lanes}>{site.lanes.map((selector,index)=>{const id=catalog?.sites.find(s=>s.id===site.id)?.lanes.find(l=>l.selector===selector)?.run?.run_id,data=records[id];return data?<group key={selector} position={[0,0,laneZ(site,index)]}><Products data={data} clock={clock}/></group>:null})}</Site>
}
