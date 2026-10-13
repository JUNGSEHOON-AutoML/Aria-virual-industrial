import {BRAND_ASSETS} from '../brand/identity'
import { Suspense, useMemo } from 'react'
import { useLoader } from '@react-three/fiber'
import { Html, RoundedBox } from '@react-three/drei'
import { ColladaLoader } from 'three/examples/jsm/loaders/ColladaLoader.js'
import * as THREE from 'three'
import conveyor from '../../../assets/cad/conveyor/dt_v1/dims.json'
import booth from '../../../assets/cad/inspection_booth/dt_v1/dims.json'
import diverter from '../../../assets/cad/diverter/dt_v1/dims.json'
import robotPose from '../d0/robot-pose.json'
import T from '../brand/cnotta.tokens.json'
import {Site} from './Site'

const C={ground:T.surface,floor:T.floor,line:T.line,blue:T['equip-frame'],dark:T.brand.ink,white:T.equip,box:T.cardboard,orange:T.human,tree:T.foliage,ink:T.brand.ink,primary:T.brand.primary}

const material = color => <meshStandardMaterial color={color} roughness={.85} metalness={0}/>
function Box({at=[0,0,0],size,color=C.white,radius=.08,rotation,...props}) {
 return <RoundedBox position={at} args={size} radius={Math.min(radius,...size.map(x=>x/3))} smoothness={2} rotation={rotation} castShadow receiveShadow {...props}>{material(color)}</RoundedBox>
}
function Cylinder({at,r=.1,h=.5,color=C.blue,rotation,name}) {return <mesh name={name} position={at} rotation={rotation} castShadow receiveShadow><cylinderGeometry args={[r,r,h,16]}/>{material(color)}</mesh>}
function Label({at,children}) {return <Html position={at} center zIndexRange={[2,0]} style={{pointerEvents:'none'}}><div className="scene-label">{children}</div></Html>}
function Grounded({name,x=0,z=0,children}) {return <group name={name} position={[x,0,z]} userData={{grounded:true,groundY:0}}>{children}</group>}
function Carton({x=0,z=0,bottom=0,size=.5}) {return <group position={[x,bottom,z]} name="fixed-carton" userData={{staticProp:true}}><Box at={[0,size/2,0]} size={[size,size,size]} color={C.box}/><Box at={[0,size+.002,0]} size={[.07,.006,size*.9]} color={C.line}/><Box at={[0,size*.5,size/2+.003]} size={[.15,.09,.006]}/></group>}
function Pallet({x,z,stack=1}) {return <Grounded name="pallet" x={x} z={z}>{[-.42,0,.42].map(a=><Box key={a} at={[a,.06,0]} size={[.17,.12,1.1]} color={C.line}/>)}{[-.45,-.225,0,.225,.45].map(a=><Box key={a} at={[0,.155,a]} size={[1.2,.07,.19]} color={C.line}/>)}{Array.from({length:stack},(_,level)=>[-.28,.28].flatMap(a=>[-.26,.26].map(b=><Carton key={`${level}-${a}-${b}`} x={a} z={b} bottom={.19+level*.5}/>)))}</Grounded>}
function Belt({x,z=0,length=conveyor.length_mm/1000,rotation=0,width=conveyor.width_mm/1000}) {
 const h=conveyor.height_mm/1000
 return <Grounded name="conveyor" x={x} z={z}><group rotation={[0,rotation,0]}>
 {[-length/2+.15,length/2-.15].flatMap(a=>[-width/2+.07,width/2-.07].map(b=><Box key={`${a}-${b}`} at={[a,(h-.14)/2,b]} size={[.1,h-.14,.1]} color={C.ink}/>))}
 <Box at={[0,h-.09,0]} size={[length,.18,width]} color={C.primary}/>
 {Array.from({length:Math.ceil(length/.17)},(_,i)=><Cylinder name="conveyor-roller" key={i} at={[-length/2+.09+i*.17,h-.04,0]} r={.04} h={width-.1} color={C.line} rotation={[Math.PI/2,0,0]}/>)}
 </group></Grounded>
}
function Booth() {
 const l=booth.length_mm/1000,w=booth.width_mm/1000,h=booth.height_mm/1000
 return <Grounded name="vision-booth" x={-3.6}>
 {[-1,1].map(sign=><Box key={sign} at={[0,(h-.2)/2,sign*(w/2-.065)]} size={[l,h-.2,.13]} color={C.blue}/>)}
 <Box at={[0,h-.1,0]} size={[l,.2,w]} color={C.white}/><Box at={[0,h-.23,0]} size={[.35,.06,.55]} color={C.line}/>
 <Box at={[0,h-.33,0]} size={[.17,.16,.18]} color={C.dark}/><Cylinder at={[0,h-.43,0]} r={.055} h={.04} color={C.ink}/>
 <Belt x={0} length={l}/><Label at={[0,2.2,0]}>VISION</Label>
 </Grounded>
}
function Cabinet({x,z}) {return <Grounded name="edge-rack" x={x} z={z}><Box at={[0,.8,0]} size={[.65,1.6,.7]} color={C.dark}/>{[.3,.6,.9,1.2].map(y=><group key={y}><Box at={[0,y,.36]} size={[.48,.2,.03]} color={C.line}/><Box at={[-.15,y,.38]} size={[.05,.025,.015]}/></group>)}<Box at={[0,1.64,0]} size={[.7,.08,.74]}/></Grounded>}
function Fence({x,z,length=4,rotation=0}) {return <Grounded name="safety-fence" x={x} z={z}><group rotation={[0,rotation,0]}>{Array.from({length:Math.ceil(length/.8)+1},(_,i)=><Box key={i} at={[-length/2+i*length/Math.ceil(length/.8),.7,0]} size={[.05,1.4,.05]} color={C.ink}/>)}{[.2,.7,1.35].map(y=><Box key={y} at={[0,y,0]} size={[length,.035,.035]} color={C.line}/>)}{Array.from({length:Math.floor(length/.2)},(_,i)=><Box key={i} at={[-length/2+.1+i*.2,.7,0]} size={[.015,1.2,.015]} color={C.line}/>)}</group></Grounded>}
const visuals=[[0,'0_0'],[1,'1_0'],[2,'2_0'],[2,'2_1'],[2,'2_2'],[3,'3_0'],[4,'4_0'],[4,'4_1'],[5,'5_0'],[6,'6_0']]
function StaticRobot() {
 const models=useLoader(ColladaLoader,visuals.map(([,name])=>`/robots/doosan_m0609/MF0609_${name}.dae`))
 const objects=useMemo(()=>models.map(m=>{const s=m.scene.clone(true);s.rotation.set(0,0,0);s.scale.setScalar(.001);const extras=[];s.traverse(o=>{if(o.isLight||o.isCamera)extras.push(o);if(o.isMesh){o.material=new THREE.MeshStandardMaterial({color:C.white,roughness:.85,metalness:0});o.castShadow=o.receiveShadow=true}});extras.forEach(o=>o.removeFromParent());return s}),[models])
 return <group position={[0,.55,0]} rotation={[-Math.PI/2,0,0]}>{objects.map((object,i)=><group key={i} matrix={new THREE.Matrix4().fromArray(robotPose.frames[visuals[i][0]])} matrixAutoUpdate={false}><primitive object={object}/></group>)}</group>
}
function RobotCell() {return <Grounded name="robot-cell" x={-5} z={-4.6}>
 <Box at={[0,.275,0]} size={[.7,.55,.7]} color={C.blue}/><Suspense fallback={null}><group name="robot-demonstration-motion"><StaticRobot/></group></Suspense>
 <Belt x={-1.5} length={1.7}/><Belt x={1.5} length={1.7}/><Fence x={0} z={-1.5} length={5}/><Fence x={-2.5} z={0} length={3} rotation={Math.PI/2}/><Fence x={2.5} z={0} length={3} rotation={Math.PI/2}/>
 <Label at={[0,2.3,-1]}>ROBOT CELL</Label>
 </Grounded>}
function Worker({x,z}) {return <Grounded name="worker" x={x} z={z}>{[-.11,.11].map(a=><group key={a}><Box at={[a,.08,.055]} size={[.16,.16,.3]} color={C.dark}/><Box at={[a,.43,0]} size={[.14,.56,.15]} color={C.ink}/></group>)}<Box at={[0,.94,0]} size={[.45,.48,.26]} color={C.orange} radius={.09}/>{[-.3,.3].map(a=><Box key={a} at={[a,.94,0]} size={[.12,.44,.14]} color={C.orange}/>)}<Cylinder at={[0,1.33,0]} r={.15} h={.28} color={C.line}/><mesh position={[0,1.49,0]} castShadow><sphereGeometry args={[.18,16,12,0,Math.PI*2,0,Math.PI/2]}/>{material(C.white)}</mesh></Grounded>}
function Rack({x,z}) {return <Grounded name="waiting-rack" x={x} z={z}>{[-1,1].flatMap(a=>[-.45,.45].map(b=><Box key={`${a}-${b}`} at={[a,1.2,b]} size={[.08,2.4,.08]} color={C.blue}/>))}{[.15,.9,1.65].map((y,i)=><group key={y}><Box at={[0,y,0]} size={[2.1,.1,1]} color={C.line}/></group>)}</Grounded>}
function Reinspection() {return <Grounded name="offline-area" x={3} z={6.2}>
 <Box at={[0,.004,0]} size={[8,.008,3.8]} color={T.brand['primary-200']}/>
 <Rack x={-2.3} z={-.5}/><Rack x={.2} z={-.5}/>
 <group position={[2.3,0,0]}>{[-.65,.65].flatMap(a=>[-.4,.4].map(b=><Box key={`${a}-${b}`} at={[a,.44,b]} size={[.09,.88,.09]} color={C.blue}/>))}<Box at={[0,.94,0]} size={[1.5,.12,1]}/><Carton bottom={1} size={.36}/><Box at={[-.5,1.2,-.24]} size={[.35,.32,.05]} color={C.dark}/></group>
 <Worker x={2.3} z={1.1}/><group position={[3.7,0,-.5]}><Box at={[0,.04,0]} size={[.6,.08,.6]} color={C.ink}/>{[-.27,.27].map(x=><Box key={x} at={[x,.35,0]} size={[.06,.7,.6]} color={C.ink}/>)}{[-.27,.27].map(z=><Box key={z} at={[0,.35,z]} size={[.6,.7,.06]} color={C.ink}/>)}</group>
 <Label at={[-1,2.9,-.3]}>OFFLINE REINSPECTION</Label>
 </Grounded>}
function Tree({x,z}) {return <Grounded name="decorative-tree" x={x} z={z}><Cylinder at={[0,.62,0]} r={.07} h={1.24} color={C.line}/><mesh position={[0,1.48,0]} scale={[.55,.8,.55]} castShadow><icosahedronGeometry args={[1,2]}/>{material(C.tree)}</mesh></Grounded>}
function Truck() {return <Grounded name="decorative-truck" x={-5} z={10.2}><Box at={[0,.95,0]} size={[3.6,1.65,1.65]}/><Box at={[-2.45,.75,0]} size={[1.15,1.25,1.6]} color={C.blue}/><Box at={[-2.46,1.04,.805]} size={[.75,.48,.015]} color={C.dark}/><Box at={[-3.035,1.04,0]} size={[.02,.48,1.3]} color={C.dark}/><Box at={[0,.49,0]} size={[3.7,.24,1.7]} color={C.dark}/>{[-2.35,.8,1.35].flatMap(x=>[-.85,.85].map(z=><Cylinder key={`${x}-${z}`} at={[x,.3,z]} r={.3} h={.16} color={C.ink} rotation={[Math.PI/2,0,0]}/>))}</Grounded>}
// Existing single-hall conveyor geometry. Model lanes are a separate Site input.
export const DEFAULT_CONVEYORS=[
 {id:'infeed',x:-7,length:6},{id:'after-vision',x:-2.2},
 {id:'cross',x:.1,z:0,length:3.6,rotation:Math.PI/2},
 ...[-1.8,0,1.8].map((z,i)=>({id:`output-${i}`,x:3.3,z,length:6})),
 {id:'offline-transfer',x:6.6,z:2.2,length:4.4,rotation:Math.PI/2},
]
export function Scene({children,origin=[0,0],rotation=0,lanes=['ccifps']}) {return <Site origin={origin} rotation={rotation} lanes={lanes}>{siteLanes=><group name="d0-static-scene" userData={{modelLanes:siteLanes}}>
 <mesh name="surface" rotation={[-Math.PI/2,0,0]} position={[0,-.015,0]}><planeGeometry args={[80,60]}/><meshBasicMaterial color={C.ground}/></mesh><mesh name="floor" rotation={[-Math.PI/2,0,0]} position={[0,-.001,1]}><planeGeometry args={[24,18]}/><meshBasicMaterial color={C.floor}/></mesh>
 <Box at={[0,.02,12]} size={[48,.04,5]} color={C.line}/>{Array.from({length:13},(_,i)=><Box key={i} at={[-22+i*3.6,.044,12]} size={[1.8,.008,.1]}/>)}
 <Grounded name="cutaway-building"><Box at={[0,1.15,-8]} size={[24,2.3,.25]} color={C.blue}/><Box at={[-12,1.15,1]} size={[.25,2.3,18]} color={C.blue}/><Box at={[0,2.35,-8]} size={[24.2,.1,.4]} color={C.dark}/><Box at={[-12,2.35,1]} size={[.4,.1,18]} color={C.dark}/>{[-9,-5,-1,3,7,10].map(x=><Box key={x} at={[x,1.6,-7.855]} size={[2.4,.65,.05]} color={C.line}/>)}<Box at={[-11.85,1.2,5.8]} size={[.05,2.4,2.5]} color={C.white}/><Html position={[-10,1.7,-7.85]} transform zIndexRange={[1,0]}><img className="wall-mark" src={BRAND_ASSETS.mark} alt="CNOTTA"/></Html></Grounded>
 {[-2,2.5].map(z=><Box key={z} at={[0,.007,z]} size={[21,.014,.07]} color={C.line}/>)}
 <group name="process-area"><RobotCell/><Cabinet x={-1.7} z={-5.4}/><Pallet x={-9.5} z={-4.5} stack={2}/>
 {DEFAULT_CONVEYORS.map(({id,...props})=><Belt key={id} {...props}/>)}<Booth/>
 <Grounded name="diverter" x={-.7}><Belt x={0} length={diverter.length_mm/1000} width={diverter.width_mm/1000}/><Box at={[0,.74,0]} size={[.7,.08,.08]} color={C.blue} rotation={[0,-.4,0]}/></Grounded>
 <Label at={[-8,1.8,0]}>INFEED</Label><Label at={[-.7,1.8,0]}>SORT</Label>
 <Pallet x={-10} z={1.7} stack={2}/>
 <Pallet x={8} z={-1.8} stack={2}/><Pallet x={9.7} z={-1.8} stack={1}/><Pallet x={8.5} z={.2} stack={1}/>
 <Fence x={7.5} z={2.5} length={2}/><Fence x={8.5} z={1.65} length={1.7} rotation={Math.PI/2}/><Box at={[7.5,.04,1.7]} size={[2,.08,1.6]} color={C.line}/><Carton x={7.4} z={1.7} bottom={.08}/>
 <Reinspection/><Pallet x={-7.5} z={5.1} stack={2}/><Pallet x={-9.2} z={5.1} stack={1}/><Worker x={-9} z={2.9}/>
 {children}</group><Truck/>{[[-15,-7],[-15,-2],[-15,4],[-15,9],[14,-7],[14,-2],[14,4],[14,9]].map(([x,z])=><Tree key={`${x}-${z}`} x={x} z={z}/>)}
 </group>}</Site>}
