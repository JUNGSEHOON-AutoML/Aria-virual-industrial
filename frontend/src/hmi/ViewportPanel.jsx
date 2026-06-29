// 중앙 3D 디지털트윈 뷰포트 — 기존 R3F FactoryLine 씬 재사용 + WS 신호 바인딩.
import { useState, useEffect } from 'react'
import { Canvas } from '@react-three/fiber'
import { Grid, OrbitControls } from '@react-three/drei'
import FactoryLine, { MVTEC_CLASSES } from '../sim/factory'
import { subscribe } from './twinStore'
import { useTwinSignal } from './useTwin'

function InspectionLights() {
  return (
    <>
      <pointLight position={[0, 2.05, 0]} intensity={0.8} color="#e8f4ff" distance={3} />
      <spotLight position={[-2, 3, 0]} angle={0.4} penumbra={0.5} intensity={0.6} color="#fff8f0" castShadow />
      <spotLight position={[2, 3, 0]} angle={0.4} penumbra={0.5} intensity={0.6} color="#fff8f0" castShadow />
    </>
  )
}

export default function ViewportPanel({ classes }) {
  const jointMsg = useTwinSignal('joint_state')
  const trainState = useTwinSignal('training')
  const [classResults, setClassResults] = useState({})
  const [validation, setValidation] = useState(null)
  const [cycle, setCycle] = useState(0)

  useEffect(() => subscribe('class_result', (d) => {
    setClassResults(prev => ({ ...prev, [d.classId]: d }))
    if (d.fat_verdict) setValidation(d)
  }), [])

  useEffect(() => subscribe('training', (d) => {
    if (d.status === 'done') setCycle(c => c + 1)
  }), [])

  const lines = (classes && classes.length) ? classes : MVTEC_CLASSES
  const jointState = jointMsg?.joints || null
  const looping = trainState?.status === 'running'

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <Canvas shadows camera={{ position: [5, 3.4, 6], fov: 50 }} gl={{ antialias: true }}>
        <color attach="background" args={['#0b0d12']} />
        <ambientLight intensity={0.42} />
        <directionalLight position={[5, 8, 5]} intensity={1.1} color="#ffffff" castShadow
          shadow-mapSize-width={1024} shadow-mapSize-height={1024} />
        <directionalLight position={[-4, 3, -4]} intensity={0.2} color="#3a5080" />
        <InspectionLights />
        <FactoryLine classes={lines} classResults={classResults} trainState={trainState}
          validation={validation} looping={looping} cycle={cycle} jointState={jointState} />
        <Grid args={[24, 24]} cellColor="#1c2030" sectionColor="#2a3040" infiniteGrid
          fadeDistance={28} fadeStrength={1.5} />
        <OrbitControls enableDamping dampingFactor={0.08} makeDefault minDistance={2} maxDistance={16} />
      </Canvas>
    </div>
  )
}
