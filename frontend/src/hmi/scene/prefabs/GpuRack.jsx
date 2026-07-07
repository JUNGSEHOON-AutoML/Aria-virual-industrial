// GpuRack — AI 연산 서버랙 프리팹 (실측 텔레메트리 연동).
// GPU별 슬랏 색 = thermal(cool시안/warm황/hot주황/critical적 점멸),
// 팬 회전속도 = util, VRAM 게이지 = vram_pct, 학습 중이면 보라 펄스 코어.
// telemetryFull.gpus(실측)가 있으면 GPU별, 없으면 summary 1칸 표시. 실측 없음 → CPU MODE 라벨.
import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'

const THERMAL_COLOR = {
  cool: '#1FB8CD', warm: '#facc15', hot: '#fb923c', critical: '#f87171',
}

const RACK_W = 1.1, RACK_D = 0.9, RACK_H = 2.1
const SLOT_H = 0.34

// GPU 1장 = 랙 슬랏 1칸. 실측 temp/util/vram 반영.
function GpuSlot({ y, gpu }) {
  const ledRef = useRef()
  const fanRef = useRef()
  const thermal = gpu?.thermal || 'cool'
  const color = THERMAL_COLOR[thermal]
  const util = gpu?.util_pct ?? 0
  const vramPct = gpu?.vram_pct ?? 0

  useFrame(({ clock }, dt) => {
    // critical: 점멸 / 그 외: util 비례 밝기
    if (ledRef.current) {
      const base = 0.35 + (util / 100) * 1.1
      ledRef.current.material.emissiveIntensity = thermal === 'critical'
        ? 0.4 + Math.abs(Math.sin(clock.getElapsedTime() * 6)) * 1.6
        : base
    }
    // 팬: util 비례 회전 (idle에도 저속)
    if (fanRef.current) fanRef.current.rotation.z += dt * (1.5 + util * 0.25)
  })

  return (
    <group position={[0, y, 0]}>
      {/* 슬랏 섀시 */}
      <mesh castShadow>
        <boxGeometry args={[RACK_W - 0.08, SLOT_H - 0.05, RACK_D - 0.08]} />
        <meshStandardMaterial color="#141a26" metalness={0.7} roughness={0.35} />
      </mesh>
      {/* 전면 LED 스트립 — thermal 색 */}
      <mesh ref={ledRef} position={[0, 0, RACK_D / 2 - 0.03]}>
        <boxGeometry args={[RACK_W - 0.18, 0.045, 0.02]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.4} />
      </mesh>
      {/* 팬 */}
      <group position={[-RACK_W / 2 + 0.22, -0.05, RACK_D / 2 - 0.02]}>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.075, 0.075, 0.02, 16]} />
          <meshStandardMaterial color="#0c1018" metalness={0.5} roughness={0.6} />
        </mesh>
        <mesh ref={fanRef} position={[0, 0, 0.012]}>
          <boxGeometry args={[0.115, 0.018, 0.004]} />
          <meshStandardMaterial color="#3a4556" metalness={0.6} />
        </mesh>
      </group>
      {/* VRAM 게이지 (가로 바) */}
      <group position={[0.12, -0.06, RACK_D / 2 - 0.02]}>
        <mesh>
          <boxGeometry args={[0.52, 0.05, 0.012]} />
          <meshStandardMaterial color="#0a0e14" />
        </mesh>
        <mesh position={[-(0.52 - 0.52 * Math.min(1, vramPct / 100)) / 2, 0, 0.008]}>
          <boxGeometry args={[Math.max(0.015, 0.52 * Math.min(1, vramPct / 100)), 0.04, 0.008]} />
          <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.7} />
        </mesh>
      </group>
    </group>
  )
}

// 학습 코어 — MODEL_TRAINING일 때 보라 펄스 회전
function TrainingCore({ active }) {
  const ref = useRef()
  useFrame(({ clock }, dt) => {
    if (!ref.current) return
    ref.current.rotation.y += dt * (active ? 3.5 : 0.5)
    const s = active ? 1 + Math.sin(clock.getElapsedTime() * 8) * 0.12 : 1
    ref.current.scale.setScalar(s)
    ref.current.material.emissiveIntensity = active
      ? 1.2 + Math.sin(clock.getElapsedTime() * 8) * 0.5
      : 0.15
  })
  return (
    <mesh ref={ref} position={[0, RACK_H + 0.28, 0]}>
      <icosahedronGeometry args={[0.13, 1]} />
      <meshStandardMaterial color={active ? '#a78bfa' : '#3a4556'}
        emissive="#a78bfa" emissiveIntensity={0.15} metalness={0.8} roughness={0.2} />
    </mesh>
  )
}

export default function GpuRack({ position = [0, 0, 0], rotation = [0, 0, 0],
  telemetry = null, gpus = null, training = false }) {
  const hasGpu = telemetry?.has_gpu
  // GPU별 실측(telemetryFull.gpus) 우선, 없으면 summary 1칸
  const slots = (gpus && gpus.length) ? gpus.slice(0, 4) : (hasGpu ? [telemetry] : [])
  const thermal = telemetry?.thermal || 'cool'
  const c = THERMAL_COLOR[thermal]

  return (
    <group position={position} rotation={rotation}>
      {/* 랙 캐비닛 */}
      <mesh position={[0, RACK_H / 2, 0]} castShadow receiveShadow>
        <boxGeometry args={[RACK_W, RACK_H, RACK_D]} />
        <meshStandardMaterial color="#1a2130" metalness={0.55} roughness={0.45} />
      </mesh>
      {/* 상단 캡 + 통풍구 */}
      <mesh position={[0, RACK_H + 0.04, 0]}>
        <boxGeometry args={[RACK_W + 0.06, 0.08, RACK_D + 0.06]} />
        <meshStandardMaterial color="#10151f" metalness={0.6} roughness={0.4} />
      </mesh>

      {/* GPU 슬랏 (실측 수만큼, 최대 4) */}
      {slots.map((g, i) => (
        <GpuSlot key={i} y={RACK_H - 0.45 - i * (SLOT_H + 0.06)} gpu={g} />
      ))}

      {/* 학습 코어 */}
      <TrainingCore active={training} />

      {/* 발열 위험 시 배경광 */}
      {thermal === 'critical' && (
        <pointLight color="#f87171" intensity={2.2} distance={5} position={[0, RACK_H / 2, 0.8]} />
      )}
      {training && thermal !== 'critical' && (
        <pointLight color="#a78bfa" intensity={1.2} distance={4} position={[0, RACK_H + 0.3, 0]} />
      )}

      {/* 머리 위 실측 라벨 */}
      <Html position={[0, RACK_H + 0.62, 0]} center distanceFactor={14}
        style={{ pointerEvents: 'none' }}>
        <div style={{ fontFamily: "'Courier New',monospace", fontSize: 11, whiteSpace: 'nowrap',
          textAlign: 'center', padding: '3px 9px', borderRadius: 6,
          background: 'rgba(10,14,20,0.88)', border: `1px solid ${c}`, color: c }}>
          {hasGpu ? (
            <>
              AI COMPUTE · {telemetry.gpu_name?.replace('NVIDIA GeForce ', '') || 'GPU'}
              {telemetry.n_gpus > 1 ? ` ×${telemetry.n_gpus}` : ''}
              <br />
              <span style={{ fontSize: 9, color: '#cbd5e1' }}>
                {telemetry.temp_c}°C · VRAM {telemetry.vram_pct}% · util {telemetry.util_pct}%
                {' · '}
                <span style={{ color: training ? '#a78bfa' : '#9aa3b2' }}>
                  {training ? '학습 중' : telemetry.load}
                </span>
              </span>
            </>
          ) : (
            <>AI COMPUTE · CPU MODE<br />
              <span style={{ fontSize: 9, color: '#9aa3b2' }}>GPU 미감지</span></>
          )}
        </div>
      </Html>
    </group>
  )
}
