// StackLight — 3단 Andon 신호탑 프리팹 (녹=가동/황=검사중/적=NG경보)
// props: running, inspecting, ngAlert — 부모(QCLine)에서 flowEngine+store 기반으로 계산해 전달
import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'

const LAYERS = [
  { color: '#34d399', emissive: '#34d399', prop: 'running' },    // 녹 (하단)
  { color: '#facc15', emissive: '#facc15', prop: 'inspecting' }, // 황 (중간)
  { color: '#f87171', emissive: '#f87171', prop: 'ngAlert' },    // 적 (상단)
]
const POLE_H = 1.9
const BULB_H = 0.26
const BULB_R = 0.105

function Bulb({ color, emissive, lit }) {
  const ref = useRef()
  useFrame(({ clock }) => {
    if (!ref.current) return
    // 적색 경보: 빠른 점멸
    const blink = lit && emissive === '#f87171'
      ? 0.5 + 0.5 * Math.sign(Math.sin(clock.getElapsedTime() * 8))
      : lit ? 1 : 0
    ref.current.material.emissiveIntensity = blink * 1.8
    ref.current.material.opacity = lit ? 1.0 : 0.35
  })

  return (
    <mesh ref={ref}>
      <cylinderGeometry args={[BULB_R, BULB_R, BULB_H, 14]} />
      <meshStandardMaterial color={color} emissive={emissive} emissiveIntensity={0.12}
        transparent opacity={lit ? 1.0 : 0.35} />
    </mesh>
  )
}

export default function StackLight({ position = [0, 0, 0], running = true, inspecting = false, ngAlert = false }) {
  const props = { running, inspecting, ngAlert }

  return (
    <group position={position}>
      {/* 베이스 */}
      <mesh position={[0, 0.07, 0]}>
        <cylinderGeometry args={[0.115, 0.14, 0.14, 12]} />
        <meshStandardMaterial color="#16191f" metalness={0.5} roughness={0.5} />
      </mesh>
      {/* 기둥 */}
      <mesh position={[0, POLE_H / 2, 0]}>
        <cylinderGeometry args={[0.025, 0.025, POLE_H, 8]} />
        <meshStandardMaterial color="#2a3040" metalness={0.72} roughness={0.28} />
      </mesh>
      {/* 3단 전구 */}
      {LAYERS.map((l, i) => (
        <group key={i} position={[0, 0.32 + i * (BULB_H + 0.07), 0]}>
          <Bulb color={l.color} emissive={l.emissive} lit={!!props[l.prop]} />
        </group>
      ))}
      {/* 상단 캡 */}
      <mesh position={[0, 0.32 + 3 * (BULB_H + 0.07) - 0.06, 0]}>
        <cylinderGeometry args={[BULB_R - 0.01, BULB_R + 0.01, 0.06, 12]} />
        <meshStandardMaterial color="#1a1f2c" metalness={0.55} roughness={0.45} />
      </mesh>
    </group>
  )
}
