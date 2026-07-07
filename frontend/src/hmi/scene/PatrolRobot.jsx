// PatrolRobot — 공장 순찰 로봇 개(4족 프록시). 명세 Prompt 2·3.
// 웨이포인트 무한 순찰(Lerp) + 머리 시야 프러스텀 + YOLO 탐지 3D 매핑.
// yolo_detection(실 WS) 수신 시: 머리 포즈에서 바닥 좌표 역산 → 적색 박스+라벨, 정지+lookAt.
import { useRef, useState, useEffect, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import { useSignalStore } from '../signalStore'

// 통로 순찰 경로(직사각 루프). 컨베이어 행 사이 통로.
const WAYPOINTS = [
  [-12, 0, 5.5], [12, 0, 5.5], [12, 0, 8.5], [-12, 0, 8.5],
]
const SPEED = 2.4   // m/s

// bbox(정규 0..1) + 머리 포즈 → 바닥 월드 좌표 역산
function bboxToFloor(headPos, headingY, bbox) {
  const [x = 0.5, y = 0.5, w = 0, h = 0] = Array.isArray(bbox) ? bbox : []
  const cx = x + w / 2, cy = y + h / 2
  const lateral = (cx - 0.5) * 5.0          // 좌우 ±2.5m
  const dist = 2.0 + (1 - cy) * 5.0          // 가까울수록(cy↑) 짧게, 멀수록 길게
  const fwd = new THREE.Vector3(Math.sin(headingY), 0, Math.cos(headingY))
  const right = new THREE.Vector3(Math.cos(headingY), 0, -Math.sin(headingY))
  return new THREE.Vector3(
    headPos.x + fwd.x * dist + right.x * lateral, 0.02,
    headPos.z + fwd.z * dist + right.z * lateral)
}

function Leg({ x, z, legRef }) {
  return (
    <mesh ref={legRef} position={[x, 0.22, z]} castShadow>
      <cylinderGeometry args={[0.035, 0.03, 0.44, 8]} />
      <meshStandardMaterial color="#2c3444" metalness={0.6} roughness={0.4} />
    </mesh>
  )
}

export default function PatrolRobot() {
  const detections = useSignalStore(s => s.detections) || []
  const connected = useSignalStore(s => s.wsStatus) === 'open'
  const dogRef = useRef()
  const frustRef = useRef()
  const wpIndex = useRef(0)
  const legRefs = [useRef(), useRef(), useRef(), useRef()]
  const [boxes, setBoxes] = useState([])    // {id, pos:[x,y,z], cls, conf}
  const lastRx = useRef(0)

  // 실 yolo_detection 수신 → 바닥 좌표 역산하여 박스 생성(클라 위조 없음)
  useEffect(() => {
    if (!detections.length) return
    const latest = detections[0]
    if (!latest._rx || latest._rx === lastRx.current) return
    lastRx.current = latest._rx
    const dog = dogRef.current
    if (!dog) return
    const headPos = new THREE.Vector3(dog.position.x, 0.5, dog.position.z)
    const pos = bboxToFloor(headPos, dog.rotation.y, latest.bbox)
    setBoxes(prev => [{
      id: latest._rx, pos: [pos.x, pos.y, pos.z],
      cls: latest.class || latest.cls || 'object', conf: latest.confidence ?? latest.conf ?? 0,
    }, ...prev].slice(0, 6))
  }, [detections])

  // 최근(4s 내) 탐지가 있으면 정지+lookAt
  const activeBox = boxes.length && (Date.now() - boxes[0].id < 4000) ? boxes[0] : null

  useFrame((_, dt) => {
    const dog = dogRef.current
    if (!dog || !connected) return     // 끊기면 freeze

    if (activeBox) {
      // 정지 + 탐지 지점 바라보기
      const dx = activeBox.pos[0] - dog.position.x, dz = activeBox.pos[2] - dog.position.z
      if (Math.abs(dx) + Math.abs(dz) > 0.01) dog.rotation.y = Math.atan2(dx, dz)
    } else {
      // 웨이포인트 순찰
      const wp = WAYPOINTS[wpIndex.current]
      const dx = wp[0] - dog.position.x, dz = wp[2] - dog.position.z
      const d = Math.hypot(dx, dz)
      if (d < 0.3) { wpIndex.current = (wpIndex.current + 1) % WAYPOINTS.length }
      else {
        dog.position.x += (dx / d) * SPEED * dt
        dog.position.z += (dz / d) * SPEED * dt
        dog.rotation.y = Math.atan2(dx, dz)
      }
      // 다리 보행 애니메이션
      const t = performance.now() / 1000
      legRefs.forEach((r, i) => { if (r.current) r.current.position.y = 0.22 + Math.sin(t * 8 + i * Math.PI / 2) * 0.04 })
    }
  })

  return (
    <>
      <group ref={dogRef} position={[-12, 0, 5.5]}>
        {/* 몸통 */}
        <mesh position={[0, 0.46, 0]} castShadow>
          <boxGeometry args={[0.62, 0.26, 0.30]} />
          <meshStandardMaterial color="#3a4456" metalness={0.7} roughness={0.32} />
        </mesh>
        {/* 머리 */}
        <group position={[0, 0.54, 0.34]}>
          <mesh castShadow>
            <boxGeometry args={[0.20, 0.18, 0.24]} />
            <meshStandardMaterial color="#2a3242" metalness={0.7} roughness={0.3} />
          </mesh>
          {/* 카메라 렌즈(시안) */}
          <mesh position={[0, 0, 0.14]}>
            <sphereGeometry args={[0.045, 12, 12]} />
            <meshStandardMaterial color="#1FB8CD" emissive="#1FB8CD" emissiveIntensity={1.0} />
          </mesh>
          {/* 시야 프러스텀(반투명 콘) — 머리에서 전방 */}
          <mesh ref={frustRef} position={[0, -0.1, 2.0]} rotation={[Math.PI / 2, 0, 0]}>
            <coneGeometry args={[1.6, 4.0, 4, 1, true]} />
            <meshStandardMaterial color="#1FB8CD" transparent opacity={0.10}
              side={THREE.DoubleSide} depthWrite={false} />
          </mesh>
          <spotLight position={[0, 0, 0.2]} angle={0.5} penumbra={0.5} intensity={1.2}
            color="#cfeeff" distance={7} target-position={[0, -1, 4]} />
        </group>
        {/* 다리 4 */}
        <Leg x={-0.26} z={0.16} legRef={legRefs[0]} />
        <Leg x={0.26} z={0.16} legRef={legRefs[1]} />
        <Leg x={-0.26} z={-0.16} legRef={legRefs[2]} />
        <Leg x={0.26} z={-0.16} legRef={legRefs[3]} />
        {/* 상태 라벨 */}
        <Html position={[0, 1.0, 0]} center distanceFactor={14} style={{ pointerEvents: 'none' }}>
          <div style={{ fontFamily: "'Courier New',monospace", fontSize: 11, whiteSpace: 'nowrap',
            padding: '3px 8px', borderRadius: 5, background: 'rgba(10,14,20,0.8)',
            border: `1px solid ${activeBox ? '#f87171' : '#1FB8CD'}`,
            color: activeBox ? '#f87171' : '#1FB8CD' }}>
            🐕 순찰로봇 · {activeBox ? '이상 감지' : '순찰 중'}
          </div>
        </Html>
      </group>

      {/* YOLO 탐지 3D 박스 + 경고 라벨 (실 데이터 위치) */}
      {boxes.map(b => (
        <group key={b.id} position={b.pos}>
          <lineSegments>
            <edgesGeometry args={[new THREE.BoxGeometry(1.0, 0.8, 1.0)]} />
            <lineBasicMaterial color="#f87171" />
          </lineSegments>
          <mesh position={[0, 0.4, 0]}>
            <boxGeometry args={[1.0, 0.8, 1.0]} />
            <meshBasicMaterial color="#f87171" transparent opacity={0.08} depthWrite={false} />
          </mesh>
          <Html position={[0, 1.1, 0]} center distanceFactor={16} style={{ pointerEvents: 'none' }}>
            <div style={{ fontFamily: "'Courier New',monospace", fontSize: 11, whiteSpace: 'nowrap',
              padding: '3px 8px', borderRadius: 5, background: 'rgba(30,8,10,0.9)',
              border: '1px solid #f87171', color: '#f87171', fontWeight: 700 }}>
              ⚠ {b.cls} {b.conf ? `(${(b.conf * 100).toFixed(0)}%)` : ''}
            </div>
          </Html>
        </group>
      ))}
    </>
  )
}
