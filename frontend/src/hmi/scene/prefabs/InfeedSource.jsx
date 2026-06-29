// InfeedSource — 호퍼(인입) 프리팹. 부품 공급 시작점.
import { Text } from '@react-three/drei'
const CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ·_-'

export default function InfeedSource({ position = [0, 0, 0], material = '' }) {
  return (
    <group position={position}>
      {/* 호퍼 바디 */}
      <mesh position={[0, 0.85, 0]} castShadow>
        <boxGeometry args={[0.75, 0.9, 0.75]} />
        <meshStandardMaterial color="#2a3040" metalness={0.55} roughness={0.45} />
      </mesh>
      {/* 호퍼 하단 출구(좁은 목) */}
      <mesh position={[0.2, 0.42, 0]} castShadow>
        <boxGeometry args={[0.38, 0.36, 0.52]} />
        <meshStandardMaterial color="#232a38" metalness={0.55} roughness={0.5} />
      </mesh>
      {/* 베이스 프레임 */}
      <mesh position={[0, 0.08, 0]} receiveShadow>
        <boxGeometry args={[0.85, 0.16, 0.85]} />
        <meshStandardMaterial color="#16191f" metalness={0.4} roughness={0.7} />
      </mesh>
      {/* 측면 가드 포스트 4개 */}
      {[[-0.42, 0.45, -0.42], [-0.42, 0.45, 0.42], [0.42, 0.45, -0.42], [0.42, 0.45, 0.42]].map((p, i) => (
        <mesh key={i} position={p} castShadow>
          <boxGeometry args={[0.06, 0.9, 0.06]} />
          <meshStandardMaterial color="#1e2433" metalness={0.45} roughness={0.55} />
        </mesh>
      ))}
      {/* 상단 가드 레일 */}
      <mesh position={[0, 1.32, 0]} castShadow>
        <boxGeometry args={[0.84, 0.06, 0.84]} />
        <meshStandardMaterial color="#1e2433" metalness={0.45} roughness={0.55} />
      </mesh>
      {/* 레이블 */}
      <Text position={[0, 1.62, 0]} fontSize={0.14} color="#6b7280" anchorX="center" characters={CHARS}>
        {material ? `SRC · ${material.toUpperCase()}` : 'INFEED SOURCE'}
      </Text>
    </group>
  )
}
