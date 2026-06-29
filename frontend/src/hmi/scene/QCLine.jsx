// QCLine — 공정 충실 검사 라인 씬 (V1→V3)
// InfeedSource → RollerConveyor → VisionBooth → Diverter → OK/NG Bin + StackLight
// 부품 흐름은 flowEngine(순수 JS), 판정 분기는 inspector_result.verdict(signalStore)
import { useRef, useState, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import { Text, Html } from '@react-three/drei'
import { useSignalStore } from '../signalStore'
import { selectKpi, selectScan } from '../signalReducer'
import { createQCFlowEngine } from './flowEngine'
import { deriveAssets, statusColor, statusKo } from './assetModel'
import { makeFloorTexture } from './textures'
import InfeedSource from './prefabs/InfeedSource'
import RollerConveyor from './prefabs/RollerConveyor'
import VisionBooth from './prefabs/VisionBooth'
import Diverter from './prefabs/Diverter'
import SortBin from './prefabs/SortBin'
import StackLight from './prefabs/StackLight'
import RobotArm from './prefabs/RobotArm'

const CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ·_-%.:/|·'

// 컨베이어 표면 높이 (롤러 센터 기준)
const H = 0.66

// 부품 위상별 3D 위치 계산
const lerp3 = (a, b, t) => [
  a[0] + (b[0] - a[0]) * t,
  a[1] + (b[1] - a[1]) * t,
  a[2] + (b[2] - a[2]) * t,
]

const WP = {
  src:        [-7.6, H, 0],
  boothIn:    [-1.4, H, 0],
  booth:      [ 0.0, H, 0],
  divert:     [ 3.6, H, 0],
  okEnd:      [ 8.8, H, 1.0],
  ngEnd:      [ 8.8, H, -1.0],
}

function partPos(p) {
  switch (p.phase) {
    case 'conveyor': return lerp3(WP.src, WP.boothIn, p.t)
    case 'dwell':    return [WP.booth[0], H + Math.sin(p.dwellT / 280) * 0.018, WP.booth[2]]
    case 'exit':     return lerp3(WP.booth, WP.divert, p.t)
    case 'ok_lane':  return lerp3(WP.divert, WP.okEnd, p.t)
    case 'ng_lane':  return lerp3(WP.divert, WP.ngEnd, p.t)
    case 'done':     return p.verdict === 'NG' ? WP.ngEnd : WP.okEnd
    default:         return WP.booth
  }
}

function partColor(p) {
  if (p.phase === 'dwell') return '#1FB8CD'
  if (!p.verdict) return '#9aa3b2'
  return p.verdict === 'OK' ? '#34d399' : '#f87171'
}

// 공장 전광판
function ScoreBoard({ scan, counts }) {
  const verdict = scan?.verdict
  const vColor = verdict === 'NG' ? '#f87171' : verdict === 'OK' ? '#34d399' : '#9aa3b2'
  const score = scan?.score != null ? scan.score.toFixed(3) : '--'
  const cls = scan?.defect_class || ''

  return (
    <group position={[0.5, 3.05, -2.8]}>
      <mesh>
        <boxGeometry args={[5.5, 1.1, 0.07]} />
        <meshStandardMaterial color="#0e1118" metalness={0.82} roughness={0.18} />
      </mesh>
      <Text position={[-2.55, 0.36, 0.05]} fontSize={0.23} color="#1FB8CD" anchorX="left" characters={CHARS}>
        ARIA QC LINE
      </Text>
      <Text position={[-2.55, 0.02, 0.05]} fontSize={0.19} color="#e2e8f0" anchorX="left" characters={CHARS}>
        {`OK ${counts.ok}   NG ${counts.ng}   TOTAL ${counts.total}`}
      </Text>
      <Text position={[-2.55, -0.32, 0.05]} fontSize={0.16} color={vColor} anchorX="left" characters={CHARS}>
        {verdict
          ? `LAST ${verdict}  SCORE ${score}  ${cls}`
          : 'WAITING FOR INSPECTION...'}
      </Text>
    </group>
  )
}

// 설비 머리 위 HTML 상태 오버레이 라벨 (drei <Html>)
function AssetLabel({ asset }) {
  const c = statusColor(asset.status)
  const blink = asset.status === 'Error'
  return (
    <Html position={asset.labelPos} center distanceFactor={12} zIndexRange={[20, 0]}
      style={{ pointerEvents: 'none', userSelect: 'none' }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap',
        fontFamily: "'Courier New', monospace", fontSize: 12, lineHeight: 1,
        padding: '4px 9px', borderRadius: 6,
        background: 'rgba(10,14,20,0.82)', border: `1px solid ${c}`,
        color: c, boxShadow: `0 0 10px ${c}55`,
        animation: blink ? 'ariaBlink 0.8s steps(2,end) infinite' : 'none',
      }}>
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: c,
          boxShadow: `0 0 6px ${c}` }} />
        <span style={{ color: '#e2e8f0' }}>{asset.name}</span>
        <span>· {statusKo(asset.status)}</span>
      </div>
    </Html>
  )
}

// 구조 요소(바닥/기둥/빔/통로선)
function Structure({ environment }) {
  const isDark = environment !== 'planner'
  const floorColor = isDark ? '#28354a' : '#c8d0dc'
  const structureColor = isDark ? '#2e3e56' : '#7a8898'
  const beamColor = isDark ? '#283448' : '#6a7888'
  const floorTex = useMemo(() => makeFloorTexture(), [])
  return (
    <group>
      {/* 바닥 — 산업 텍스처(절차적 캔버스) */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0.5, -0.01, 0]} receiveShadow>
        <planeGeometry args={[24, 8]} />
        <meshStandardMaterial map={floorTex} color={floorColor}
          metalness={0.12} roughness={0.86} />
      </mesh>

      {/* 안전 통로 라인 */}
      {[-2.6, 2.6].map((z, i) => (
        <mesh key={i} position={[0.5, 0.008, z]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[23, 0.10]} />
          <meshStandardMaterial color="#f5c518" emissive="#f5c518" emissiveIntensity={0.15} />
        </mesh>
      ))}

      {/* 지지 기둥 4개 */}
      {[[-9.5, -2.4], [-9.5, 2.4], [10.5, -2.4], [10.5, 2.4]].map(([x, z], i) => (
        <mesh key={i} position={[x, 1.5, z]} castShadow>
          <boxGeometry args={[0.28, 3.0, 0.28]} />
          <meshStandardMaterial color={structureColor} metalness={0.52} roughness={0.48} />
        </mesh>
      ))}

      {/* 오버헤드 빔 */}
      <mesh position={[0.5, 3.0, -2.4]}>
        <boxGeometry args={[21, 0.17, 0.17]} />
        <meshStandardMaterial color={beamColor} metalness={0.52} roughness={0.48} />
      </mesh>
      <mesh position={[0.5, 3.0, 2.4]}>
        <boxGeometry args={[21, 0.17, 0.17]} />
        <meshStandardMaterial color={beamColor} metalness={0.52} roughness={0.48} />
      </mesh>
    </group>
  )
}

export default function QCLine({ environment = 'control_room' }) {
  const engineRef = useRef()
  if (!engineRef.current) engineRef.current = createQCFlowEngine()
  const engine = engineRef.current

  const kpi = useSignalStore(selectKpi)
  const scan = useSignalStore(selectScan)

  const [, force] = useState(0)
  const acc = useRef(0)
  // G3: NG 점멸용 — useFrame에서 매 프레임 갱신, 리렌더는 0.06s 간격
  const blinkRef = useRef(1)
  const nowRef = useRef(0)   // 설비 시뮬 지표용 시간(ms)

  useFrame(({ clock }, dt) => {
    nowRef.current = clock.getElapsedTime() * 1000
    blinkRef.current = Math.sin(clock.getElapsedTime() * Math.PI * 3) > 0 ? 1.0 : 0.15
    engine.tick(dt * 1000, scan)
    acc.current += dt
    if (acc.current > 0.06) { acc.current = 0; force(n => (n + 1) % 999999) }
  })

  const counts = engine.counts
  const parts = engine.parts

  // StackLight 신호: flowEngine(dwell) + store(kpi.state)
  const isInspecting = kpi.state === 'running' || parts.some(p => p.phase === 'dwell')
  const ngAlert = scan?.verdict === 'NG'
  // NG 분기 중인 부품이 있으면 diverter 강조
  const divertNG = parts.some(p => p.phase === 'ng_lane') || ngAlert
  const lineRunning = String(kpi.state || '').toLowerCase().startsWith('run')

  // 설비 건전성 — 기존 신호에서 파생(3D 오버레이 라벨용)
  const assets = deriveAssets(kpi, scan, nowRef.current)

  return (
    <group>
      {/* 환경 구조 */}
      <Structure environment={environment} />

      {/* ── 장비 프리팹 ── */}
      {/* 로봇 암 프롭 — 컨베이어 좌측, 절차적 애니메이션(키네매틱스 없음) */}
      <RobotArm position={[-6.2, 0, 1.4]} active={isInspecting} />

      <InfeedSource position={[-8.5, 0, 0]} />

      {/* 인입 컨베이어 (src→booth) */}
      <RollerConveyor length={6.2} width={0.95} position={[-4.5, H - 0.06, 0]}
        running={lineRunning} speed={0.6} />

      {/* 비전 부스 */}
      <VisionBooth position={[0, 0, 0]} boothDwelling={isInspecting} />

      {/* Andon 신호탑 */}
      <StackLight position={[0.6, 0, -1.55]}
        running={true}
        inspecting={isInspecting}
        ngAlert={ngAlert} />

      {/* 후부 출구 컨베이어 (booth→divert) */}
      <RollerConveyor length={3.0} width={0.95} position={[2.0, H - 0.06, 0]}
        running={lineRunning} speed={0.6} />

      {/* Diverter */}
      <Diverter position={[3.6, 0, 0]} ngActive={divertNG} />

      {/* OK 레인 컨베이어 */}
      <RollerConveyor length={4.5} width={0.75} position={[6.0, H - 0.06, 1.0]}
        running={lineRunning} speed={0.5} />
      {/* NG 레인 컨베이어 */}
      <RollerConveyor length={4.5} width={0.75} position={[6.0, H - 0.06, -1.0]}
        running={lineRunning} speed={0.5} />

      {/* 분류 함 */}
      <SortBin position={[8.8, 0, 1.0]} kind="OK" count={counts.ok} />
      <SortBin position={[8.8, 0, -1.0]} kind="NG" count={counts.ng} />

      {/* 설비 상태 HTML 오버레이 라벨 (CCTV 관제) */}
      {assets.map(a => <AssetLabel key={a.id} asset={a} />)}

      {/* 전광판 */}
      <ScoreBoard scan={scan} counts={counts} />

      {/* ── 부품 흐름 (Material Flow) ── */}
      {/* G3: OK=연녹 발광(0.28) / NG=강한 적색 발광+점멸(0.85×blink) / dwell=시안 펄스 */}
      {parts.map(p => {
        const pos = partPos(p)
        const col = partColor(p)
        const isNgPart = p.verdict === 'NG' && p.phase !== 'dwell'
        const emissI = p.phase === 'dwell' ? 0.55
          : isNgPart ? 0.85 * blinkRef.current
          : p.verdict === 'OK' ? 0.28
          : 0.06
        return (
          <mesh key={p.id} position={pos} castShadow>
            <boxGeometry args={[0.19, 0.19, 0.19]} />
            <meshStandardMaterial color={col} emissive={col} emissiveIntensity={emissI}
              metalness={0.38} roughness={0.52} />
          </mesh>
        )
      })}

      {/* G3: NG 마커 링 — conveyor 제외(아직 판정 전), dwell 이후만 표시 */}
      {parts.filter(p => p.verdict === 'NG' && p.phase !== 'conveyor').map(p => {
        const pos = partPos(p)
        return (
          <mesh key={`ng-ring-${p.id}`}
            position={[pos[0], H - 0.02, pos[2]]}
            rotation={[-Math.PI / 2, 0, 0]}>
            <ringGeometry args={[0.20, 0.30, 16]} />
            <meshStandardMaterial color="#f87171" emissive="#f87171"
              emissiveIntensity={1.2 * blinkRef.current}
              transparent opacity={0.6 * blinkRef.current}
              depthWrite={false} />
          </mesh>
        )
      })}
    </group>
  )
}
