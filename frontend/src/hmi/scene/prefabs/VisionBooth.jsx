// VisionBooth — 비전 검사 부스 프리팹. 아치+돔라이트+카메라+dwell 바인딩.
// G3: 초점 콘 추가 (반투명 cone = 카메라 FOV 시각화).
// 라이브 바인딩: inspector_state(kpi.state) + inspector_result(scan)
import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Text } from '@react-three/drei'
import * as THREE from 'three'
import { useSignalStore } from '../../signalStore'
import { selectKpi, selectScan } from '../../signalReducer'

const CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ·_-%.:'
const ARCH = '#232a38'
const DOME_C = '#1FB8CD'
const RING_C = '#e0f4ff'

export default function VisionBooth({ position = [0, 0, 0], boothDwelling = false }) {
  const kpi = useSignalStore(selectKpi)
  const scan = useSignalStore(selectScan)

  const domeRef = useRef()
  const ringRef = useRef()
  const camRef = useRef()
  const flashT = useRef(0)
  const lastScanId = useRef(null)

  const isRunning = kpi.state === 'running'
  const lastVerdict = scan?.verdict
  const verdictColor = lastVerdict === 'NG' ? '#f87171' : lastVerdict === 'OK' ? '#34d399' : '#9aa3b2'

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    const dwelling = boothDwelling || isRunning

    // 새 스캔 결과 → 짧은 플래시
    if (scan && scan.part_id !== lastScanId.current) {
      lastScanId.current = scan.part_id
      flashT.current = 1.0
    }
    if (flashT.current > 0) flashT.current = Math.max(0, flashT.current - 0.04)

    if (domeRef.current) {
      const pulse = dwelling ? 0.55 + Math.sin(t * 9) * 0.45 : 0.15
      const flash = flashT.current * 2.2
      domeRef.current.material.emissiveIntensity = Math.max(pulse, flash)
    }
    if (ringRef.current) {
      ringRef.current.material.emissiveIntensity = dwelling ? 0.75 : 0.08
    }
    if (camRef.current) {
      camRef.current.rotation.y = dwelling ? Math.sin(t * 2.4) * 0.28 : 0
    }
  })

  const aW = 1.3, aH = 1.9, aD = 0.7

  return (
    <group position={position}>
      {/* 아치 좌 기둥 */}
      <mesh position={[-aW / 2, aH / 2, 0]} castShadow>
        <boxGeometry args={[0.13, aH, aD]} />
        <meshStandardMaterial color={ARCH} metalness={0.62} roughness={0.38} />
      </mesh>
      {/* 아치 우 기둥 */}
      <mesh position={[aW / 2, aH / 2, 0]} castShadow>
        <boxGeometry args={[0.13, aH, aD]} />
        <meshStandardMaterial color={ARCH} metalness={0.62} roughness={0.38} />
      </mesh>
      {/* 아치 상단 빔 */}
      <mesh position={[0, aH + 0.065, 0]} castShadow>
        <boxGeometry args={[aW + 0.13, 0.13, aD]} />
        <meshStandardMaterial color={ARCH} metalness={0.62} roughness={0.38} />
      </mesh>

      {/* 머신 하우징(상단 후드) + 액센트 엣지 */}
      <mesh position={[0, aH + 0.30, 0]} castShadow>
        <boxGeometry args={[aW + 0.34, 0.42, aD + 0.18]} />
        <meshStandardMaterial color="#1a2030" metalness={0.7} roughness={0.3} />
      </mesh>
      <mesh position={[0, aH + 0.10, (aD + 0.18) / 2]}>
        <boxGeometry args={[aW + 0.34, 0.03, 0.02]} />
        <meshStandardMaterial color={DOME_C} emissive={DOME_C} emissiveIntensity={0.8} />
      </mesh>

      {/* 베이스 플레이트 + 경고 스트라이프(좌우 기둥 하단) */}
      {[-aW / 2, aW / 2].map((x, i) => (
        <group key={i} position={[x, 0.04, 0]}>
          <mesh receiveShadow>
            <boxGeometry args={[0.34, 0.08, aD + 0.12]} />
            <meshStandardMaterial color="#11151d" metalness={0.5} roughness={0.5} />
          </mesh>
          <mesh position={[0, 0.05, 0]}>
            <boxGeometry args={[0.30, 0.012, aD + 0.05]} />
            <meshStandardMaterial color="#f5c518" emissive="#f5c518" emissiveIntensity={0.2} />
          </mesh>
        </group>
      ))}

      {/* 측면 HMI 스크린(우측 기둥) — verdict 색 패널 */}
      <group position={[aW / 2 + 0.02, aH * 0.62, aD / 2 - 0.05]} rotation={[0, -0.25, 0]}>
        <mesh>
          <boxGeometry args={[0.34, 0.26, 0.03]} />
          <meshStandardMaterial color="#0a0e14" metalness={0.4} roughness={0.5} />
        </mesh>
        <mesh position={[0, 0, 0.02]}>
          <boxGeometry args={[0.30, 0.22, 0.01]} />
          <meshStandardMaterial color="#0a0e14" emissive={verdictColor} emissiveIntensity={0.5} />
        </mesh>
      </group>

      {/* 링 라이트 LED 도트(검사 영역 조명 어레이) */}
      {Array.from({ length: 10 }).map((_, i) => {
        const a = (i / 10) * Math.PI * 2
        return (
          <mesh key={`led-${i}`} position={[Math.cos(a) * 0.38, aH * 0.55, Math.sin(a) * 0.30]}>
            <sphereGeometry args={[0.016, 6, 6]} />
            <meshStandardMaterial color={RING_C} emissive={RING_C} emissiveIntensity={0.6} />
          </mesh>
        )
      })}

      {/* 돔/구형 라이트 — 검사 중 펄스 */}
      <mesh ref={domeRef} position={[0, aH - 0.22, 0]}>
        <sphereGeometry args={[0.19, 16, 16]} />
        <meshStandardMaterial color={DOME_C} emissive={DOME_C} emissiveIntensity={0.15} />
      </mesh>

      {/* 링 라이트 (X축 기준 아치 아래) */}
      <mesh ref={ringRef} position={[0, aH * 0.55, 0]} rotation={[0, 0, Math.PI / 2]}>
        <torusGeometry args={[0.38, 0.022, 8, 28]} />
        <meshStandardMaterial color={RING_C} emissive={RING_C} emissiveIntensity={0.08} />
      </mesh>

      {/* G3: 초점 콘 — 카메라 FOV 반투명 시각화 (opacity 높여 가시성 확보) */}
      <mesh position={[0, aH * 0.50, 0]} rotation={[Math.PI, 0, 0]}>
        <coneGeometry args={[0.55, aH * 0.68, 16, 1, true]} />
        <meshStandardMaterial color="#1FB8CD" transparent opacity={0.16}
          side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      {/* 콘 외곽선 (약간 진한 테두리) */}
      <mesh position={[0, aH * 0.50, 0]} rotation={[Math.PI, 0, 0]}>
        <coneGeometry args={[0.56, aH * 0.68, 16, 1, true]} />
        <meshStandardMaterial color="#1FB8CD" transparent opacity={0.06}
          side={THREE.BackSide} depthWrite={false} wireframe={false} />
      </mesh>

      {/* 카메라 헤드 */}
      <group ref={camRef} position={[0, aH - 0.44, -(aD / 2 + 0.06)]}>
        <mesh castShadow>
          <boxGeometry args={[0.13, 0.13, 0.2]} />
          <meshStandardMaterial color="#111620" metalness={0.85} roughness={0.15} />
        </mesh>
        <mesh position={[0, 0, -0.11]} rotation={[Math.PI / 2, 0, 0]}>
          <cylinderGeometry args={[0.038, 0.042, 0.06, 10]} />
          <meshStandardMaterial color="#080c14" metalness={0.95} roughness={0.05} />
        </mesh>
      </group>

      {/* 부스 라벨 */}
      <Text position={[0, aH + 0.28, 0]} fontSize={0.15} color="#6b7280" anchorX="center" characters={CHARS}>
        VISION BOOTH
      </Text>

      {/* 마지막 판정 표시 */}
      {lastVerdict && (
        <Text position={[0, aH * 0.28, -(aD / 2 + 0.04)]} fontSize={0.22}
          color={verdictColor} anchorX="center" characters={CHARS}>
          {lastVerdict}
        </Text>
      )}
    </group>
  )
}
