import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { useRuntime,diagnostics } from '../twin/runtimeStore'
import { useSelection } from '../twin/selectionStore'
import { damping } from '../twin/presentation'
export default function LogisticsActors() {
  const box=useRef(),wheel=useRef(),poses=useRef(new Map()),lastRun=useRef(),lastTime=useRef(-1),ids=useRef([])
  const root=useMemo(()=>new THREE.Object3D(),[]),part=useMemo(()=>new THREE.Object3D(),[]),matrix=useMemo(()=>new THREE.Matrix4(),[]),color=useMemo(()=>new THREE.Color(),[])
  useFrame((_,dt)=>{
    const s=useRuntime.getState().site;if(!s||!box.current||!wheel.current)return
    if(lastRun.current!==s.run_token){poses.current.clear();lastTime.current=-1;lastRun.current=s.run_token}
    const running=s.status==='running',step=!running&&s.time!==lastTime.current;lastTime.current=s.time
    let n=0,w=0;ids.current=[]
    const emit=(p,size,c,id)=>{part.position.set(...p);part.rotation.set(0,0,0);part.scale.set(...size);part.updateMatrix();matrix.multiplyMatrices(root.matrix,part.matrix);box.current.setMatrixAt(n,matrix);box.current.setColorAt(n,color.set(c));ids.current[n]=id;n++}
    const actors=[...s.trucks,...s.forklifts]
    for(const a of actors){
      if(['PLANNED','DEPARTED'].includes(a.state))continue
      let visual=poses.current.get(a.id);if(!visual){visual={position:new THREE.Vector3(...a.position),angle:a.heading};poses.current.set(a.id,visual)}
      if(step) {visual.position.set(...a.position);visual.angle=a.heading}
      else if(running){const alpha=damping(dt,12);visual.position.x+=(a.position[0]-visual.position.x)*alpha;visual.position.y+=(a.position[1]-visual.position.y)*alpha;visual.position.z+=(a.position[2]-visual.position.z)*alpha;visual.angle+=Math.atan2(Math.sin(a.heading-visual.angle),Math.cos(a.heading-visual.angle))*alpha}
      root.position.copy(visual.position);root.rotation.set(0,visual.angle,0);root.scale.set(1,1,1);root.updateMatrix()
      if(a.kind==='truck'){
        emit([0,.72,0],[2.6,.45,8.6],'#546c7d',a.id);emit([0,1.95,-1.5],[2.8,2.8,5.7],a.flow==='inbound'?'#f3f4ec':'#87b6c8',a.id);emit([0,1.55,2.6],[2.6,2.1,2.2],a.flow==='inbound'?'#3296b7':'#537a96',a.id);emit([0,2,3.72],[2.2,.7,.07],'#b7d9e3',a.id);emit([0,1.1,3.74],[2.3,.14,.08],'#e6edeb',a.id)
      }else{emit([0,.8,0],[1.45,1.25,2.05],'#e8b55d',a.id);emit([0,1.9,-.3],[1.4,.16,1.4],'#eec273',a.id);for(const x of [-.59,.59])emit([x,1.43,-.3],[.07,1.1,.08],'#567784',a.id);emit([0,1.1,1.1],[1.15,2.1,.18],'#557783',a.id);for(const x of [-.42,.42])emit([x,.32,1.6],[.14,.12,1.2],'#6b8b9b',a.id)}
      for(const z of a.kind==='truck'?[-3.4,-2.4,2.7]:[-.7,.7])for(const x of [-1,1]){part.position.set(x*(a.kind==='truck'?1.25:.7),.47,z);part.rotation.set(0,0,Math.PI/2);part.scale.set(.45,.3,.45);part.updateMatrix();matrix.multiplyMatrices(root.matrix,part.matrix);wheel.current.setMatrixAt(w++,matrix)}
    }
    for(const p of s.pallets){if(['ON_TRUCK','ON_OUTBOUND_TRUCK','IN_PROCESS'].includes(p.state))continue
      const carried=poses.current.get(p.carrier);root.position.set(...p.position);root.rotation.set(0,0,0)
      if(carried){root.position.copy(carried.position);root.rotation.y=carried.angle;root.translateZ(1.7);root.position.y+=.3}
      root.updateMatrix();emit([0,.14,0],[1.4,.25,1.2],'#bd9f6d',p.id);emit([0,.62,0],[1.2,.75,1],p.state==='HOLD'?'#d98e80':'#acc8bc',p.id)
    }
    // Rejected/held units remain separately visible; outbound pallets contain OK units only.
    const quarantined=s.metrics.reject_units+s.metrics.held_units
    root.position.set(39,0,-29);root.rotation.set(0,0,0);root.updateMatrix()
    for(let i=0;i<quarantined;i++)emit([(i%3-1)*.65,.3,Math.floor(i/3)*.65],[.5,.5,.5],'#d38c7a','REJECT-HOLD-01')
    box.current.count=n;wheel.current.count=w;box.current.instanceMatrix.needsUpdate=true;if(box.current.instanceColor)box.current.instanceColor.needsUpdate=true;wheel.current.instanceMatrix.needsUpdate=true
    if(diagnostics.enabled)diagnostics.logistics={time:s.time,poses:[...poses.current].map(([id,v])=>({id,position:v.position.toArray(),heading:v.angle})),boxes:n,wheels:w}
  })
  return <><instancedMesh ref={box} args={[undefined,undefined,180]} frustumCulled={false} onClick={e=>{e.stopPropagation();useSelection.getState().select(ids.current[e.instanceId])}}><boxGeometry/><meshStandardMaterial roughness={.55} metalness={.12}/></instancedMesh><instancedMesh ref={wheel} args={[undefined,undefined,64]} frustumCulled={false}><cylinderGeometry args={[1,1,1,10]}/><meshStandardMaterial color="#42596b" roughness={.9}/></instancedMesh></>
}
