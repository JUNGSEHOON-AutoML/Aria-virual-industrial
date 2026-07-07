// LaserMarker — 표면 (x,y,z)에 결함 지시 레이저 투영 (E-FOREST 시그니처의 트윈판).
// 가상 투사기에서 내려오는 발광 빔 + 표면 십자선/링 + 점멸. 위치는 coordinateTransform 산출(난수 아님).
import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

export default function LaserMarker({ point, normal, color = '#ff3344', projectorHeight = 3.2 }) {
  const beamRef = useRef()
  const crossRef = useRef()
  const ringRef = useRef()

  const p = useMemo(() => (point?.isVector3 ? point : new THREE.Vector3(...(point || [0, 0, 0]))), [point])
  const n = useMemo(() => (normal?.isVector3 ? normal : new THREE.Vector3(...(normal || [0, 1, 0]))), [normal])

  // 빔: 천장 투사기(point 바로 위)에서 point로
  const beamMid = useMemo(() => p.clone().add(new THREE.Vector3(0, projectorHeight / 2, 0)), [p, projectorHeight])

  // 십자선/링을 표면 법선에 맞춰 회전
  const quat = useMemo(() => {
    const q = new THREE.Quaternion()
    q.setFromUnitVectors(new THREE.Vector3(0, 0, 1), n.clone().normalize())
    return q
  }, [n])

  useFrame(({ clock }) => {
    const blink = 0.55 + Math.abs(Math.sin(clock.getElapsedTime() * 6)) * 0.45
    if (beamRef.current) beamRef.current.material.opacity = 0.18 * blink
    if (crossRef.current) crossRef.current.children.forEach(c => { c.material.emissiveIntensity = 1.4 * blink })
    if (ringRef.current) {
      ringRef.current.material.emissiveIntensity = 1.2 * blink
      ringRef.current.rotation.z = clock.getElapsedTime() * 2
    }
  })

  return (
    <group>
      {/* 투사 빔 */}
      <mesh ref={beamRef} position={beamMid}>
        <cylinderGeometry args={[0.012, 0.012, projectorHeight, 6]} />
        <meshBasicMaterial color={color} transparent opacity={0.18} depthWrite={false} />
      </mesh>
      {/* 가상 투사기(천장) */}
      <mesh position={p.clone().add(new THREE.Vector3(0, projectorHeight, 0))}>
        <boxGeometry args={[0.14, 0.08, 0.14]} />
        <meshStandardMaterial color="#1a2230" emissive={color} emissiveIntensity={0.5} metalness={0.7} roughness={0.3} />
      </mesh>

      {/* 표면 십자선 + 링 (법선 정렬) */}
      <group position={p.clone().addScaledVector(n, 0.004)} quaternion={quat}>
        <group ref={crossRef}>
          <mesh>
            <boxGeometry args={[0.18, 0.012, 0.001]} />
            <meshStandardMaterial color={color} emissive={color} emissiveIntensity={1.4} transparent opacity={0.95} />
          </mesh>
          <mesh>
            <boxGeometry args={[0.012, 0.18, 0.001]} />
            <meshStandardMaterial color={color} emissive={color} emissiveIntensity={1.4} transparent opacity={0.95} />
          </mesh>
        </group>
        <mesh ref={ringRef}>
          <ringGeometry args={[0.085, 0.11, 24]} />
          <meshStandardMaterial color={color} emissive={color} emissiveIntensity={1.2}
            side={THREE.DoubleSide} transparent opacity={0.85} depthWrite={false} />
        </mesh>
      </group>
    </group>
  )
}
