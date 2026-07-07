// InspectionArm — 검사용 로봇 팔(연속 동작). VisionBooth 대체.
// 엔드이펙터에 비전 카메라 + 초점 콘. 항상 스캔 모션(검사 중엔 빠르고 집중). 키네매틱스/물리 없음(절차적 애니).
// 바인딩: inspector_state(kpi.state) + inspector_result(scan) — dwell 펄스·verdict·플래시.
import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Text } from '@react-three/drei'
import * as THREE from 'three'
import { useSignalStore } from '../../signalStore'
import { selectKpi, selectScan } from '../../signalReducer'

const CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ·_-%.:'
const METAL = '#5c6e84'
const METAL_D = '#3e5268'
const JOINT = '#24293a'
const DOME_C = '#1FB8CD'

function Joint({ r = 0.1 }) {
  return (
    <mesh castShadow><sphereGeometry args={[r, 12, 12]} />
      <meshStandardMaterial color={JOINT} metalness={0.8} roughness={0.2} /></mesh>
  )
}

export default function InspectionArm({ position = [0, 0, 0], dwelling = false, laneScan = null }) {
  const kpi = useSignalStore(selectKpi)
  const globalScan = useSignalStore(selectScan)
  const scan = laneScan || globalScan   // 레인별 scan 우선(멀티레인)
  const isRunning = kpi.state === 'running'
  const live = isRunning || dwelling

  const baseRef = useRef()    // 베이스 yaw
  const shoulderRef = useRef()
  const elbowRef = useRef()
  const wristRef = useRef()
  const domeRef = useRef()
  const coneRef = useRef()
  const flashT = useRef(0)
  const lastScanId = useRef(null)

  const lastVerdict = scan?.verdict
  const verdictColor = lastVerdict === 'NG' ? '#f87171' : lastVerdict === 'OK' ? '#34d399' : '#9aa3b2'

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    const sp = live ? 1.6 : 0.5            // 검사 중 빠르게
    // 연속 스캔 모션 — 항상 움직임
    if (baseRef.current) baseRef.current.rotation.y = Math.sin(t * 0.5 * sp) * (live ? 0.3 : 0.5)
    if (shoulderRef.current) shoulderRef.current.rotation.x = -0.5 + Math.sin(t * 0.9 * sp) * 0.14
    if (elbowRef.current) elbowRef.current.rotation.x = 0.9 + Math.sin(t * 1.1 * sp + 1) * 0.18
    if (wristRef.current) wristRef.current.rotation.x = Math.sin(t * 1.4 * sp) * 0.22 + (live ? 0.3 : 0.1)

    // 새 스캔 → 플래시
    if (scan && scan.part_id !== lastScanId.current) { lastScanId.current = scan.part_id; flashT.current = 1.0 }
    if (flashT.current > 0) flashT.current = Math.max(0, flashT.current - 0.04)
    if (domeRef.current) {
      const pulse = live ? 0.55 + Math.sin(t * 9) * 0.45 : 0.15
      domeRef.current.material.emissiveIntensity = Math.max(pulse, flashT.current * 2.2)
    }
    if (coneRef.current) coneRef.current.material.opacity = live ? 0.18 : 0.06
  })

  return (
    <group position={position}>
      {/* 베이스 페데스탈(컨베이어 옆) */}
      <group position={[0, 0, 1.05]}>
        <mesh position={[0, 0.12, 0]} castShadow>
          <cylinderGeometry args={[0.26, 0.32, 0.24, 20]} />
          <meshStandardMaterial color="#1e2433" metalness={0.7} roughness={0.35} />
        </mesh>

        {/* 베이스 yaw */}
        <group ref={baseRef} position={[0, 0.26, 0]}>
          <mesh position={[0, 0.12, 0]} castShadow>
            <boxGeometry args={[0.3, 0.28, 0.3]} />
            <meshStandardMaterial color={METAL_D} metalness={0.7} roughness={0.3} />
          </mesh>
          <Joint r={0.14} />

          {/* 어깨 → 상완 */}
          <group ref={shoulderRef} position={[0, 0.14, 0]}>
            <mesh position={[0, 0.42, 0]} castShadow>
              <cylinderGeometry args={[0.085, 0.1, 0.84, 12]} />
              <meshStandardMaterial color={METAL} metalness={0.65} roughness={0.35} />
            </mesh>
            <group position={[0, 0.84, 0]}>
              <Joint r={0.11} />
              {/* 팔꿈치 → 전완 */}
              <group ref={elbowRef}>
                <mesh position={[0, 0.34, 0]} castShadow>
                  <cylinderGeometry args={[0.07, 0.085, 0.68, 10]} />
                  <meshStandardMaterial color={METAL_D} metalness={0.7} roughness={0.3} />
                </mesh>
                <group position={[0, 0.68, 0]}>
                  <Joint r={0.085} />
                  {/* 손목 → 카메라 헤드 */}
                  <group ref={wristRef}>
                    <mesh position={[0, 0.16, 0]} castShadow>
                      <cylinderGeometry args={[0.055, 0.07, 0.3, 10]} />
                      <meshStandardMaterial color={METAL} metalness={0.72} roughness={0.28} />
                    </mesh>
                    {/* 카메라 헤드(아래 방향) */}
                    <group position={[0, 0.34, 0]}>
                      <mesh castShadow>
                        <boxGeometry args={[0.18, 0.16, 0.2]} />
                        <meshStandardMaterial color="#111620" metalness={0.85} roughness={0.15} />
                      </mesh>
                      {/* 렌즈(하단) */}
                      <mesh position={[0, -0.1, 0]} rotation={[0, 0, 0]}>
                        <cylinderGeometry args={[0.05, 0.055, 0.06, 12]} />
                        <meshStandardMaterial color="#080c14" metalness={0.95} roughness={0.05} />
                      </mesh>
                      {/* 돔 라이트(펄스) */}
                      <mesh ref={domeRef} position={[0, 0.13, 0]}>
                        <sphereGeometry args={[0.07, 12, 12]} />
                        <meshStandardMaterial color={DOME_C} emissive={DOME_C} emissiveIntensity={0.15} />
                      </mesh>
                      {/* 초점 콘(아래로) */}
                      <mesh ref={coneRef} position={[0, -0.55, 0]}>
                        <coneGeometry args={[0.34, 0.9, 16, 1, true]} />
                        <meshStandardMaterial color={DOME_C} transparent opacity={0.1}
                          side={THREE.DoubleSide} depthWrite={false} />
                      </mesh>
                    </group>
                  </group>
                </group>
              </group>
            </group>
          </group>
        </group>
      </group>

      {/* 라벨 + 마지막 판정 */}
      <Text position={[0, 2.5, 1.05]} fontSize={0.14} color="#6b7280" anchorX="center" characters={CHARS}>
        INSPECTION ARM
      </Text>
      {lastVerdict && (
        <Text position={[0, 1.5, 0]} fontSize={0.2} color={verdictColor} anchorX="center" characters={CHARS}>
          {lastVerdict}
        </Text>
      )}
    </group>
  )
}
