// Smooth display transforms only. Engineering retains direct authoritative poses.
import { useContext, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { PresentationContext } from './PresentationContext'
export default function MotionGroup({ position = [0, 0, 0], rotation = [0, 0, 0], children }) {
  const ref = useRef(), previous = useRef({}), initialized = useRef(false)
  const { smooth, paused, readClock } = useContext(PresentationContext)
  const p = useMemo(() => new THREE.Vector3(...position), [position[0], position[1], position[2]])
  const q = useMemo(() => new THREE.Quaternion().setFromEuler(new THREE.Euler(...rotation)), [rotation[0], rotation[1], rotation[2]])
  useFrame((_, dt) => {
    if (!ref.current) return
    const clock = readClock?.() || {}, reset = clock.run !== previous.current.run
    const step = paused && clock.time !== previous.current.time
    previous.current = clock
    if (!smooth || !initialized.current || reset || step) {
      ref.current.position.copy(p); ref.current.quaternion.copy(q); initialized.current = true
    } else if (!paused) {
      const alpha = 1 - Math.exp(-12 * dt)
      ref.current.position.lerp(p, alpha); ref.current.quaternion.slerp(q, alpha)
    }
  })
  return <group ref={ref}>{children}</group>
}
