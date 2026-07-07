// Diverter — 판정 기반 물리 분기 프리팹 (verdict=NG → 푸셔 암 스윙)
// 라이브 바인딩: inspector_result.verdict (selectScan)
import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Text } from '@react-three/drei'
import { useSignalStore } from '../../signalStore'
import { selectScan } from '../../signalReducer'

const CHARS = 'NGO K·-'
const FRAME = '#1e2433'
const ARM_OK = '#3a4150'
const ARM_NG = '#f87171'

export default function Diverter({ position = [0, 0, 0], ngActive = false }) {
  const scan = useSignalStore(selectScan)
  const armRef = useRef()
  const ledRef = useRef()

  // ngActive prop 우선, 없으면 store에서
  const isNG = ngActive || scan?.verdict === 'NG'

  useFrame(() => {
    if (!armRef.current) return
    const target = isNG ? -Math.PI / 2.8 : 0
    armRef.current.rotation.y += (target - armRef.current.rotation.y) * 0.10

    if (ledRef.current) {
      ledRef.current.material.emissiveIntensity = isNG ? 1.4 : 0.1
      ledRef.current.material.color.setStyle(isNG ? ARM_NG : '#34d399')
      ledRef.current.material.emissive.setStyle(isNG ? ARM_NG : '#34d399')
    }
  })

  return (
    <group position={position}>
      {/* 베이스 프레임 */}
      <mesh position={[0, 0.18, 0.55]} castShadow>
        <boxGeometry args={[0.32, 0.36, 0.36]} />
        <meshStandardMaterial color={FRAME} metalness={0.6} roughness={0.4} />
      </mesh>
      {/* 후방 프레임 스트립 */}
      <mesh position={[0, 0.18, -0.18]} castShadow>
        <boxGeometry args={[0.65, 0.32, 0.10]} />
        <meshStandardMaterial color={FRAME} metalness={0.55} roughness={0.45} />
      </mesh>

      {/* 푸셔 암 (pivot at [0, 0.34, 0.4]) */}
      <group ref={armRef} position={[0, 0.34, 0.44]}>
        <mesh position={[0, 0, -0.44]} castShadow>
          <boxGeometry args={[0.085, 0.115, 0.88]} />
          <meshStandardMaterial color={isNG ? ARM_NG : ARM_OK}
            emissive={isNG ? ARM_NG : '#000'} emissiveIntensity={isNG ? 0.28 : 0}
            metalness={0.5} roughness={0.4} />
        </mesh>
        {/* 암 팁 */}
        <mesh position={[0, 0, -0.9]} castShadow>
          <boxGeometry args={[0.085, 0.20, 0.06]} />
          <meshStandardMaterial color="#2a3040" metalness={0.6} roughness={0.3} />
        </mesh>
      </group>

      {/* 상태 LED */}
      <mesh ref={ledRef} position={[0, 0.5, 0.72]}>
        <sphereGeometry args={[0.06, 10, 10]} />
        <meshStandardMaterial color="#34d399" emissive="#34d399" emissiveIntensity={0.1} />
      </mesh>

      {/* 레이블 */}
      <Text position={[0, 0.78, 0.55]} fontSize={0.12} color="#6b7280" anchorX="center" characters={CHARS}>
        {isNG ? 'NG ▶' : 'OK ▶'}
      </Text>
    </group>
  )
}
