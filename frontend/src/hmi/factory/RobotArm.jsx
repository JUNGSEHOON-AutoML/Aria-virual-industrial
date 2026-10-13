import { Suspense, useMemo, useRef, useContext } from 'react'
import { useLoader, useFrame } from '@react-three/fiber'
import { ColladaLoader } from 'three/examples/jsm/loaders/ColladaLoader'
import * as THREE from 'three'
import { PresentationContext } from './PresentationContext'

const visuals = [[0, "MF0609_0_0.dae"], [1, "MF0609_1_0.dae"], [2, "MF0609_2_0.dae"], [2, "MF0609_2_1.dae"], [2, "MF0609_2_2.dae"], [3, "MF0609_3_0.dae"], [4, "MF0609_4_0.dae"], [4, "MF0609_4_1.dae"], [5, "MF0609_5_0.dae"], [6, "MF0609_6_0.dae"]]
const urls=visuals.map(([,name])=>`/robots/doosan_m0609/${name}`)
function Pose({ values, children }) {
  const ref=useRef(), { smooth, paused, readClock }=useContext(PresentationContext)
  const pose=useMemo(()=>{const m=new THREE.Matrix4().fromArray(values),p=new THREE.Vector3(),q=new THREE.Quaternion(),s=new THREE.Vector3();m.decompose(p,q,s);return {m,p,q,s}},[values])
  const initialized=useRef(false), lastClock=useRef({})
  useFrame((_,dt)=>{
    if(!ref.current)return
    const clock=readClock?.() || {}, reset=clock.run!==lastClock.current.run, step=paused&&clock.time!==lastClock.current.time
    lastClock.current=clock
    if(!smooth||!initialized.current||reset||step){ref.current.position.copy(pose.p);ref.current.quaternion.copy(pose.q);ref.current.scale.copy(pose.s);initialized.current=true}
    else if(!paused){const a=1-Math.exp(-12*dt);ref.current.position.lerp(pose.p,a);ref.current.quaternion.slerp(pose.q,a)}
  })
  return <group ref={ref}>{children}</group>
}
function Links({ state }) {
  const models=useLoader(ColladaLoader,urls)
  const scenes=useMemo(()=>models.map(model=>{
    const scene=model.scene.clone(true)
    // URDF supplies scale and Z-up frame. Undo the loader's automatic Z→Y rotation.
    scene.rotation.set(0,0,0);scene.scale.setScalar(.001)
    const extras=[];scene.traverse(o=>{if(o.isLight||o.isCamera)extras.push(o);if(o.isMesh){o.castShadow=true;o.receiveShadow=true}})
    extras.forEach(o=>o.removeFromParent());return scene
  }),[models])
  return <group rotation={[-Math.PI/2,0,0]}>
    {scenes.map((scene,i)=><Pose key={i} values={state.frames[visuals[i][0]]}><primitive object={scene}/></Pose>)}
    <Pose values={state.tool_frame}>
      <mesh position={[0,0,.035]}><boxGeometry args={[.09,.055,.07]}/><meshStandardMaterial color="#273a49"/></mesh>
      {[-1,1].map(sign=><mesh key={sign} position={[sign*(state.attached ? .025 : .048),0,.09]}><boxGeometry args={[.012,.035,.08]}/><meshStandardMaterial color="#4cbfbc"/></mesh>)}
    </Pose>
  </group>
}
export default function RobotArm({state}) {
  if(!state)return null
  return <Suspense fallback={<mesh><boxGeometry args={[.15,.3,.15]}/><meshStandardMaterial color="#7896a0"/></mesh>}><Links state={state}/></Suspense>
}
