// QCLine — 공정 충실 검사 라인 씬 (V1→V3)
// InfeedSource → RollerConveyor → VisionBooth → Diverter → OK/NG Bin + StackLight
// 부품 흐름은 flowEngine(순수 JS), 판정 분기는 inspector_result.verdict(signalStore)
import { useRef, useState, useMemo, useEffect } from 'react'
import { useFrame } from '@react-three/fiber'
import { Text, Html } from '@react-three/drei'
import * as THREE from 'three'
import { useSignalStore } from '../signalStore'
import { selectKpi, selectScan } from '../signalReducer'
import { createQCFlowEngine } from './flowEngine'
import { deriveAssets, statusColor, statusKo, ASSET_GROUND } from './assetModel'
import { makeFloorTexture } from './textures'
import { heightTexFromDataURI } from './inspectVfx'
import ReliefPatch from './ReliefPatch'
import { evaluateDeviation } from './deviationModel'
import InfeedSource from './prefabs/InfeedSource'
import RollerConveyor from './prefabs/RollerConveyor'
import InspectionArm from './prefabs/InspectionArm'
import Diverter from './prefabs/Diverter'
import SortBin from './prefabs/SortBin'
import StackLight from './prefabs/StackLight'
import RobotArm from './prefabs/RobotArm'
import GpuRack from './prefabs/GpuRack'
import InspectionSpecimen from './InspectionSpecimen'
import WorkerAgent from './WorkerAgent'
import PatrolRobot from './PatrolRobot'

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
  deferEnd:   [ 8.8, H, 0.0],   // 보류함(미검사) — 가운데
}

function partPos(p) {
  switch (p.phase) {
    case 'conveyor': return lerp3(WP.src, WP.boothIn, p.t)
    case 'dwell':    return [WP.booth[0], H + Math.sin(p.dwellT / 280) * 0.018, WP.booth[2]]
    case 'exit':     return lerp3(WP.booth, WP.divert, p.t)
    // 레인 진입: z(횡방향)는 앞 25%에서 빠르게 ±1로 이동 → 이후 벨트 위 직진(레인 이탈 방지)
    case 'ok_lane': {
      const x = WP.divert[0] + (WP.okEnd[0] - WP.divert[0]) * p.t
      const z = WP.okEnd[2] * Math.min(1, p.t / 0.25)
      return [x, H, z]
    }
    case 'ng_lane': {
      const x = WP.divert[0] + (WP.ngEnd[0] - WP.divert[0]) * p.t
      const z = WP.ngEnd[2] * Math.min(1, p.t / 0.25)
      return [x, H, z]
    }
    case 'defer_lane': return lerp3(WP.boothIn, WP.deferEnd, p.t)   // 보류: 검사 없이 곧장 보류함
    case 'done':     return p.verdict === 'NG' ? WP.ngEnd : p.verdict === 'SKIPPED' ? WP.deferEnd : WP.okEnd
    default:         return WP.booth
  }
}

function partColor(p) {
  if (p.phase === 'dwell') return '#1FB8CD'
  if (p.verdict === 'SKIPPED') return '#facc15'   // 보류=주의색(황)
  if (!p.verdict) return '#9aa3b2'
  return p.verdict === 'OK' ? '#34d399' : '#f87171'
}

// 설비 상태 → 전광판 표기/색 (백엔드 FactoryLine equipment_status)
const EQUIP_LABEL = {
  RUNNING: ['가동 중', '#34d399'], IDLE: ['대기', '#9aa3b2'],
  QA_ALERT: ['품질 경보', '#facc15'], MODEL_TRAINING: ['모델 학습 중', '#a78bfa'],
  THERMAL_FAULT: ['발열 위험 감속', '#f87171'],
}

// 공장 전광판 — 검사 결과 + 현실 라인 지표(속도·택트·처리량·설비상태)
function ScoreBoard({ scan, kpi, line, lineStats, telemetry }) {
  const verdict = scan?.verdict
  const vColor = verdict === 'NG' ? '#f87171' : verdict === 'OK' ? '#34d399' : '#9aa3b2'
  const score = scan?.score != null ? scan.score.toFixed(3) : '--'
  const cls = scan?.defect_class || ''
  const counts = { ok: kpi?.n_ok ?? 0, ng: kpi?.n_ng ?? 0, total: (kpi?.n_ok ?? 0) + (kpi?.n_ng ?? 0) }
  const [equipKo, equipColor] = EQUIP_LABEL[line?.equipment_status] || ['—', '#9aa3b2']
  const lineRow = line
    ? `SPD ${line.conveyor_speed_mps ?? '--'}m/s  TACT ${line.tact_time_s != null ? line.tact_time_s + 's' : '--'}  THRU ${line.throughput_per_min ?? '--'}/min`
    : 'LINE METRICS...'
  const gpuRow = telemetry?.has_gpu
    ? `GPU ${telemetry.temp_c}°C  VRAM ${telemetry.vram_pct}%  ${telemetry.load?.toUpperCase() || ''}`
    : null

  return (
    <group position={[0.5, 3.05, -2.8]}>
      <mesh>
        <boxGeometry args={[5.5, 1.65, 0.07]} />
        <meshStandardMaterial color="#0e1118" metalness={0.82} roughness={0.18} />
      </mesh>
      <Text position={[-2.55, 0.62, 0.05]} fontSize={0.23} color="#1FB8CD" anchorX="left" characters={CHARS}>
        ARIA QC LINE
      </Text>
      <Text position={[0.6, 0.62, 0.05]} fontSize={0.17} color={equipColor} anchorX="left" characters={CHARS}>
        {(line?.equipment_status || 'OFFLINE').replace('_', ' ')}
      </Text>
      <Text position={[-2.55, 0.28, 0.05]} fontSize={0.19} color="#e2e8f0" anchorX="left" characters={CHARS}>
        {`OK ${counts.ok}   NG ${counts.ng}   TOTAL ${counts.total}${lineStats?.defect_rate != null ? `   DEFECT ${(lineStats.defect_rate * 100).toFixed(0)}%` : ''}`}
      </Text>
      <Text position={[-2.55, -0.04, 0.05]} fontSize={0.16} color={vColor} anchorX="left" characters={CHARS}>
        {verdict
          ? `LAST ${verdict}  SCORE ${score}  ${cls}`
          : 'WAITING FOR INSPECTION...'}
      </Text>
      {/* 현실 라인 지표(ⓑ) — 컨베이어 속도·택트·처리량 */}
      <Text position={[-2.55, -0.36, 0.05]} fontSize={0.155} color="#8fd6e0" anchorX="left" characters={CHARS}>
        {lineRow}
      </Text>
      {/* 실측 GPU(ⓓ) — 온도·VRAM·부하 */}
      {gpuRow && (
        <Text position={[-2.55, -0.66, 0.05]} fontSize={0.15}
          color={telemetry.thermal === 'critical' ? '#f87171' : telemetry.thermal === 'hot' ? '#fb923c' : '#9fb4c8'}
          anchorX="left" characters={CHARS}>
          {gpuRow}
        </Text>
      )}
    </group>
  )
}

// F1: 선택 부품의 결함을 3D로 — 그 부품 record.heatmap_b64 → relief + 선택 링.
function SelectedPartViz({ part, partPos }) {
  const rec = part?.record
  const heightTex = useMemo(
    () => (rec?.heatmap_b64 ? heightTexFromDataURI(rec.heatmap_b64) : null),
    [rec?.heatmap_b64])
  if (!part || !rec) return null
  const pos = partPos(part)
  const isNG = rec.verdict === 'NG'
  return (
    <group>
      {/* 선택 링 */}
      <mesh position={[pos[0], pos[1] - 0.12, pos[2]]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.16, 0.22, 24]} />
        <meshStandardMaterial color="#38d9f5" emissive="#38d9f5" emissiveIntensity={1.0}
          side={2} transparent opacity={0.85} depthWrite={false} />
      </mesh>
      {/* 결함 요철(heatmap displacement) — 부품 위로 띄움 */}
      {heightTex && isNG && (
        <ReliefPatch heightTex={heightTex} size={0.42} score={rec.score ?? 0.6}
          position={[pos[0], pos[1] + 0.32, pos[2]]} />
      )}
      <Html position={[pos[0], pos[1] + 0.62, pos[2]]} center distanceFactor={12}
        style={{ pointerEvents: 'none' }}>
        <div style={{ fontFamily: "'Courier New',monospace", fontSize: 10, whiteSpace: 'nowrap',
          padding: '2px 7px', borderRadius: 5, background: 'rgba(10,14,20,0.85)',
          border: `1px solid ${isNG ? '#f87171' : '#34d399'}`, color: isNG ? '#f87171' : '#34d399' }}>
          {rec.part_id} · {rec.verdict}{rec.defect_class ? ` · ${rec.defect_class}` : ''}
        </div>
      </Html>
    </group>
  )
}

// 완전한 검사 라인 1개(z 오프셋) — 모든 레인이 동일: 인입→검사팔→분기→OK/NG 분류함 + WP 라우팅.
// laneScan(lanes[laneIdx]) 결과로 부품 스폰. 단일노드(레인0, lanes 비어있음)면 전역 scan 사용.
function LaneAssembly({ z, laneIdx, interactive = false, onOpenPiP, speedFactor = 1 }) {
  const lane = useSignalStore(s => s.lanes?.[laneIdx])
  const globalScan = useSignalStore(selectScan)
  const liveCategory = useSignalStore(s => s.liveCategory)
  const activeMode = useSignalStore(s => s.activeMode)
  const connected = useSignalStore(s => s.wsStatus) === 'open'
  const replayActive = useSignalStore(s => s.replay.active)
  const laneScan = lane ? lane.scan : (laneIdx === 0 ? globalScan : null)
  const category = lane?.category ?? (laneIdx === 0 ? liveCategory : null)

  const engineRef = useRef()
  if (!engineRef.current) engineRef.current = createQCFlowEngine()
  const eng = engineRef.current
  const lastPart = useRef(null)
  const blinkRef = useRef(1)
  const acc = useRef(0)
  const [, force] = useState(0)
  const [selId, setSelId] = useState(null)
  const setFocus = useSignalStore(s => s.setFocus)

  useEffect(() => {
    if (replayActive) return
    if (laneScan && laneScan.part_id && laneScan.part_id !== lastPart.current) {
      lastPart.current = laneScan.part_id
      eng.spawnFromResult(laneScan)
    }
  }, [laneScan, eng, replayActive])

  useEffect(() => {
    const k = (e) => { if (e.key === 'Escape') setSelId(null) }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [])

  // 발열 감속(ⓑ×ⓓ) — 백엔드 conveyor_speed_factor를 부품 이동 시간에도 반영
  useEffect(() => {
    const f = Math.max(0.2, speedFactor)
    eng.setConfig({ conveyorMs: 3200 / f, exitMs: 700 / f, laneMs: 2000 / f })
  }, [speedFactor, eng])

  useFrame(({ clock }, dt) => {
    if (!connected || replayActive) return
    blinkRef.current = Math.sin(clock.getElapsedTime() * Math.PI * 3) > 0 ? 1.0 : 0.15
    eng.tick(dt * 1000)
    acc.current += dt
    if (acc.current > 0.06) { acc.current = 0; force(n => (n + 1) % 999999) }
  })

  const counts = eng.counts
  const parts = eng.parts
  const running = connected && !replayActive
  const isInspecting = parts.some(p => p.phase === 'dwell')
  const divertNG = parts.some(p => p.phase === 'ng_lane') || laneScan?.verdict === 'NG'
  const lastV = laneScan?.verdict
  const lastColor = lastV === 'NG' ? '#f87171' : lastV === 'OK' ? '#34d399' : '#6b7280'
  const pp = (p) => { const q = partPos(p); return [q[0], q[1], q[2] + z] }

  return (
    <group>
      <InfeedSource position={[-8.5, 0, z]} />
      <RollerConveyor length={6.2} width={0.95} position={[-4.5, H - 0.06, z]} running={running} speed={0.6 * speedFactor} />
      {/* 비전 검사 로봇 팔(연속 동작) */}
      <InspectionArm position={[0, 0, z]} dwelling={isInspecting} laneScan={laneScan} />
      <RollerConveyor length={3.0} width={0.95} position={[2.0, H - 0.06, z]} running={running} speed={0.6 * speedFactor} />
      <Diverter position={[3.6, 0, z]} ngActive={divertNG} />
      <RollerConveyor length={4.5} width={0.75} position={[6.0, H - 0.06, z + 1.0]} running={running} speed={0.5 * speedFactor} />
      <RollerConveyor length={4.5} width={0.75} position={[6.0, H - 0.06, z - 1.0]} running={running} speed={0.5 * speedFactor} />
      <SortBin position={[8.8, 0, z + 1.0]} kind="OK" count={counts.ok} />
      <SortBin position={[8.8, 0, z - 1.0]} kind="NG" count={counts.ng} />
      {/* 보류함(미검사=백프레셔) — 드롭이 조용히 사라지지 않고 알려진 상태로 집계 */}
      <SortBin position={[8.8, 0, z]} kind="DEFER" count={counts.deferred} />
      {/* 보류 레인 컨베이어(가운데) */}
      <RollerConveyor length={4.5} width={0.6} position={[6.0, H - 0.06, z]} running={running} speed={0.5 * speedFactor} />

      {interactive && (
        <>
          <InspectionSpecimen position={[0, H + 0.15, z]} onTrigger={onOpenPiP} />
          <mesh position={[0, 1.46, z]} onClick={(e) => { e.stopPropagation(); onOpenPiP?.() }}
            onPointerOver={() => (document.body.style.cursor = 'pointer')}
            onPointerOut={() => (document.body.style.cursor = 'default')}>
            <sphereGeometry args={[0.12, 18, 18]} />
            <meshStandardMaterial color="#1FB8CD" emissive="#1FB8CD" emissiveIntensity={0.85} />
          </mesh>
        </>
      )}

      {/* 부품 흐름(WP 라우팅 + z 오프셋) — 클릭 시 PiP */}
      {parts.map(p => {
        const q = pp(p); const col = partColor(p)
        const ng = p.verdict === 'NG' && p.phase !== 'dwell'
        const emissI = p.phase === 'dwell' ? 0.55 : ng ? 0.85 * blinkRef.current : p.verdict === 'OK' ? 0.28 : 0.06
        return (
          <mesh key={p.id} position={q} rotation={[Math.PI / 2, 0, 0]} castShadow
            onClick={(e) => { e.stopPropagation(); setSelId(p.id); setFocus(p.record || null); onOpenPiP?.(p.record || null) }}
            onPointerOver={() => (document.body.style.cursor = 'pointer')}
            onPointerOut={() => (document.body.style.cursor = 'default')}>
            <cylinderGeometry args={[0.10, 0.10, 0.20, 16]} />
            <meshStandardMaterial color={col} emissive={col} emissiveIntensity={emissI} metalness={0.8} roughness={0.3} />
          </mesh>
        )
      })}

      <SelectedPartViz part={parts.find(p => p.id === selId)} partPos={pp} />

      {/* NG 마커 링 */}
      {parts.filter(p => p.verdict === 'NG' && p.phase !== 'conveyor').map(p => {
        const q = pp(p)
        return (
          <mesh key={`ng-${p.id}`} position={[q[0], H - 0.02, q[2]]} rotation={[-Math.PI / 2, 0, 0]}>
            <ringGeometry args={[0.20, 0.30, 16]} />
            <meshStandardMaterial color="#f87171" emissive="#f87171" emissiveIntensity={1.2 * blinkRef.current}
              transparent opacity={0.6 * blinkRef.current} depthWrite={false} />
          </mesh>
        )
      })}

      {/* 레인 라벨 — 클래스/모델 + 마지막 결과 */}
      <Html position={[-8.5, 1.55, z + 0.6]} center distanceFactor={16} style={{ pointerEvents: 'none' }}>
        <div style={{ fontFamily: "'Courier New',monospace", fontSize: 11, whiteSpace: 'nowrap', textAlign: 'center',
          padding: '3px 9px', borderRadius: 6, background: 'rgba(10,14,20,0.88)',
          border: `1px solid ${laneIdx === 0 ? '#34d399' : '#1FB8CD'}`, color: laneIdx === 0 ? '#34d399' : '#1FB8CD' }}>
          레인{laneIdx} · {category || '대기'}{activeMode ? ` · ${activeMode}` : ''}
          <br />
          <span style={{ fontSize: 9, color: '#cbd5e1' }}>
            OK {counts.ok}/NG {counts.ng} · 최근{' '}
            <span style={{ color: lastColor }}>{lastV || '—'}{laneScan?.score != null && laneScan.score >= 0 ? ` ${laneScan.score.toFixed(3)}` : ''}</span>
          </span>
        </div>
      </Html>
    </group>
  )
}

// ② 병목 인디케이터 — 비전 스테이션 적색 박스 + BOTTLENECK 라벨(편차 진단).
function BottleneckIndicator({ dev, position = [0, 1.0, 0] }) {
  const ref = useRef()
  useFrame(({ clock }) => {
    if (!ref.current) return
    const b = 0.4 + Math.abs(Math.sin(clock.getElapsedTime() * 4)) * 0.5
    ref.current.material.opacity = b
  })
  if (!dev?.bottleneck) return null
  return (
    <group position={position}>
      <lineSegments>
        <edgesGeometry args={[new THREE.BoxGeometry(2.0, 2.2, 1.6)]} />
        <lineBasicMaterial color="#f87171" />
      </lineSegments>
      <mesh ref={ref}>
        <boxGeometry args={[2.0, 2.2, 1.6]} />
        <meshBasicMaterial color="#f87171" transparent opacity={0.5} depthWrite={false} />
      </mesh>
      <Html position={[0, 1.5, 0]} center distanceFactor={14} style={{ pointerEvents: 'none' }}>
        <div style={{ fontFamily: "'Courier New',monospace", fontSize: 12, whiteSpace: 'nowrap',
          padding: '4px 10px', borderRadius: 6, background: 'rgba(30,8,10,0.92)',
          border: '2px solid #f87171', color: '#f87171', fontWeight: 700, textAlign: 'center' }}>
          ⚠ BOTTLENECK<br />
          <span style={{ fontSize: 9, color: '#fca5a5', fontWeight: 400 }}>{dev.reason}</span>
        </div>
      </Html>
    </group>
  )
}

// T1-B: 의심 스테이션 위치 힌트 — 3D엔 은은한 황색 링만(텍스트 라벨은 우측 "예지" 리스트로 강등).
// 색 의미 고정: 황(#facc15)=주의·예지.
// T1-C: 건전성 링(H로 색: 녹→황→적) + RUL 라벨. pred 없으면 T1-B 황색 펄스.
const _healthColor = (h) => (h == null ? '#facc15' : h >= 0.7 ? '#34d399' : h >= 0.45 ? '#facc15' : '#f87171')
function SuspectStation({ assetId, pred }) {
  const ground = ASSET_GROUND[assetId]
  const ringRef = useRef()
  useFrame(({ clock }) => {
    if (!ringRef.current) return
    const s = 1 + Math.sin(clock.getElapsedTime() * 3) * 0.15
    ringRef.current.scale.setScalar(s)
    ringRef.current.material.opacity = 0.3 + Math.abs(Math.sin(clock.getElapsedTime() * 3)) * 0.35
  })
  if (!ground) return null
  const color = _healthColor(pred?.health)
  const rul = pred?.rul
  return (
    <group>
      <mesh ref={ringRef} position={[ground[0], 0.04, ground[2]]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.5, 0.68, 32]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.9}
          transparent opacity={0.5} side={2} depthWrite={false} />
      </mesh>
      {rul && (
        <Html position={[ground[0], 1.15, ground[2]]} center distanceFactor={13} style={{ pointerEvents: 'none' }}>
          <div style={{ background: 'rgba(10,12,16,0.82)', border: `1px solid ${color}`, borderRadius: 6,
            padding: '2px 7px', color, fontSize: 11, fontFamily: 'Courier New, monospace', whiteSpace: 'nowrap' }}>
            {pred.corroborated && <span style={{ color: '#34d399' }}>✓ </span>}
            {rul.est_hours != null ? `RUL ~${rul.est_hours}h (${rul.lo}–${rul.hi})` : '건전성 주의'}
            {pred.health != null && <span style={{ color: '#9aa0aa' }}> · H {Math.round(pred.health * 100)}%</span>}
          </div>
        </Html>
      )}
    </group>
  )
}

// 설비 머리 위 HTML 상태 오버레이 라벨 (drei <Html>)
// ③ 디제틱 라벨 — 클릭 시 상세 팝업 토글(가장자리 패널 아님, 공간 내부)
function AssetLabel({ asset, onClick, selected }) {
  const c = statusColor(asset.status)
  const blink = asset.status === 'Error'
  return (
    <Html position={asset.labelPos} center distanceFactor={12} zIndexRange={[20, 0]}
      style={{ pointerEvents: 'auto', userSelect: 'none' }}>
      <div onClick={(e) => { e.stopPropagation(); onClick?.() }}
        style={{
          display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap', cursor: 'pointer',
          fontFamily: "'Courier New', monospace", fontSize: 12, lineHeight: 1,
          padding: '4px 9px', borderRadius: 6,
          background: 'rgba(10,14,20,0.82)', border: `1px solid ${selected ? '#fff' : c}`,
          color: c, boxShadow: `0 0 ${selected ? 14 : 10}px ${c}66`,
          animation: blink ? 'ariaBlink 0.8s steps(2,end) infinite' : 'none',
        }}>
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: c,
          boxShadow: `0 0 6px ${c}` }} />
        <span style={{ color: '#e2e8f0' }}>{asset.name}</span>
        <span>· {statusKo(asset.status)}</span>
        <span style={{ color: '#5b6677', fontSize: 10 }}>{selected ? '▾' : 'ⓘ'}</span>
      </div>
    </Html>
  )
}

// ③ 객체 디제틱 팝업 — 클릭한 설비 옆 공간에 라이브 데이터 추적 표시.
function DiegeticPopup({ asset, scan }) {
  if (!asset) return null
  const c = statusColor(asset.status)
  const lp = asset.labelPos
  const isCam = asset.id === 'vision_camera'
  return (
    <Html position={[lp[0] + 0.6, lp[1] - 0.35, lp[2]]} distanceFactor={11}
      style={{ pointerEvents: 'none' }}>
      <div style={{ fontFamily: "'Courier New',monospace", fontSize: 11, width: 190,
        background: 'rgba(9,13,20,0.94)', border: `1px solid ${c}`, borderRadius: 8,
        padding: '8px 10px', color: '#cbd5e1', boxShadow: `0 0 16px ${c}55` }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
          <span style={{ color: '#e2e8f0', fontWeight: 700 }}>{asset.name}</span>
          <span style={{ color: c }}>{statusKo(asset.status)}</span>
        </div>
        {asset.metrics.map((m, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '1px 0' }}>
            <span style={{ color: '#6b7280' }}>{m.k}{m.sim ? ' ◦' : ''}</span>
            <span style={{ color: '#cbd5e1' }}>{m.v}{m.unit ? ` ${m.unit}` : ''}</span>
          </div>
        ))}
        {isCam && scan && (
          <div style={{ marginTop: 5, paddingTop: 5, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: '#6b7280' }}>last</span>
              <span style={{ color: scan.verdict === 'NG' ? '#f87171' : '#34d399' }}>
                {scan.verdict} {scan.score != null && scan.score >= 0 ? scan.score.toFixed(3) : ''}
              </span>
            </div>
          </div>
        )}
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
      {/* 바닥 — 거대 공장 스케일(Prompt 2) */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]} receiveShadow>
        <planeGeometry args={[110, 70]} />
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

      {isDark && <FactoryBackdrop />}
    </group>
  )
}

// 스마트 공장 배경 — 후벽·천장 트러스·천장 조명·측면 설비 실루엣(경량, 깊이감)
function FactoryBackdrop() {
  return (
    <group>
      {/* 후벽(패널) */}
      <mesh position={[0.5, 4, -14]} receiveShadow>
        <planeGeometry args={[80, 12]} />
        <meshStandardMaterial color="#161d2a" metalness={0.2} roughness={0.9} />
      </mesh>
      {/* 후벽 가로 패널 라인 */}
      {[1.5, 4, 6.5].map((y, i) => (
        <mesh key={`wl-${i}`} position={[0.5, y, -13.95]}>
          <planeGeometry args={[78, 0.04]} />
          <meshStandardMaterial color="#26344a" emissive="#26344a" emissiveIntensity={0.2} />
        </mesh>
      ))}

      {/* 천장 트러스(가로 빔 × 세로 빔) */}
      {[-9, -3, 3, 9, 15].map((x, i) => (
        <mesh key={`tx-${i}`} position={[x, 6.2, -2]} castShadow>
          <boxGeometry args={[0.18, 0.18, 18]} />
          <meshStandardMaterial color="#1c2536" metalness={0.5} roughness={0.5} />
        </mesh>
      ))}
      {[-7, -1, 5].map((z, i) => (
        <mesh key={`tz-${i}`} position={[3, 6.2, z]}>
          <boxGeometry args={[44, 0.14, 0.14]} />
          <meshStandardMaterial color="#1c2536" metalness={0.5} roughness={0.5} />
        </mesh>
      ))}

      {/* 천장 조명 패널(발광) */}
      {[-8, 0, 8, 16].map((x, i) => (
        <mesh key={`cl-${i}`} position={[x, 6.0, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <planeGeometry args={[2.4, 0.5]} />
          <meshStandardMaterial color="#0a0e14" emissive="#dbe8ff" emissiveIntensity={0.7} />
        </mesh>
      ))}

      {/* 측면 설비 실루엣(캐비닛/랙) — 깊이감 */}
      {[[-13, -8], [-13, 6], [16, -8], [16, 6], [22, 0]].map(([x, z], i) => (
        <mesh key={`cab-${i}`} position={[x, 1.1, z]} castShadow>
          <boxGeometry args={[1.6, 2.2, 1.2]} />
          <meshStandardMaterial color="#1a2230" metalness={0.4} roughness={0.6} />
        </mesh>
      ))}
    </group>
  )
}

export default function QCLine({ environment = 'control_room', onOpenPiP }) {
  const kpi = useSignalStore(selectKpi)
  const scan = useSignalStore(selectScan)
  const replayActive = useSignalStore(s => s.replay.active)
  const lanesMap = useSignalStore(s => s.lanes)
  const predictions = useSignalStore(s => s.predictions) || []
  // ── 공장 트윈 라인(ⓑ) + 실측 텔레메트리(ⓓ) ──
  const line = useSignalStore(s => s.line)
  const lineStats = useSignalStore(s => s.lineStats)
  const telemetry = useSignalStore(s => s.telemetry)
  const telemetryFull = useSignalStore(s => s.telemetryFull)

  const nowRef = useRef(0)
  const acc = useRef(0)
  const [, force] = useState(0)
  const [selAsset, setSelAsset] = useState(null)   // ③ 디제틱 팝업 선택 설비

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setSelAsset(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // 설비 시뮬 지표용 시간 + 경량 리렌더(에셋/팝업 갱신). 레인 흐름은 각 LaneAssembly가 자체 tick.
  useFrame(({ clock }, dt) => {
    nowRef.current = clock.getElapsedTime() * 1000
    acc.current += dt
    if (acc.current > 0.12) { acc.current = 0; force(n => (n + 1) % 999999) }
  })

  const isRunning = String(kpi.state || '').toLowerCase().startsWith('run')
  const ngAlert = scan?.verdict === 'NG'
  const dev = evaluateDeviation(kpi)
  const assets = deriveAssets(kpi, scan, nowRef.current)
  // 발열 감속 계수(백엔드 결정) — 컨베이어·부품 흐름 속도에 반영
  const speedFactor = line?.conveyor_speed_factor ?? 1
  const equip = line?.equipment_status
  const training = equip === 'MODEL_TRAINING' || !!telemetry?.training

  // 레인 구성: 멀티레인이면 lanes 키, 아니면 단일(레인0)
  const laneIdxs = lanesMap && Object.keys(lanesMap).length
    ? Object.keys(lanesMap).map(Number).sort((a, b) => a - b)
    : [0]
  const LANE_Z = { 0: 0, 1: -6, 2: -11, 3: -16 }

  // T1-B/T1-C: 의심 스테이션 강조 — 자산 베이스명(레인접미사 제거)으로 지면 매핑
  const suspectByAsset = {}
  predictions.filter(p => p.status === 'pending' || p.status === 'approved').forEach(p => {
    const a = (p.asset || p.causal?.assetHint || '').replace(/_\d+$/, '')
    if (!a) return
    // 우선순위: 더 낮은 건전성(H) 또는 더 높은 신뢰도
    const worse = !suspectByAsset[a] ||
      ((p.health ?? 1) < (suspectByAsset[a].health ?? 1)) ||
      ((p.statConfidence ?? 0) > (suspectByAsset[a].statConfidence ?? 0))
    if (worse) suspectByAsset[a] = p
  })

  return (
    <group>
      <Structure environment={environment} />
      <RobotArm position={[-6.2, 0, 4.4]} active={isRunning} />

      {/* 동일 검사 라인 N개 — 레인0(인터랙티브) + 멀티레인 시 1·2 추가 */}
      {laneIdxs.map(i => (
        <LaneAssembly key={i} z={LANE_Z[i] ?? -6 - 5 * (i - 1)} laneIdx={i}
          interactive={i === 0} onOpenPiP={onOpenPiP} speedFactor={speedFactor} />
      ))}

      {/* AI 연산 서버랙(ⓓ) — 실측 GPU 온도/VRAM/부하 → 색·팬·게이지·학습 코어 */}
      <GpuRack position={[-4.2, 0, -3.4]} rotation={[0, 0.35, 0]}
        telemetry={telemetry} gpus={telemetryFull?.gpus} training={training} />

      {/* ② 병목 인디케이터(레인0 비전 스테이션) */}
      <BottleneckIndicator dev={dev} position={[0, 1.0, 0]} />

      {/* Andon 신호탑 — 라인 설비상태(QA_ALERT/THERMAL_FAULT)도 적색 경보 */}
      <StackLight position={[0.6, 0, -1.55]} running={equip !== 'IDLE'} inspecting={isRunning || training}
        ngAlert={ngAlert || dev.bottleneck || equip === 'QA_ALERT' || equip === 'THERMAL_FAULT'} />

      {/* 설비 상태 라벨 + 디제틱 팝업 */}
      {assets.map(a => (
        <AssetLabel key={a.id} asset={a} selected={selAsset === a.id}
          onClick={() => setSelAsset(selAsset === a.id ? null : a.id)} />
      ))}
      <DiegeticPopup asset={assets.find(a => a.id === selAsset)} scan={scan} />

      {/* 유지보수 에이전트 + 예지 의심 강조 + 순찰 로봇 */}
      <WorkerAgent />
      {Object.keys(suspectByAsset).map(a => (
        <SuspectStation key={a} assetId={a} pred={suspectByAsset[a]} />
      ))}
      <PatrolRobot />

      {/* 전광판 — 검사 + 라인 지표 + GPU 실측 */}
      <ScoreBoard scan={scan} kpi={kpi} line={line} lineStats={lineStats} telemetry={telemetry} />
    </group>
  )
}
