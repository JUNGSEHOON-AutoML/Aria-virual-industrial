// 게임형 3D 공장 플로어 — factorySim 상태를 렌더. 로봇 검사셀 + 절차적 부품 흐름 + 24h 가동.
import { useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import { Text } from '@react-three/drei'
import { formatSimClock } from '../sim/factorySim'

const CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 _-·%./:'
const VCOLOR = { OK: '#34d399', NG: '#f87171' }
const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]

function cellLayout(n) {
  const cols = n <= 4 ? n : Math.ceil(n / 2)
  const rows = Math.ceil(n / cols)
  const pos = []
  for (let i = 0; i < n; i++) {
    const col = i % cols, row = Math.floor(i / cols)
    pos.push([(col - (cols - 1) / 2) * 2.6, 0, (row - (rows - 1) / 2) * 3.0])
  }
  return pos
}

const INBOUND = [-8, 0.7, 0]
function sortPos(v) { return [7.6, 0.7, v === 'NG' ? 1.3 : -1.3] }

function partPos(p, layout) {
  if (p.stage === 'inbound') return INBOUND
  const cp = layout[p.cell] || [0, 0, 0]
  const cell = [cp[0], 0.95, cp[2]]
  if (p.stage === 'toCell') return lerp(INBOUND, cell, p.progress)
  if (p.stage === 'inspect') return cell
  const sp = sortPos(p.verdict)
  if (p.stage === 'toSort') return lerp(cell, sp, p.progress)
  return sp
}

function RobotCell({ cell, pos }) {
  const arm = useRef()
  const head = useRef()
  useFrame(() => {
    const busy = !!cell.part
    const target = busy ? -0.9 : -0.15
    if (arm.current) arm.current.rotation.z += ((target) - arm.current.rotation.z) * 0.12
    if (head.current) head.current.material.emissiveIntensity = busy ? 1.4 : 0.3
  })
  return (
    <group position={[pos[0], 0, pos[2]]}>
      {/* 검사 패드 */}
      <mesh position={[0, 0.45, 0]} receiveShadow>
        <cylinderGeometry args={[0.55, 0.6, 0.1, 20]} /><meshStandardMaterial color="#1a1d26" metalness={0.6} roughness={0.4} />
      </mesh>
      {/* 로봇 베이스 */}
      <group position={[0.75, 0.5, 0]}>
        <mesh castShadow><cylinderGeometry args={[0.22, 0.28, 0.4, 12]} /><meshStandardMaterial color="#2d3240" metalness={0.7} /></mesh>
        <group ref={arm} position={[0, 0.2, 0]} rotation={[0, 0, -0.15]}>
          <mesh position={[-0.35, 0.05, 0]} castShadow><boxGeometry args={[0.8, 0.12, 0.12]} /><meshStandardMaterial color="#3a4150" metalness={0.6} /></mesh>
          <mesh ref={head} position={[-0.72, 0.05, 0]}>
            <boxGeometry args={[0.12, 0.16, 0.16]} /><meshStandardMaterial color="#1FB8CD" emissive="#1FB8CD" emissiveIntensity={0.3} />
          </mesh>
        </group>
      </group>
    </group>
  )
}

function Structure() {
  return (
    <group>
      {/* 바닥 */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]} receiveShadow>
        <planeGeometry args={[26, 16]} /><meshStandardMaterial color="#0e1016" metalness={0.2} roughness={0.9} />
      </mesh>
      {/* 통로 라인 */}
      {[-4.5, 4.5].map((z, i) => (
        <mesh key={i} position={[0, 0.012, z]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[24, 0.12]} /><meshStandardMaterial color="#f5c518" />
        </mesh>
      ))}
      {/* 기둥 + 오버헤드 빔 */}
      {[[-11, -6], [11, -6], [-11, 6], [11, 6]].map(([x, z], i) => (
        <mesh key={i} position={[x, 2.2, z]} castShadow><boxGeometry args={[0.35, 4.4, 0.35]} /><meshStandardMaterial color="#3a4150" metalness={0.4} /></mesh>
      ))}
      <mesh position={[0, 4.3, -6]}><boxGeometry args={[22.5, 0.2, 0.2]} /><meshStandardMaterial color="#3a4150" /></mesh>
      <mesh position={[0, 4.3, 6]}><boxGeometry args={[22.5, 0.2, 0.2]} /><meshStandardMaterial color="#3a4150" /></mesh>
    </group>
  )
}

function Zone({ pos, color, label }) {
  return (
    <group position={pos}>
      <mesh position={[0, 0.25, 0]}><boxGeometry args={[1.4, 0.5, 2.6]} /><meshStandardMaterial color="#14171f" metalness={0.5} roughness={0.6} /></mesh>
      <mesh position={[0, 0.51, 0]}><boxGeometry args={[1.42, 0.02, 2.62]} /><meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.3} /></mesh>
      <Text position={[0, 0.8, 0]} fontSize={0.22} color={color} anchorX="center" characters={CHARS}>{label}</Text>
    </group>
  )
}

export default function FactoryFloor({ sim, onMetrics }) {
  const [, force] = useState(0)
  const acc = useRef(0)
  const layout = useRef(cellLayout(sim.state.cells.length))
  const lastN = useRef(sim.state.cells.length)

  useFrame((_, dt) => {
    sim.tick(dt * 1000)
    if (sim.state.cells.length !== lastN.current) {
      lastN.current = sim.state.cells.length
      layout.current = cellLayout(sim.state.cells.length)
    }
    acc.current += dt
    if (acc.current > 0.4) { acc.current = 0; onMetrics && onMetrics(sim.metrics()) }
    force(n => (n + 1) % 1000000)
  })

  const cells = sim.state.cells
  const parts = sim.state.parts
  const lay = layout.current
  const m = sim.metrics()

  return (
    <group>
      <Structure />
      <Zone pos={[-8, 0, 0]} color="#9aa3b2" label="INBOUND" />
      <Zone pos={[7.6, 0, -1.3]} color="#34d399" label="OK" />
      <Zone pos={[7.6, 0, 1.3]} color="#f87171" label="NG" />
      <Zone pos={[10.4, 0, 0]} color="#1FB8CD" label="STORAGE" />

      {cells.map((c, i) => <RobotCell key={i} cell={c} pos={lay[i] || [0, 0, 0]} />)}

      {parts.map(p => {
        const pp = partPos(p, lay)
        const col = p.verdict ? VCOLOR[p.verdict] : '#9aa3b2'
        return (
          <mesh key={p.id} position={pp} castShadow>
            <boxGeometry args={[0.22, 0.22, 0.22]} />
            <meshStandardMaterial color={col} emissive={col} emissiveIntensity={p.verdict ? 0.35 : 0.05} metalness={0.4} roughness={0.5} />
          </mesh>
        )
      })}

      {/* 전광판 */}
      <group position={[0, 3.4, -5.6]}>
        <mesh><boxGeometry args={[6, 1.3, 0.05]} /><meshStandardMaterial color="#111318" metalness={0.8} roughness={0.2} /></mesh>
        <Text position={[-2.8, 0.42, 0.04]} fontSize={0.26} color="#1FB8CD" anchorX="left" characters={CHARS}>{`ARIA FACTORY  ${formatSimClock(m.timeMs)}`}</Text>
        <Text position={[-2.8, 0.02, 0.04]} fontSize={0.2} color="#e2e8f0" anchorX="left" characters={CHARS}>{`THROUGHPUT ${m.throughput}/h   OEE ${m.oee}%   DEFECT ${m.defect}%`}</Text>
        <Text position={[-2.8, -0.38, 0.04]} fontSize={0.2}
          color={m.bottleneck === 'balanced' ? '#34d399' : '#facc15'} anchorX="left" characters={CHARS}>
          {`CELLS ${m.cells}  QUEUE ${m.queue}  BOTTLENECK ${m.bottleneck.toUpperCase()}`}
        </Text>
      </group>
    </group>
  )
}
