import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html, Line } from '@react-three/drei'
import * as THREE from 'three'
import { useFactory } from './factoryStore'
import { Solid } from './IndustrialEquipment'

function Limb({ side, leg = false, phase, moving, inspect }) {
  const angle = moving ? Math.sin(phase + (side === -1 ? Math.PI : 0)) * (leg ? .4 : -.3) : !leg && inspect ? -.8 : 0
  const length = leg ? .42 : .29
  return <group position={[side * (leg ? .15 : .32), leg ? .91 : 1.51, 0]} rotation={[angle, 0, leg ? 0 : side * -.1]}>
    <mesh><sphereGeometry args={[.09, 12, 12]} /><meshStandardMaterial color="#252d38" metalness={.7} roughness={.35} /></mesh>
    <Solid at={[0, -length / 2, 0]} size={[leg ? .17 : .13, length, .16]} color="#d8e1e5" />
    <group position={[0, -length, 0]} rotation={[leg ? Math.max(0, -angle) : -.25, 0, 0]}>
      <mesh><sphereGeometry args={[.075, 12, 12]} /><meshStandardMaterial color="#2b3844" /></mesh>
      <Solid at={[0, -length / 2, 0]} size={[leg ? .14 : .11, length, .14]} color="#bacbd3" />
      <Solid at={[0, -length, leg ? .08 : 0]} size={leg ? [.18, .1, .33] : [.12, .14, .09]} color="#2b3944" />
    </group>
  </group>
}
function Humanoid({ robot, enabled }) {
  const ref = useRef(), phase = useRef(robot.phase), previous = useRef(robot.position)
  const target = new THREE.Vector3(...robot.position)
  useFrame((_,dt) => {
    if (!ref.current) return
    ref.current.position.lerp(target,1-Math.exp(-dt*12))
    const delta = Math.atan2(Math.sin(robot.heading-ref.current.rotation.y), Math.cos(robot.heading-ref.current.rotation.y))
    ref.current.rotation.y += delta*(1-Math.exp(-dt*10))
    phase.current = robot.phase
    previous.current = robot.position
  })
  const moving = enabled && ['PATROLLING','RESPONDING'].includes(robot.state)
  const inspecting = robot.state === 'INSPECTING'
  const accent = robot.id === 'ARIA-01' ? '#1cb4cf' : '#ec9e30'
  return <group ref={ref} position={robot.position}>
    <Solid at={[0, 1.28, 0]} size={[.48, .57, .28]} color="#d8e3e7" />
    <Solid at={[0, 1.32, .15]} size={[.31, .23, .035]} color="#253e50" />
    <Solid at={[0, 1.3, .177]} size={[.16, .025, .01]} color={accent} />
    <Solid at={[0, .96, 0]} size={[.36, .15, .25]} color="#243240" />
    <Solid at={[0, 1.55, 0]} size={[.13, .16, .13]} color="#273b46" />
    <mesh position={[0, 1.77, 0]} castShadow><capsuleGeometry args={[.14, .11, 5, 12]} /><meshStandardMaterial color="#dce4e7" metalness={.5} roughness={.3} /></mesh>
    <Solid at={[0, 1.79, .13]} size={[.25, .095, .055]} color="#182f42" />
    <Solid at={[0, 1.79, .164]} size={[.16, .017, .012]} color={accent} />
    {[-1,1].flatMap(side => [false,true].map(leg => <Limb key={`${side}-${leg}`} side={side} leg={leg} phase={robot.phase} moving={moving} inspect={inspecting} />))}
    <mesh rotation={[-Math.PI/2,0,0]} position={[0,.015,0]}><ringGeometry args={[.37,.41,36]} /><meshBasicMaterial color={accent} /></mesh>
    {inspecting && <mesh position={[0,1.5,1.1]} rotation={[Math.PI/2,0,0]}><coneGeometry args={[.55,2,20,1,true]} /><meshBasicMaterial color={accent} transparent opacity={.07} depthWrite={false} side={THREE.DoubleSide} /></mesh>}
    <Html position={[0,2.2,0]} center zIndexRange={[18,0]}><div className="patrol-robot-label" style={{borderColor:accent}}><b>{robot.id}</b><span>{enabled ? robot.state : 'PAUSED'}</span><small>{robot.target || 'Patrol route'}</small></div></Html>
  </group>
}
export default function PatrolHumanoids({ visible = true }) {
  const patrol=useFactory(s=>s.patrol)
  if (!visible || !patrol) return null
  return <>{patrol.robots.map(robot => <group key={robot.id}>
    <Humanoid robot={robot} enabled={patrol.enabled} />
    {robot.state==='RESPONDING' && robot.path.length>1 && <Line points={[robot.position,...robot.path].map(p=>[p[0],.05,p[2]])} color="#ee9d31" lineWidth={1.2} dashed dashSize={.2} gapSize={.15} />}
  </group>)}</>
}
