// RobotArm — G3 경량 장식 프롭. 키네매틱스/물리/URDF 없음.
// 작업영역 엔벨로프(반투명 토러스)로 가동 반경 시각화.
import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { useSignalStore } from '../../signalStore'
import { selectKpi } from '../../signalReducer'

const METAL_DARK = '#5c6e84'   // 밝은 산업용 회색 — 어두운 씬에서 가시성 확보
const METAL_MID  = '#6e8098'
const JOINT_C    = '#3e5268'

function Joint({ position, r = 0.12 }) {
  return (
    <mesh position={position} castShadow>
      <sphereGeometry args={[r, 10, 10]} />
      <meshStandardMaterial color={JOINT_C} metalness={0.8} roughness={0.2} />
    </mesh>
  )
}

export default function RobotArm({ position = [0, 0, 0], active = false }) {
  const kpi = useSignalStore(selectKpi)
  const isRunning = String(kpi.state || '').toLowerCase().startsWith('run')

  // 절차적 애니메이션: 베이스 회전 스캐닝 + 어깨/팔꿈치 사인 모션 (키네매틱스 아님)
  const groupRef = useRef()   // 베이스 요(yaw) 스캔
  const shoulderRef = useRef() // 어깨 피치
  const elbowRef = useRef()    // 팔꿈치 굽힘
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    const live = isRunning || active

    if (groupRef.current) {
      // 대기: 좌우로 넓게 스캐닝 / 가동·검사: 작업영역 쪽으로 집중 + 빠른 진동
      const target = live ? Math.sin(t * 1.4) * 0.42 - 0.25 : Math.sin(t * 0.35) * 0.55
      groupRef.current.rotation.y += (target - groupRef.current.rotation.y) * 0.08
    }
    if (shoulderRef.current) {
      const dip = active ? 0.22 : 0       // 부품 인입 시 집는 동작
      shoulderRef.current.rotation.z = -0.25 + Math.sin(t * (live ? 1.8 : 0.6)) * 0.08 + dip
    }
    if (elbowRef.current) {
      elbowRef.current.rotation.z = 0.65 + Math.sin(t * (live ? 2.1 : 0.5) + 1) * 0.10 - (active ? 0.18 : 0)
    }
  })

  return (
    <group position={position}>
      {/* 베이스 페데스탈 */}
      <mesh position={[0, 0.15, 0]} castShadow>
        <cylinderGeometry args={[0.26, 0.32, 0.30, 16]} />
        <meshStandardMaterial color="#3a4e62" metalness={0.7} roughness={0.35} />
      </mesh>
      <mesh position={[0, 0.32, 0]} castShadow>
        <cylinderGeometry args={[0.20, 0.26, 0.10, 16]} />
        <meshStandardMaterial color="#445870" metalness={0.72} roughness={0.28} />
      </mesh>

      {/* 어깨 하우징 */}
      <mesh position={[0, 0.55, 0]} castShadow>
        <boxGeometry args={[0.30, 0.36, 0.30]} />
        <meshStandardMaterial color={METAL_DARK} metalness={0.68} roughness={0.32} />
      </mesh>
      <Joint position={[0, 0.74, 0]} r={0.13} />

      {/* 상완 (약간 기울어짐) */}
      <group ref={groupRef} position={[0, 0.74, 0]}>
        <group ref={shoulderRef} rotation={[0, 0, -0.25]}>
          <mesh position={[0, 0.38, 0]} castShadow>
            <cylinderGeometry args={[0.088, 0.105, 0.76, 12]} />
            <meshStandardMaterial color={METAL_MID} metalness={0.65} roughness={0.35} />
          </mesh>
          <Joint position={[0, 0.76, 0]} r={0.115} />

          {/* 팔꿈치 관절 + 전완 */}
          <group ref={elbowRef} position={[0, 0.76, 0]} rotation={[0, 0, 0.65]}>
            <mesh position={[0, 0.26, 0]} castShadow>
              <cylinderGeometry args={[0.072, 0.088, 0.52, 10]} />
              <meshStandardMaterial color={METAL_DARK} metalness={0.7} roughness={0.30} />
            </mesh>
            <Joint position={[0, 0.52, 0]} r={0.095} />

            {/* 손목 */}
            <group position={[0, 0.52, 0]} rotation={[0, 0, -0.30]}>
              <mesh position={[0, 0.14, 0]} castShadow>
                <cylinderGeometry args={[0.055, 0.070, 0.28, 10]} />
                <meshStandardMaterial color={METAL_MID} metalness={0.72} roughness={0.28} />
              </mesh>

              {/* 엔드 이펙터 / 그리퍼 */}
              <group position={[0, 0.30, 0]}>
                <mesh castShadow>
                  <boxGeometry args={[0.13, 0.09, 0.13]} />
                  <meshStandardMaterial color="#344560" metalness={0.88} roughness={0.12} />
                </mesh>
                {/* 집게 손가락 */}
                {[[-0.042, 0], [0.042, 0]].map(([z], i) => (
                  <mesh key={i} position={[0, 0.07, z]} castShadow>
                    <boxGeometry args={[0.055, 0.10, 0.022]} />
                    <meshStandardMaterial color="#111828" metalness={0.92} roughness={0.08} />
                  </mesh>
                ))}
                {/* 그리퍼 LED */}
                <mesh position={[0.065, 0, 0]}>
                  <sphereGeometry args={[0.018, 6, 6]} />
                  <meshStandardMaterial
                    color={isRunning ? '#34d399' : '#f87171'}
                    emissive={isRunning ? '#34d399' : '#f87171'}
                    emissiveIntensity={isRunning ? 1.2 : 0.4} />
                </mesh>
              </group>
            </group>
          </group>
        </group>

        {/* 작업 영역 엔벨로프 — 반투명 반원호 */}
        <mesh rotation={[0, 0.8, 0]}>
          <torusGeometry args={[0.88, 0.016, 8, 40, Math.PI * 1.4]} />
          <meshStandardMaterial color="#1FB8CD" transparent opacity={0.18} depthWrite={false} />
        </mesh>
        <mesh rotation={[Math.PI / 2, 0, 0.5]}>
          <torusGeometry args={[0.88, 0.016, 8, 40, Math.PI]} />
          <meshStandardMaterial color="#1FB8CD" transparent opacity={0.10} depthWrite={false} />
        </mesh>
      </group>
    </group>
  )
}
