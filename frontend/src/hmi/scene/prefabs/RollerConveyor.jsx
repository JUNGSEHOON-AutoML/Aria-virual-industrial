// RollerConveyor — 롤러 컨베이어 프리팹. 롤러는 InstancedMesh(드로우콜 1회).
// 가동 중(running)이면 벨트 표면 텍스처가 UV offset으로 흐른다.
import { useRef, useEffect, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { makeBeltTexture } from '../textures'

const FRAME = '#222838'
const ROLLER = '#4a5568'
const LEG = '#1a1f2c'
const ROLLER_R = 0.034

// 흐르는 벨트 표면 — UV offset 애니메이션으로 가동감 표현
function Belt({ length, width, running, speed }) {
  const matRef = useRef()
  const tex = useMemo(() => makeBeltTexture(), [])
  useMemo(() => { tex.repeat.set(Math.max(2, length * 2.2), 1) }, [tex, length])

  useFrame((_, dt) => {
    if (running) tex.offset.x -= dt * (speed ?? 0.6)
  })

  return (
    <mesh position={[0, ROLLER_R + 0.002, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
      <planeGeometry args={[length, width * 0.86]} />
      <meshStandardMaterial ref={matRef} map={tex} color="#3a4356"
        metalness={0.35} roughness={0.7} />
    </mesh>
  )
}

function Rollers({ length, width, count }) {
  const ref = useRef()
  useEffect(() => {
    if (!ref.current) return
    const dummy = new THREE.Object3D()
    for (let i = 0; i < count; i++) {
      const x = (i / Math.max(1, count - 1)) * length - length / 2
      dummy.position.set(x, 0, 0)
      dummy.rotation.set(Math.PI / 2, 0, 0)   // 롤러 축 = Z방향
      dummy.updateMatrix()
      ref.current.setMatrixAt(i, dummy.matrix)
    }
    ref.current.instanceMatrix.needsUpdate = true
  }, [count, length, width])

  return (
    <instancedMesh ref={ref} args={[undefined, undefined, count]} castShadow>
      <cylinderGeometry args={[ROLLER_R, ROLLER_R, width * 0.90, 8]} />
      <meshStandardMaterial color={ROLLER} metalness={0.78} roughness={0.22} />
    </instancedMesh>
  )
}

export default function RollerConveyor({ length = 4, width = 0.9, position = [0, 0, 0],
  rotation = [0, 0, 0], running = true, speed = 0.6 }) {
  const count = Math.max(2, Math.floor(length / 0.26))
  const legXs = []
  for (let x = -length / 2 + 0.8; x < length / 2; x += 1.4) legXs.push(x)

  const rail = { w: length, h: 0.045, d: 0.07 }

  return (
    <group position={position} rotation={rotation}>
      {/* 왼쪽 레일 */}
      <mesh position={[0, 0, -width / 2 + 0.035]} castShadow>
        <boxGeometry args={[rail.w, rail.h, rail.d]} />
        <meshStandardMaterial color={FRAME} metalness={0.5} roughness={0.5} />
      </mesh>
      {/* 오른쪽 레일 */}
      <mesh position={[0, 0, width / 2 - 0.035]} castShadow>
        <boxGeometry args={[rail.w, rail.h, rail.d]} />
        <meshStandardMaterial color={FRAME} metalness={0.5} roughness={0.5} />
      </mesh>

      {/* 흐르는 벨트 표면 */}
      <Belt length={length} width={width} running={running} speed={speed} />

      {/* 롤러 (InstancedMesh) */}
      <Rollers length={length} width={width} count={count} />

      {/* 지지 다리 */}
      {legXs.map((x, i) => (
        <group key={i} position={[x, -0.28, 0]}>
          <mesh position={[0, 0, -width / 2 + 0.05]}>
            <boxGeometry args={[0.055, 0.56, 0.055]} />
            <meshStandardMaterial color={LEG} metalness={0.45} roughness={0.55} />
          </mesh>
          <mesh position={[0, 0, width / 2 - 0.05]}>
            <boxGeometry args={[0.055, 0.56, 0.055]} />
            <meshStandardMaterial color={LEG} metalness={0.45} roughness={0.55} />
          </mesh>
          {/* 가로 크로스 브레이스 */}
          <mesh position={[0, -0.05, 0]}>
            <boxGeometry args={[0.055, 0.055, width - 0.1]} />
            <meshStandardMaterial color={LEG} metalness={0.45} roughness={0.55} />
          </mesh>
        </group>
      ))}
    </group>
  )
}
