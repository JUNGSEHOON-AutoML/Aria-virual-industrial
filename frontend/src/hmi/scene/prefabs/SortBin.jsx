// SortBin — OK/NG 분류함 프리팹. count는 부모에서 props로 전달.
import { Text } from '@react-three/drei'
const CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 :·'

export default function SortBin({ position = [0, 0, 0], kind = 'OK', count = 0 }) {
  const isOK = kind === 'OK'
  const accent = isOK ? '#34d399' : '#f87171'
  const frame = '#16191f'
  const w = 1.05, h = 0.7, d = 0.88

  return (
    <group position={position}>
      {/* 뒷판 */}
      <mesh position={[0, h / 2, -d / 2 + 0.03]} castShadow>
        <boxGeometry args={[w, h, 0.07]} />
        <meshStandardMaterial color={frame} metalness={0.5} roughness={0.5} />
      </mesh>
      {/* 바닥 */}
      <mesh position={[0, 0.035, 0]} receiveShadow>
        <boxGeometry args={[w, 0.07, d]} />
        <meshStandardMaterial color={frame} metalness={0.5} roughness={0.5} />
      </mesh>
      {/* 왼쪽 벽 */}
      <mesh position={[-w / 2, h / 2, 0]}>
        <boxGeometry args={[0.07, h, d]} />
        <meshStandardMaterial color={frame} metalness={0.5} roughness={0.5} />
      </mesh>
      {/* 오른쪽 벽 */}
      <mesh position={[w / 2, h / 2, 0]}>
        <boxGeometry args={[0.07, h, d]} />
        <meshStandardMaterial color={frame} metalness={0.5} roughness={0.5} />
      </mesh>
      {/* 전면 하단 가드(입구 개방) */}
      <mesh position={[0, 0.12, d / 2 - 0.03]}>
        <boxGeometry args={[w, 0.24, 0.07]} />
        <meshStandardMaterial color={frame} metalness={0.5} roughness={0.5} />
      </mesh>

      {/* 상단 악센트 띠 */}
      <mesh position={[0, h + 0.025, 0]}>
        <boxGeometry args={[w, 0.05, d]} />
        <meshStandardMaterial color={accent} emissive={accent} emissiveIntensity={0.45} />
      </mesh>

      {/* 카운터 레이블 */}
      <Text position={[0, h + 0.22, 0]} fontSize={0.2} color={accent} anchorX="center" characters={CHARS}>
        {`${kind} · ${count}`}
      </Text>
    </group>
  )
}
