import { useMemo, useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Html, Line, TransformControls } from '@react-three/drei'
import * as THREE from 'three'
import RollerConveyor from '../scene/prefabs/RollerConveyor'
import { Equipment, FactoryBuilding } from './IndustrialEquipment'
import PatrolHumanoids from './PatrolHumanoids'

const COLORS = { IDLE: '#697f97', STARVED: '#73a2b6', PROCESSING: '#2dd4bf', BLOCKED: '#ffb454', DOWN: '#fb7185', SETUP: '#a78bfa', MAINTENANCE: '#e879f9' }
const KIND_COLOR = { Source: '#60a5fa', Buffer: '#fbbf24', Machine: '#2dd4bf', Inspection: '#a78bfa', Diverter: '#fb923c', Sink: '#60a5fa' }

function Unit({ component: c, resource, selected, onSelect, part, time, labels }) {
  const accent = COLORS[resource?.state] || KIND_COLOR[c.kind]
  return <group onClick={e => { e.stopPropagation(); onSelect(c.id) }}>
    {c.kind === 'Conveyor'
      ? <RollerConveyor length={c.length} width={1.1} position={[0, .86, 0]} running={false} />
      : <Equipment component={c} resource={resource} part={part} time={time} />}
    {selected && <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, .04, 0]}><ringGeometry args={[1.5, 1.56, 48]} /><meshBasicMaterial color="#1385bc" /></mesh>}
    {(labels || selected) && <Html position={[0, ['Machine', 'Inspection'].includes(c.kind) ? 3.8 : 1.8, 0]} center zIndexRange={[20, 0]}>
      <button className={`factory-label ${selected ? 'selected' : ''}`} onClick={() => onSelect(c.id)}>
        <b>{c.id}</b><span style={{ color: accent }}>{resource?.state || 'IDLE'} · {resource?.occupancy || 0}/{c.capacity}</span>
        {c.kind === 'Inspection' && <small>{c.inspection_mode.toUpperCase()}</small>}
      </button>
    </Html>}
  </group>
}

function EditableUnit({ component, resource, selected, editMode, onSelect, onMove, part, time, labels }) {
  const ref = useRef()
  const mesh = <group ref={ref} position={component.position} rotation={[0, component.rotation, 0]}>
    <Unit component={component} resource={resource} selected={selected} onSelect={onSelect} part={part} time={time} labels={labels} />
  </group>
  return <>{mesh}{selected && editMode && <TransformControls object={ref} mode="translate" showY={false} onMouseUp={() => {
    if (ref.current) {
      const position = ref.current.position.toArray().map(v => Math.round(v * 10) / 10)
      onMove(component.id, position)
      ref.current.position.fromArray(component.position)
    }
  }} />}</>
}

function Parts({ snapshot }) {
  const ref = useRef()
  const positions = useRef(new Map())
  const dummy = useMemo(() => new THREE.Object3D(), [])
  const components = useMemo(() => new Map(snapshot.model.components.map(c => [c.id, c])), [snapshot.model])
  useFrame((_, dt) => {
    if (!ref.current) return
    const live = new Set()
    const offsets = new Map()
    snapshot.parts.slice(0, 2000).forEach((p, i) => {
      live.add(p.id)
      const c = components.get(p.component)
      if (!c) return
      const idx = offsets.get(c.id) || 0
      offsets.set(c.id, idx + 1)
      const target = new THREE.Vector3(...c.position)
      target.y += 1
      target.z += (idx % 3 - 1) * .3
      target.x += (Math.floor(idx / 3) % 4 - 1.5) * .25
      if (c.kind === 'Machine') target.z += .3
      if (c.kind === 'Conveyor') {
        const progress = Math.min(1, Math.max(0, (snapshot.time - p.entered) / Math.max(p.due - p.entered, .01)))
        target.x += (progress - .5) * c.length
      }
      target.sub(new THREE.Vector3(...c.position)).applyAxisAngle(new THREE.Vector3(0, 1, 0), c.rotation).add(new THREE.Vector3(...c.position))
      let position = positions.current.get(p.id)
      if (!position) {
        const move = [...snapshot.moves].reverse().find(m => m.part === p.id && m.source)
        position = move && components.has(move.source) ? new THREE.Vector3(...components.get(move.source).position).add(new THREE.Vector3(0, 1, 0)) : target.clone()
        positions.current.set(p.id, position)
      }
      position.lerp(target, 1 - Math.exp(-dt * 9))
      dummy.position.copy(position); dummy.updateMatrix()
      ref.current.setMatrixAt(i, dummy.matrix)
      ref.current.setColorAt(i, new THREE.Color(p.verdict === 'NG' ? '#fb7185' : p.verdict === 'OK' ? '#34d399' : p.verdict === 'SKIPPED' ? '#fbbf24' : '#e2e8f0'))
    })
    for (const id of positions.current.keys()) if (!live.has(id)) positions.current.delete(id)
    ref.current.count = Math.min(snapshot.parts.length, 2000)
    ref.current.instanceMatrix.needsUpdate = true
    if (ref.current.instanceColor) ref.current.instanceColor.needsUpdate = true
  })
  return <instancedMesh ref={ref} args={[undefined, undefined, 2000]} frustumCulled={false}>
    <boxGeometry args={[.22, .22, .22]} /><meshStandardMaterial roughness={.45} metalness={.2} />
  </instancedMesh>
}

export default function FactoryScene({ snapshot, selected, onSelect, editMode, onMove, view = 'overview', labels = false, paths = false }) {
  const nodes = new Map(snapshot.model.components.map(c => [c.id, c]))
  const focus = nodes.get(selected) || snapshot.model.components.find(c => c.kind === 'Machine') || snapshot.model.components[0]
  const visibleComponents = view === 'cell' ? [focus] : snapshot.model.components
  const visibleSnapshot = view === 'cell' ? { ...snapshot, parts: snapshot.parts.filter(p => p.component === focus.id) } : snapshot
  const center = snapshot.model.components.reduce((a, c) => a.map((v, i) => v + c.position[i] / snapshot.model.components.length), [0, 0, 0])
  const target = view === 'cell' ? [focus.position[0], 1, focus.position[2] + 1] : [center[0], 0, center[2]]
  const camera = view === 'cell' ? [target[0] + 5.5, 5, target[2] + 7] : view === 'top' ? [center[0], 35, center[2] + .01] : [center[0] + 9, 17, center[2] + 24]
  return <Canvas key={`${view}-${view === 'cell' ? focus.id : ''}`} shadows camera={{ position: camera, fov: 38 }} dpr={[1, 1.5]} onPointerMissed={() => onSelect(null)}>
    <color attach="background" args={['#737f85']} />
    <ambientLight intensity={.65} /><hemisphereLight args={['#f4f6ff', '#666656', 1.2]} />
    <directionalLight position={[4, 18, 10]} intensity={2.4} castShadow shadow-mapSize={[2048, 2048]} shadow-camera-left={-24} shadow-camera-right={24} shadow-camera-top={18} shadow-camera-bottom={-18} shadow-normalBias={.04} />
    <FactoryBuilding components={snapshot.model.components} />
    {view !== 'cell' && snapshot.model.connections.map(e => {
      const a = nodes.get(e.source).position, b = nodes.get(e.target).position
      const distance = Math.hypot(b[0] - a[0], b[2] - a[2])
      return <group key={`${e.source}-${e.condition}`}>
        {distance > 2.6 && distance < 10 && <RollerConveyor length={distance - 2.1} width={.65} position={[(a[0] + b[0]) / 2, .86, (a[2] + b[2]) / 2]} rotation={[0, -Math.atan2(b[2] - a[2], b[0] - a[0]), 0]} running={false} />}
        {paths && <Line points={[[a[0], 1.3, a[2]], [b[0], 1.3, b[2]]]} color={e.condition === 'NG' ? '#f04b35' : e.condition === 'OK' ? '#28af74' : '#0b9acc'} lineWidth={2} dashed dashSize={.16} gapSize={.09} />}
      </group>
    })}
    {visibleComponents.map(c => <EditableUnit key={`${snapshot.revision}-${c.id}`} component={c} resource={snapshot.metrics.resources[c.id]} selected={selected === c.id} editMode={editMode} onSelect={onSelect} onMove={onMove} part={snapshot.parts.find(p => p.component === c.id)} time={snapshot.time} labels={labels} />)}
    <Parts snapshot={visibleSnapshot} />
    <PatrolHumanoids visible={view !== 'cell'} />
    <OrbitControls makeDefault target={target} minDistance={3} maxDistance={100} maxPolarAngle={Math.PI / 2.05} />
  </Canvas>
}
