// WorkerAgent — 유지보수 로봇(이동형 서비스 로봇 형태). 경량 프록시, 키네매틱스/물리 없음.
// 흔한 로봇 형태: 휠 베이스 + 토르소 + 머리(바이저) + 관절 팔. task에 따라 이동/수리 시연.
// signalStore.agent 구독. 끊김/리플레이 시 freeze는 상위에서 제어(여기선 이동만).
import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import { useSignalStore } from '../signalStore'
import { ASSET_GROUND } from './assetModel'

const TASK_KO = { MOVING: '이동 중', DIAGNOSING: '진단 중', REPAIRING: '수리 중', VERIFYING: '검증 중', RESOLVED: '✓ 해결완료' }

const BODY = '#dfe6ef'      // 흰색 플라스틱 셸
const DARK = '#2a3242'      // 관절/디테일
const ACCENT = '#1FB8CD'

// 자율 순찰 경로 — 컨베이어 레인을 가로지르지 않는 외곽 통로 루프(라인 침범 금지).
// 라인 범위: 메인 z≈±1.5, 병렬 z=-6/-11, x≈-10..10 → 그 바깥 직사각 둘레만 돈다.
const PATROL = [
  [-12, 0, 4.0],    // 전면-좌 (라인 앞 통로)
  [14, 0, 4.0],     // 전면-우
  [14, 0, -13.5],   // 후면-우 (병렬2 z=-11 뒤)
  [-12, 0, -13.5],  // 후면-좌
]
const SPEED = 2.6          // m/s

export default function WorkerAgent() {
  const agent = useSignalStore(s => s.agent) || {}
  const connected = useSignalStore(s => s.wsStatus) === 'open'
  const replayActive = useSignalStore(s => s.replay.active)
  const groupRef = useRef()
  const armRef = useRef()       // 관절 팔(피치)
  const headRef = useRef()      // 머리 스캔
  const sparkRef = useRef()
  const wheelL = useRef(); const wheelR = useRef()
  const wpRef = useRef(0)        // 현재 순찰 웨이포인트 인덱스

  const sparks = useMemo(() => {
    const g = new THREE.BufferGeometry(); const n = 20, a = new Float32Array(n * 3)
    for (let i = 0; i < n; i++) { a[i * 3] = (Math.random() - 0.5) * 0.4; a[i * 3 + 1] = Math.random() * 0.5; a[i * 3 + 2] = (Math.random() - 0.5) * 0.4 }
    g.setAttribute('position', new THREE.BufferAttribute(a, 3)); return g
  }, [])

  useFrame(({ clock }, dt) => {
    const g = groupRef.current
    if (!g || !connected || replayActive) return
    const t = clock.getElapsedTime()
    const atAsset = agent.targetAssetId && agent.task && agent.task !== 'IDLE'
    const traveling = agent.task === 'MOVING'
    const repairing = agent.task === 'REPAIRING'

    // ── 목표 결정: 결함 대응(자산) 우선, 아니면 공장 전체 자율 순찰 ──
    let tgt
    if (atAsset) {
      tgt = ASSET_GROUND[agent.targetAssetId] || PATROL[0]
    } else {
      const wp = PATROL[wpRef.current]
      const d = Math.hypot(wp[0] - g.position.x, wp[2] - g.position.z)
      if (d < 0.5) wpRef.current = (wpRef.current + 1) % PATROL.length   // 도착 → 다음 지점(무한 순찰)
      tgt = PATROL[wpRef.current]
    }

    // 설비 앞 작업(진단/수리/검증/해결) 중엔 정지, 이동(MOVING)·순찰 시에만 주행
    const stationary = atAsset && !traveling
    let moving = false
    if (!stationary) {
      const dx = tgt[0] - g.position.x, dz = tgt[2] - g.position.z
      const dist = Math.hypot(dx, dz)
      if (dist > 0.05) {
        const step = Math.min(dist, SPEED * dt)
        g.position.x += (dx / dist) * step
        g.position.z += (dz / dist) * step
        g.rotation.y = Math.atan2(dx, dz)
        moving = true
      }
    }

    // 바퀴 회전 / 머리 스캔 / 수리 팔·스파크
    const spin = moving ? t * 8 : 0
    if (wheelL.current) wheelL.current.rotation.x = spin
    if (wheelR.current) wheelR.current.rotation.x = spin
    if (headRef.current) headRef.current.rotation.y = Math.sin(t * 1.5) * 0.4
    if (armRef.current) armRef.current.rotation.x = repairing ? -0.6 + Math.sin(t * 6) * 0.25 : -0.2
    if (sparkRef.current) {
      sparkRef.current.visible = repairing
      sparkRef.current.rotation.y = t * 3
      sparkRef.current.scale.setScalar(0.8 + Math.sin(t * 10) * 0.2)
    }
  })

  // 순찰=시안 / 이동=청록 / 진단·검증=보라 / 수리=황 / 해결완료=녹
  const stateColor = agent.task === 'RESOLVED' ? '#34d399'
    : agent.task === 'REPAIRING' ? '#facc15'
    : (agent.task === 'DIAGNOSING' || agent.task === 'VERIFYING') ? '#a78bfa'
    : agent.task === 'MOVING' ? '#38d9f5' : ACCENT

  return (
    <group ref={groupRef} position={PATROL[0]}>
      {/* 휠 베이스(원통) */}
      <mesh position={[0, 0.16, 0]} castShadow>
        <cylinderGeometry args={[0.30, 0.34, 0.22, 20]} />
        <meshStandardMaterial color={DARK} metalness={0.6} roughness={0.4} />
      </mesh>
      {/* 바퀴 2 */}
      <mesh ref={wheelL} position={[-0.30, 0.12, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.12, 0.12, 0.06, 16]} />
        <meshStandardMaterial color="#11151d" metalness={0.5} roughness={0.6} />
      </mesh>
      <mesh ref={wheelR} position={[0.30, 0.12, 0]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.12, 0.12, 0.06, 16]} />
        <meshStandardMaterial color="#11151d" metalness={0.5} roughness={0.6} />
      </mesh>

      {/* 토르소(둥근 흰색 셸) */}
      <mesh position={[0, 0.62, 0]} castShadow>
        <capsuleGeometry args={[0.26, 0.5, 8, 18]} />
        <meshStandardMaterial color={BODY} metalness={0.2} roughness={0.5} />
      </mesh>
      {/* 가슴 디스플레이(상태색) */}
      <mesh position={[0, 0.66, 0.255]}>
        <boxGeometry args={[0.22, 0.16, 0.02]} />
        <meshStandardMaterial color="#0a0e14" emissive={stateColor} emissiveIntensity={0.6} />
      </mesh>

      {/* 머리 + 바이저 */}
      <group ref={headRef} position={[0, 1.12, 0]}>
        <mesh castShadow>
          <sphereGeometry args={[0.19, 20, 20]} />
          <meshStandardMaterial color={BODY} metalness={0.25} roughness={0.45} />
        </mesh>
        {/* 바이저(가로 발광 띠) */}
        <mesh position={[0, 0.02, 0.15]}>
          <boxGeometry args={[0.26, 0.07, 0.04]} />
          <meshStandardMaterial color="#0a0e14" emissive={ACCENT} emissiveIntensity={1.2} />
        </mesh>
      </group>

      {/* 관절 팔(어깨→팔뚝→그리퍼) */}
      <group position={[0.26, 0.82, 0.04]}>
        <group ref={armRef} rotation={[-0.2, 0, 0]}>
          <mesh position={[0, -0.18, 0]} castShadow>
            <cylinderGeometry args={[0.045, 0.045, 0.38, 10]} />
            <meshStandardMaterial color={DARK} metalness={0.6} roughness={0.4} />
          </mesh>
          {/* 그리퍼 */}
          <mesh position={[0, -0.40, 0]}>
            <boxGeometry args={[0.10, 0.08, 0.06]} />
            <meshStandardMaterial color="#1a2030" metalness={0.8} roughness={0.2} />
          </mesh>
          {/* 수리 스파크 */}
          <points ref={sparkRef} position={[0, -0.46, 0.05]} visible={false} geometry={sparks}>
            <pointsMaterial size={0.04} color="#ffd66b" transparent opacity={0.9} />
          </points>
        </group>
      </group>

      {/* 상단 상태등 */}
      <mesh position={[0, 1.34, 0]}>
        <sphereGeometry args={[0.045, 8, 8]} />
        <meshStandardMaterial color={stateColor} emissive={stateColor} emissiveIntensity={1.3} />
      </mesh>

      {/* 자율 상태 라벨(이동/수리/해결완료 시) */}
      {agent.task && agent.task !== 'IDLE' && (
        <Html position={[0, 1.7, 0]} center distanceFactor={14} style={{ pointerEvents: 'none' }}>
          <div style={{ fontFamily: "'Courier New',monospace", fontSize: 11, whiteSpace: 'nowrap',
            padding: '3px 9px', borderRadius: 6, background: 'rgba(10,14,20,0.88)',
            border: `1px solid ${stateColor}`, color: stateColor, fontWeight: 700, textAlign: 'center' }}>
            🤖 {TASK_KO[agent.task] || agent.task}
            {agent.thought && <><br /><span style={{ fontSize: 9, color: '#cbd5e1', fontWeight: 400 }}>{agent.thought}</span></>}
          </div>
        </Html>
      )}
    </group>
  )
}
