// WorkerAgent — 유지보수 에이전트 아바타(경량 캡슐 프록시). 명세 §6.
// 리깅 GLB 없이 캡슐+드론 마커. task에 따라 대상 설비로 lerp 이동 + 수리 이펙트.
// 키네매틱스/물리 없음. signalStore.agent 구독.
import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { useSignalStore } from '../signalStore'
import { ASSET_GROUND } from './assetModel'

const HOME = [-9.2, 0, 3.2]

export default function WorkerAgent() {
  const agent = useSignalStore(s => s.agent) || {}
  const groupRef = useRef()
  const ringRef = useRef()
  const partsRef = useRef()

  const target = useMemo(() => {
    if ((agent.task === 'MOVING' || agent.task === 'REPAIRING') && agent.targetAssetId)
      return ASSET_GROUND[agent.targetAssetId] || HOME
    return HOME
  }, [agent.task, agent.targetAssetId])

  // 수리 파티클(작은 점 군집)
  const sparks = useMemo(() => {
    const g = new THREE.BufferGeometry()
    const n = 24, arr = new Float32Array(n * 3)
    for (let i = 0; i < n; i++) { arr[i * 3] = (Math.random() - 0.5) * 0.5; arr[i * 3 + 1] = Math.random() * 0.6; arr[i * 3 + 2] = (Math.random() - 0.5) * 0.5 }
    g.setAttribute('position', new THREE.BufferAttribute(arr, 3))
    return g
  }, [])

  const connected = useSignalStore(s => s.wsStatus) === 'open'

  useFrame(({ clock }, dt) => {
    const g = groupRef.current
    if (!g || !connected) return   // 끊기면 freeze
    // 목표로 부드럽게 이동(lerp)
    g.position.x += (target[0] - g.position.x) * Math.min(1, dt * 2.2)
    g.position.z += (target[2] - g.position.z) * Math.min(1, dt * 2.2)
    // 진행 방향 바라보기
    const dx = target[0] - g.position.x, dz = target[2] - g.position.z
    if (Math.abs(dx) + Math.abs(dz) > 0.02) g.rotation.y = Math.atan2(dx, dz)

    const repairing = agent.task === 'REPAIRING'
    if (ringRef.current) {
      ringRef.current.visible = repairing
      ringRef.current.rotation.z = clock.getElapsedTime() * 3
    }
    if (partsRef.current) {
      partsRef.current.visible = repairing
      partsRef.current.rotation.y = clock.getElapsedTime() * 2
      const s = 0.8 + Math.sin(clock.getElapsedTime() * 9) * 0.2
      partsRef.current.scale.setScalar(s)
    }
  })

  const taskColor = agent.task === 'REPAIRING' ? '#facc15'
    : agent.task === 'MOVING' ? '#1FB8CD' : '#7c8aa0'

  return (
    <group ref={groupRef} position={HOME}>
      {/* 몸통 캡슐 */}
      <mesh position={[0, 0.55, 0]} castShadow>
        <capsuleGeometry args={[0.16, 0.5, 6, 14]} />
        <meshStandardMaterial color={taskColor} metalness={0.4} roughness={0.5}
          emissive={taskColor} emissiveIntensity={agent.task === 'IDLE' ? 0.05 : 0.3} />
      </mesh>
      {/* 머리 */}
      <mesh position={[0, 1.0, 0]} castShadow>
        <sphereGeometry args={[0.13, 16, 16]} />
        <meshStandardMaterial color="#d6deea" metalness={0.3} roughness={0.6} />
      </mesh>
      {/* 상태등 */}
      <mesh position={[0, 1.28, 0]}>
        <sphereGeometry args={[0.05, 8, 8]} />
        <meshStandardMaterial color={taskColor} emissive={taskColor} emissiveIntensity={1.2} />
      </mesh>

      {/* 수리 링(REPAIRING 시) */}
      <mesh ref={ringRef} position={[0, 0.05, 0.35]} rotation={[-Math.PI / 2, 0, 0]} visible={false}>
        <ringGeometry args={[0.18, 0.26, 20]} />
        <meshStandardMaterial color="#facc15" emissive="#facc15" emissiveIntensity={1.0}
          transparent opacity={0.7} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      {/* 수리 스파크 파티클 */}
      <points ref={partsRef} position={[0, 0.2, 0.4]} visible={false} geometry={sparks}>
        <pointsMaterial size={0.05} color="#ffd66b" transparent opacity={0.9} />
      </points>

      {/* 라벨 */}
      <mesh position={[0, 1.5, 0]} visible={false} />
    </group>
  )
}
