import { memo, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import { useSelection } from '../twin/selectionStore'
import { countRender } from '../twin/runtimeStore'

// Hundreds of repeated boxes share one geometry/material/draw call per batch.
export const BoxBatch=memo(function BoxBatch({items,onPick,shape='box'}) {
  const ref=useRef()
  useLayoutEffect(()=>{
    const o=new THREE.Object3D(),color=new THREE.Color()
    items.forEach((x,i)=>{o.position.fromArray(x.p);o.rotation.set(0,x.yaw||0,0);o.scale.fromArray(x.s);o.updateMatrix();ref.current.setMatrixAt(i,o.matrix);ref.current.setColorAt(i,color.set(x.c||'#d7e4eb'))})
    ref.current.instanceMatrix.needsUpdate=true;if(ref.current.instanceColor)ref.current.instanceColor.needsUpdate=true;ref.current.computeBoundingSphere()
  },[items])
  return <instancedMesh ref={ref} args={[undefined,undefined,items.length]} onClick={onPick?e=>{const id=items[e.instanceId]?.id;if(id){e.stopPropagation();onPick(id)}}:undefined}>{shape==='tree'?<coneGeometry args={[.65,1,7]}/>:<boxGeometry/>}<meshStandardMaterial roughness={.75} metalness={.06}/></instancedMesh>
})
function road(a,b,width,color,y=.035){const dx=b[0]-a[0],dz=b[2]-a[2];return {p:[(a[0]+b[0])/2,y,(a[2]+b[2])/2],s:[width,.035,Math.hypot(dx,dz)],yaw:Math.atan2(dx,dz),c:color}}
const CampusGround=memo(function CampusGround({definition}) {
  countRender('CampusGround')
  const items=useMemo(()=>{
    const b=[];const add=(p,s,c,yaw=0)=>b.push({p,s,c,yaw})
    add([0,-.4,-8],[138,.7,84],'#bfd4c1');add([0,-.02,-8],[127,.08,74],'#e8eeee')
    add([0,.025,16],[132,.06,8],'#657d8b')
    const nodes=new Map(definition.transport_nodes.map(n=>[n.id,n.position]))
    definition.transport_edges.forEach(e=>{
      const a=nodes.get(e.source),c=nodes.get(e.target);b.push(road(a,c,e.modes.includes('truck')?5.8:1.5,e.modes.includes('truck')?'#657d8b':'#b2d6d7',e.modes.includes('truck')?.055:.09))
      if(e.modes.includes('truck')){const dist=Math.hypot(c[0]-a[0],c[2]-a[2]);for(let i=3;i<dist;i+=6){const p=a.map((v,k)=>v+(c[k]-v)*i/dist);add([p[0],.1,p[2]],[.11,.016,1.8],'#ecf0e8',Math.atan2(c[0]-a[0],c[2]-a[2]))}}
    })
    definition.staging_areas.forEach(a=>{add([a.position[0],.07,a.position[2]],a.size,a.kind==='reject_hold'?'#e6c4bd':'#bfdbdb');for(const side of [-1,1]){add([a.position[0]+side*a.size[0]/2,.16,a.position[2]],[.12,.025,a.size[2]],'#fbf8e8');add([a.position[0],.16,a.position[2]+side*a.size[2]/2],[a.size[0],.025,.12],'#fbf8e8')}})
    // Gatehouse, opening, zebra crossing and fixed barriers are scenery, not live sensors.
    add([-58,1.5,23],[5,3,4],'#fafcfb');add([-58,3.2,23],[5.5,.45,4.5],'#4b8caf');add([-55,2,23],[.1,1.2,2.8],'#80adb9')
    for(let i=0;i<7;i++)add([-55+i*.7,.14,16],[.3,.02,6.2],'#f8f5e7')
    for(const x of [-63,63]){for(let z=-43;z<30;z+=3)add([x,1,z],[.11,2,.11],'#72909c');for(const y of [.6,1.7])add([x,y,-8],[.05,.06,73],'#8da3ac')}
    for(let x=-63;x<63;x+=3)add([x,1,-44],[.11,2,.11],'#72909c')
    for(const y of [.6,1.7])add([0,y,-44],[126,.06,.05],'#8da3ac')
    // Parking / truck waiting bays.
    for(let i=0;i<9;i++){const x=-40+i*8;add([x,.06,29],[6,.025,8],'#d7e0e4');for(const dx of [-3,3])add([x+dx,.1,29],[.08,.02,8],'#fcfdf5')}
    for(let i=0;i<6;i++){const x=-36+i*8;add([x,.7,29],[2.1,1.2,4.1],['#7e99a6','#fffefe','#71aab3'][i%3]);add([x,1.4,29],[1.8,.55,2.3],'#c2dce5')}
    for(let x=-49;x<61;x+=12){add([x,2.6,21],[.12,5.2,.12],'#6e8b9c');add([x,5.25,20],[.25,.2,2],'#7798ac')}
    return b
  },[definition])
  const trees=useMemo(()=>Array.from({length:24},(_,i)=>({p:[-59+i*5,2.3,-48],s:[2.2,3.4,2.2],c:i%3===0?'#639b7f':'#80ac8d'})),[])
  return <><BoxBatch items={items}/><BoxBatch items={trees} shape="tree"/></>
})
function Building({building:b,detail}) {
  const [hover,setHover]=useState(false);const pick=()=>useSelection.getState().select(b.id)
  const parts=useMemo(()=>{
    const [w,h,d]=b.size;const production=b.kind==='production';const color=production?'#397f98':'#357da7'
    const objects=[{p:[0,.12,0],s:[w,.25,d],c:'#dde5e8'},{p:[0,h/2,-d/2],s:[w,h,.35],c:'#e6eef0'},{p:[-w/2,h/2,0],s:[.3,h,d],c:'#d0e0e6'}]
    if(!production||!detail){objects.push({p:[0,h,0],s:[w+1,.4,d+1],c:color});for(let x=-w/2+1;x<w/2;x+=2.5)objects.push({p:[x,h+.24,0],s:[.06,.08,d],c:'#acc8d5'})}
    const frontH=production&&detail?1.1:h
    objects.push({p:[0,frontH/2,d/2],s:[w,frontH,.3],c:'#edf3f3'})
    for(let x=-w/2+3;x<w/2;x+=6)objects.push({p:[x,2,d/2+.2],s:[3.2,3.8,.25],c:'#6993a9'})
    return objects
  },[b,detail])
  return <group position={b.position} onClick={e=>{e.stopPropagation();pick()}} onPointerOver={e=>{e.stopPropagation();setHover(true)}} onPointerOut={()=>setHover(false)}><BoxBatch items={parts}/>{hover&&<Html position={[0,b.size[1]+1,0]} center style={{pointerEvents:'none'}} zIndexRange={[7,0]}><div className="ct-tooltip">{b.label}<small>Click to enter</small></div></Html>}</group>
}
const Docks=memo(function Docks({definition}) {
  const pieces=useMemo(()=>definition.docks.flatMap(d=>[{id:d.id,p:[d.position[0],.13,d.position[2]],s:[5,.12,10],c:'#c9d3d8'},{id:d.id,p:[d.position[0]-2.6,.19,d.position[2]],s:[.12,.03,10],c:'#ebc774'},{id:d.id,p:[d.position[0]+2.6,.19,d.position[2]],s:[.12,.03,10],c:'#ebc774'}]),[definition])
  return <BoxBatch items={pieces} onPick={id=>useSelection.getState().select(id)}/>
})
export default memo(function SiteWorld({definition,detail}) {
  countRender('SiteWorld')
  const low=useMemo(()=>definition.assets.filter(a=>!['cell','Source','Sink','Conveyor','Diverter'].includes(a.kind)).map(a=>({id:a.id,p:[a.position[0],1,a.position[2]],s:a.kind==='Buffer'?[1.8,1.5,1.4]:[2.5,2.4,2],c:a.kind==='Inspection'?'#80b9b3':'#a9bcc5'})),[definition])
  return <><CampusGround definition={definition}/>{definition.buildings.map(b=><Building key={b.id} building={b} detail={detail}/>)}<Docks definition={definition}/>{!detail&&<BoxBatch items={low} onPick={id=>useSelection.getState().select(id)}/>}</>
})
