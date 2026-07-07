// 데이터 주도 3D 인스펙션 플로어 — 부품 1개 = 실제 inspector_result 이벤트.
// 무작위 스폰 없음. 노드 미가동 시 벨트가 빈다(데이터 없으면 부품 없음 = 진짜 트윈).
import { useRef, useState, useEffect } from 'react'
import { useFrame } from '@react-three/fiber'
import { Text } from '@react-three/drei'
import { useSignalStore } from '../signalStore'

const VCOLOR = { OK: '#34d399', NG: '#f87171', SKIPPED: '#facc15' }
const LANE = { OK: -0.55, NG: 0.55, SKIPPED: 1.05 }
const CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 _-·%.'

function ConveyorBelt() {
  const stripes = useRef()
  useFrame((_, dt) => {
    if (stripes.current) {
      const d = Math.min(dt, 0.1)
      stripes.current.position.x += d * 1.4
      if (stripes.current.position.x > 0.5) stripes.current.position.x -= 0.5
    }
  })
  return (
    <group position={[0, 0.5, 0]}>
      <mesh receiveShadow><boxGeometry args={[12, 0.1, 1.6]} /><meshStandardMaterial color="#1a1c23" metalness={0.7} roughness={0.5} /></mesh>
      <mesh position={[0, 0.05, 0.81]}><boxGeometry args={[12, 0.12, 0.02]} /><meshStandardMaterial color="#3a3f4b" metalness={0.8} /></mesh>
      <mesh position={[0, 0.05, -0.81]}><boxGeometry args={[12, 0.12, 0.02]} /><meshStandardMaterial color="#3a3f4b" metalness={0.8} /></mesh>
      <group ref={stripes}>
        {[...Array(26)].map((_, i) => (
          <mesh key={i} position={[-6.25 + i * 0.5, 0.055, 0]}>
            <boxGeometry args={[0.08, 0.01, 1.56]} /><meshStandardMaterial color="#1f4861" emissive="#1f4861" emissiveIntensity={0.2} />
          </mesh>
        ))}
      </group>
    </group>
  )
}

function InspectionGantry({ pulseRef }) {
  const laser = useRef()
  const ring = useRef()
  useFrame((s) => {
    const t = s.clock.elapsedTime
    if (laser.current) laser.current.position.y = 0.55 + Math.sin(t * 6) * 0.35
    if (ring.current) {
      const since = (typeof performance !== 'undefined' ? performance.now() : 0) - (pulseRef.current || -9999)
      const hot = since < 250
      const sc = hot ? 1.0 + (250 - since) / 250 * 0.5 : 1.0
      ring.current.scale.set(sc, sc, sc)
      ring.current.material.emissiveIntensity = hot ? 1.6 : 0.6
    }
  })
  return (
    <group position={[0, 0.5, 0]}>
      <mesh position={[0, 0.6, -0.85]} castShadow><boxGeometry args={[0.15, 1.2, 0.08]} /><meshStandardMaterial color="#2d3240" metalness={0.7} /></mesh>
      <mesh position={[0, 0.6, 0.85]} castShadow><boxGeometry args={[0.15, 1.2, 0.08]} /><meshStandardMaterial color="#2d3240" metalness={0.7} /></mesh>
      <mesh position={[0, 1.2, 0]} castShadow><boxGeometry args={[0.16, 0.12, 1.78]} /><meshStandardMaterial color="#1a1d26" metalness={0.8} /></mesh>
      <mesh ref={laser} position={[0, 0.55, 0]}><boxGeometry args={[0.02, 0.015, 1.55]} /><meshBasicMaterial color="#1fb8cd" transparent opacity={0.65} /></mesh>
      <mesh ref={ring} position={[0, 0.7, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.4, 0.025, 8, 40]} /><meshStandardMaterial color="#1fb8cd" emissive="#1fb8cd" emissiveIntensity={0.6} />
      </mesh>
    </group>
  )
}

function Bins({ ok, ng, skip }) {
  const bin = (z, color, label, n) => (
    <group position={[5.6, 0.55, z]}>
      <mesh castShadow><boxGeometry args={[0.7, 0.25, 0.6]} /><meshStandardMaterial color="#1a1d24" roughness={0.6} /></mesh>
      <mesh position={[0, 0.14, 0]}><boxGeometry args={[0.72, 0.02, 0.62]} /><meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.3} /></mesh>
      <Text position={[0, 0.4, 0]} fontSize={0.16} color={color} anchorX="center" characters={CHARS}>{`${label} ${n}`}</Text>
    </group>
  )
  return <group>{bin(LANE.OK, VCOLOR.OK, 'OK', ok || 0)}{bin(LANE.NG, VCOLOR.NG, 'NG', ng || 0)}{bin(LANE.SKIPPED, VCOLOR.SKIPPED, 'SKIP', skip || 0)}</group>
}

function DataParts({ pulseRef }) {
  const parts = useRef([])
  const [, force] = useState(0)
  useEffect(() => {
    // 실제 inspector_result 이벤트마다 부품 1개 스폰 (store.scan 변화 구독)
    const unsub = useSignalStore.subscribe((s, p) => {
      if (s.scan !== p.scan && s.scan) {
        const r = s.scan
        parts.current.push({
          id: `${r.part_id || 'P'}_${parts.current.length}_${r.ts || 0}`,
          x: -5.6, lane: 0, target: LANE[r.verdict] ?? 0,
          verdict: r.verdict, defect: r.defect_class,
          color: VCOLOR[r.verdict] || '#9aa3b2', passed: false,
        })
        if (parts.current.length > 48) parts.current.shift()
      }
    })
    return unsub
  }, [])
  useFrame((_, dt) => {
    const d = Math.min(dt, 0.1)
    for (const pt of parts.current) {
      pt.x += d * 1.8
      if (pt.x >= 0) {
        pt.lane += (pt.target - pt.lane) * d * 4
        if (!pt.passed) { pt.passed = true; pulseRef.current = (typeof performance !== 'undefined' ? performance.now() : 0) }
      }
    }
    parts.current = parts.current.filter(pt => pt.x < 5.8)
    force(n => n + 1)
  })
  return (
    <group position={[0, 0.61, 0]}>
      {parts.current.map(pt => (
        <group key={pt.id} position={[pt.x, 0.09, pt.lane]}>
          <mesh castShadow>
            <boxGeometry args={[0.26, 0.18, 0.26]} />
            <meshStandardMaterial color={pt.color} emissive={pt.color} emissiveIntensity={pt.verdict ? 0.35 : 0} metalness={0.4} roughness={0.5} />
          </mesh>
          {pt.verdict === 'NG' && pt.defect && pt.x > 0.2 && (
            <Text position={[0, 0.32, 0]} fontSize={0.11} color="#fca5a5" anchorX="center" characters={CHARS}>{pt.defect}</Text>
          )}
        </group>
      ))}
    </group>
  )
}

function StatusBoard({ kpi }) {
  const verdict = kpi.state || 'IDLE'
  return (
    <group position={[0, 2.2, 0]}>
      <mesh castShadow><boxGeometry args={[3.0, 0.9, 0.05]} /><meshStandardMaterial color="#111318" metalness={0.8} roughness={0.2} /></mesh>
      <Text position={[-1.35, 0.25, 0.04]} fontSize={0.13} color="#1FB8CD" anchorX="left" characters={CHARS}>ARIA LIVE INSPECTION</Text>
      <Text position={[-1.35, -0.02, 0.04]} fontSize={0.12} color="#e2e8f0" anchorX="left" characters={CHARS}>
        {`STATE ${verdict} · YIELD ${((kpi.yield_rate ?? 0) * 100).toFixed(0)}%`}
      </Text>
      <Text position={[-1.35, -0.27, 0.04]} fontSize={0.12} color={(kpi.ack_max_ms ?? 0) < 20 ? '#34d399' : '#f87171'} anchorX="left" characters={CHARS}>
        {`ACK ${(kpi.ack_max_ms ?? 0).toFixed(1)}ms · QUEUE ${kpi.queue_depth ?? 0} · DROP ${kpi.drop_count ?? 0}`}
      </Text>
    </group>
  )
}

export default function DataFloor() {
  const kpi = useSignalStore(s => s.kpi) || {}
  const pulseRef = useRef(-9999)
  return (
    <group>
      <ConveyorBelt />
      <InspectionGantry pulseRef={pulseRef} />
      <Bins ok={kpi.n_ok} ng={kpi.n_ng} skip={kpi.n_skipped} />
      <DataParts pulseRef={pulseRef} />
      <StatusBoard kpi={kpi} />
    </group>
  )
}
