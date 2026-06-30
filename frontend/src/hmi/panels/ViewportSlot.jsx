// ViewportSlot — 공장 관제(CCTV) 디지털 트윈 씬 마운트
// 환경맵(Lightformer, 오프라인 안전) + CCTV 쿼터뷰 + 설비 상태 오버레이.
// 환경 토글: planner(밝은 체커보드) ↔ control_room(관제 다크)
import { useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Grid, Environment, Lightformer } from '@react-three/drei'
import QCLine from '../scene/QCLine'
import VisionPiP from './VisionPiP'
import ApprovalGate from './ApprovalGate'
import ReplayBar from './ReplayBar'
import SceneErrorBoundary from './SceneErrorBoundary'
import MaintenanceController from '../scene/MaintenanceController'
import PredictiveMaintenance from '../scene/PredictiveMaintenance'
import { useSignalStore } from '../signalStore'
import { selectScan, selectKpi } from '../signalReducer'

// 공장 천장 조명 리그 — 외부 HDRI 없이 PBR 반사 환경을 베이크(frames=1, 정적).
// (온라인이면 <Environment preset="warehouse" />로 교체 가능)
function FactoryEnv() {
  return (
    <Environment resolution={256} frames={1}>
      {/* 천장 메인 패널 */}
      <Lightformer intensity={2.2} color="#eef4ff" form="rect"
        position={[0, 7, 0]} rotation={[Math.PI / 2, 0, 0]} scale={[14, 8, 1]} />
      {/* 좌/우 측광 */}
      <Lightformer intensity={1.3} color="#cfe0ff" form="rect"
        position={[-9, 4, 0]} rotation={[0, Math.PI / 2, 0]} scale={[8, 6, 1]} />
      <Lightformer intensity={1.3} color="#bfe9ff" form="rect"
        position={[9, 4, 0]} rotation={[0, -Math.PI / 2, 0]} scale={[8, 6, 1]} />
      {/* 검사 부스 강조(시안) */}
      <Lightformer intensity={1.6} color="#1FB8CD" form="circle"
        position={[0, 4.5, 1.5]} rotation={[Math.PI / 2, 0, 0]} scale={[3, 3, 1]} />
    </Environment>
  )
}

function Lights({ environment }) {
  if (environment === 'planner') {
    return (
      <>
        <ambientLight intensity={1.05} />
        <directionalLight position={[4, 12, 6]} intensity={1.1} color="#fff8f0" castShadow
          shadow-mapSize-width={1024} shadow-mapSize-height={1024} />
        <directionalLight position={[-6, 8, -4]} intensity={0.4} color="#f0f4ff" />
      </>
    )
  }
  // G3 조명 전면 재설계 — 공장 오버헤드 스팟 + 검사 부스 시안 포인트
  return (
    <>
      {/* 기저 환경광 */}
      <ambientLight intensity={0.55} />
      <hemisphereLight skyColor="#c8d8f5" groundColor="#0c1018" intensity={0.45} />

      {/* 주 방향광 — 천장 좌측 대각선 */}
      <directionalLight position={[3, 14, 7]} intensity={1.8} color="#fff4ec" castShadow
        shadow-mapSize-width={2048} shadow-mapSize-height={2048}
        shadow-camera-far={40} shadow-camera-left={-16} shadow-camera-right={16}
        shadow-camera-top={8} shadow-camera-bottom={-4} />

      {/* 공장 천장 형광등 3개 — 장비 전 구간 조명 */}
      <pointLight position={[-7, 5.5, 0]} intensity={3.0} color="#e8f2ff" distance={14} />
      <pointLight position={[ 0, 5.5, 0]} intensity={3.0} color="#e8f2ff" distance={14} />
      <pointLight position={[ 7, 5.5, 0]} intensity={3.0} color="#e8f2ff" distance={14} />

      {/* 비전 부스 검사 조명 (시안) — 검사 영역 강조 */}
      <pointLight position={[0, 3.2, 0]} intensity={3.5} color="#1FB8CD" distance={6} />

      {/* 배경 채움 (청색 역광) */}
      <directionalLight position={[-8, 4, -5]} intensity={0.38} color="#2a4568" />
    </>
  )
}

const chip = {
  fontFamily: "'Courier New',monospace", fontSize: 10, padding: '3px 8px', borderRadius: 5,
  background: 'rgba(0,0,0,0.45)', border: '1px solid rgba(255,255,255,0.08)',
  color: '#9aa3b2', userSelect: 'none', cursor: 'pointer', letterSpacing: 0.5,
}
const chipActive = {
  ...chip,
  background: 'rgba(31,184,205,0.18)', border: '1px solid #1FB8CD', color: '#1FB8CD',
}

export default function ViewportSlot() {
  const [env, setEnv] = useState('control_room')
  const [pip, setPip] = useState(false)
  const [pipData, setPipData] = useState(null)   // 시편 클릭 시 viz override
  const scan = useSignalStore(selectScan)
  const kpi = useSignalStore(selectKpi)
  const wsStatus = useSignalStore(s => s.wsStatus)
  const disconnected = wsStatus !== 'open'

  const bgColor = env === 'planner' ? '#dce4ee' : '#0d1320'

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <SceneErrorBoundary>
      <Canvas
        shadows
        camera={{ position: [11.5, 8.5, 12], fov: 42 }}
        gl={{ antialias: true }}
      >
        <color attach="background" args={[bgColor]} />
        {/* fog 제거 — 장비 가시성 확보 (어두운 배경은 재질색/조명으로 처리) */}

        <Lights environment={env} />
        {env === 'control_room' && <FactoryEnv />}

        {/* 대형 공장 그리드(Prompt 2: 100×100+) */}
        <Grid infiniteGrid position={[0, 0.001, 0]}
          cellSize={1} sectionSize={5}
          cellColor={env === 'planner' ? '#a8b4c0' : '#22303f'}
          sectionColor={env === 'planner' ? '#7a8898' : '#36506e'}
          fadeDistance={120} fadeStrength={1.0} />

        <QCLine environment={env}
          onOpenPiP={(d) => { setPipData(d || null); setPip(true) }} />

        {/* CCTV 쿼터뷰 — 바닥 아래/완전 탑다운 차단, 전체 라인 조망 */}
        <OrbitControls
          enableDamping dampingFactor={0.08} makeDefault
          minDistance={6} maxDistance={70}
          minPolarAngle={0.18} maxPolarAngle={Math.PI / 2.15}
          target={[0.5, 0.8, 0]}
        />
      </Canvas>
      </SceneErrorBoundary>

      {/* 유지보수 루프(비시각) — Observe→Think→Act 규칙기반 (Spec 2) */}
      <MaintenanceController />
      {/* 예지보전 루프(비시각) — 결함 패턴 집계 → 가설 (T1-B) */}
      <PredictiveMaintenance />

      {/* Vision PiP — 카메라/시편 클릭 시 슬라이드 (명세 A·§4) */}
      <VisionPiP open={pip} data={pipData} onClose={() => setPip(false)} />

      {/* 승인 게이트 — 실 액션은 승인 후에만 (Simulate-then-Approve) */}
      <ApprovalGate />

      {/* ① 3D 리플레이 블랙박스 — 데이터 되먹임으로 과거 재생 */}
      <ReplayBar />

      {/* Prompt 1: 백엔드 끊김 경고 — 씬 freeze + 실데이터 강제(시늉 방지) */}
      {disconnected && (
        <div style={{ position: 'absolute', inset: 0, zIndex: 20, display: 'flex',
          flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10,
          background: 'rgba(8,10,16,0.62)', backdropFilter: 'blur(2px)',
          fontFamily: "'Courier New',monospace", pointerEvents: 'none' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '16px 24px',
            borderRadius: 10, background: 'rgba(20,8,10,0.92)', border: '2px solid #f87171',
            boxShadow: '0 0 30px rgba(248,113,113,0.4)' }}>
            <span style={{ fontSize: 26, color: '#f87171' }}>⛔</span>
            <div>
              <div style={{ fontSize: 16, color: '#f87171', fontWeight: 700, letterSpacing: 0.5 }}>
                Backend Disconnected — GPU Inference Offline
              </div>
              <div style={{ fontSize: 11, color: '#cbd5e1', marginTop: 4 }}>
                WS: {wsStatus} · 실시간 추론 스트림 없음 — 씬 정지됨 (가짜 데이터 미생성)
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 환경 토글 */}
      <div style={{ position: 'absolute', top: 10, right: 12, display: 'flex', gap: 5 }}>
        <span style={env === 'planner' ? chipActive : chip} onClick={() => setEnv('planner')}>
          PLANNER
        </span>
        <span style={env === 'control_room' ? chipActive : chip} onClick={() => setEnv('control_room')}>
          CTRL ROOM
        </span>
      </div>

      {/* 라이브 상태 오버레이 */}
      <div style={{ position: 'absolute', top: 10, left: 12, display: 'flex', gap: 5, flexWrap: 'wrap' }}>
        {scan && (
          <>
            <span style={{ ...chip, color: scan.verdict === 'NG' ? '#f87171' : '#34d399' }}>
              {scan.verdict} {scan.score != null ? scan.score.toFixed(3) : ''}
            </span>
            {scan.defect_class && (
              <span style={{ ...chip, color: '#facc15' }}>{scan.defect_class}</span>
            )}
          </>
        )}
        {kpi.state && <span style={chip}>INSP {kpi.state}</span>}
      </div>
    </div>
  )
}
