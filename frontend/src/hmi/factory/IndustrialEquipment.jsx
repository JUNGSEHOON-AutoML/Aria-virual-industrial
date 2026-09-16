// Parametric industrial equipment. Robot/spindle pose is a visualization of the
// actual DES processing phase, not a collision-checked robot motion program.
import { useMemo } from 'react'
import { Html, Line } from '@react-three/drei'

export function Solid({ at = [0, 0, 0], size, color = '#d7dcde', rotation, metal = .25, ...props }) {
  return <mesh position={at} rotation={rotation} castShadow receiveShadow {...props}>
    <boxGeometry args={size} /><meshStandardMaterial color={color} metalness={metal} roughness={.48} />
  </mesh>
}
function Cylinder({ at, radius, length, color = '#46535b', rotation }) {
  return <mesh position={at} rotation={rotation} castShadow><cylinderGeometry args={[radius, radius, length, 20]} /><meshStandardMaterial color={color} metalness={.65} roughness={.32} /></mesh>
}
function Glass({ at, size }) {
  return <mesh position={at}><boxGeometry args={size} /><meshStandardMaterial color="#86bfc7" transparent opacity={.15} depthWrite={false} roughness={.15} metalness={.15} /></mesh>
}
function Sign({ at, children, color = '#e5edf0', small = false }) {
  return <Html position={at} transform distanceFactor={5} zIndexRange={[12, 0]} style={{ pointerEvents: 'none' }}>
    <div className={`equipment-decal ${small ? 'small' : ''}`} style={{ color }}>{children}</div>
  </Html>
}
export function StackLight({ position, state }) {
  const colors = ['#e84740', '#f3b82e', '#37ba78']
  const active = state === 'DOWN' ? 0 : ['BLOCKED', 'MAINTENANCE', 'SETUP'].includes(state) ? 1 : state === 'PROCESSING' ? 2 : -1
  return <group position={position}><Cylinder at={[0, .15, 0]} radius={.028} length={.3} />{colors.map((color, i) => <mesh key={color} position={[0, .37 + (2 - i) * .12, 0]}><cylinderGeometry args={[.06, .06, .1, 14]} /><meshStandardMaterial color={i === active ? color : '#46534e'} emissive={color} emissiveIntensity={i === active ? .7 : 0} /></mesh>)}</group>
}
function Pendant({ at }) {
  return <group position={at}>
    <Solid at={[0, .7, 0]} size={[.055, 1.4, .055]} color="#495963" />
    <Solid at={[0, 1.4, .03]} size={[.48, .58, .14]} color="#e1e5e5" />
    <Solid at={[0, 1.47, .11]} size={[.33, .26, .012]} color="#142d39" />
    {[-.12, 0, .12].map(x => <Solid key={x} at={[x, 1.25, .11]} size={[.06, .045, .02]} color={x === .12 ? '#cf3c35' : '#61717a'} />)}
  </group>
}
export function Robot({ at = [0, 0, 0], phase = 0, active = false }) {
  // Joint angles only advance when simulation time/processing advances.
  const cycle = active ? Math.sin(phase * Math.PI * 2) : 0
  return <group position={at}>
    <Solid at={[0, .12, 0]} size={[.7, .24, .65]} color="#444e53" />
    <Cylinder at={[0, .37, 0]} radius={.24} length={.34} color="#ed8b19" />
    <group position={[0, .55, 0]} rotation={[0, -.7 + cycle * .3, 0]}>
      <Cylinder at={[0, .1, 0]} radius={.22} length={.32} rotation={[Math.PI / 2, 0, 0]} color="#de7b11" />
      <group rotation={[0, 0, -.38 + cycle * .15]}>
        <Solid at={[0, .5, 0]} size={[.26, 1, .28]} color="#f59b20" />
        <Cylinder at={[0, 1, 0]} radius={.19} length={.36} rotation={[Math.PI / 2, 0, 0]} color="#46545b" />
        <group position={[0, 1, 0]} rotation={[0, 0, -1.55 + cycle * .22]}>
          <Solid at={[0, .43, 0]} size={[.2, .86, .22]} color="#f29b21" />
          <Cylinder at={[0, .86, 0]} radius={.14} length={.26} rotation={[Math.PI / 2, 0, 0]} />
          <group position={[0, .91, 0]} rotation={[0, 0, -.4]}>
            <Cylinder at={[0, .16, 0]} radius={.085} length={.3} color="#adb9c0" />
            <Solid at={[0, .35, 0]} size={[.24, .14, .2]} color="#303e47" />
            {[-1, 1].map(x => <Solid key={x} at={[x * .095, .47, 0]} size={[.04, .22, .12]} color="#a5b0b5" />)}
          </group>
        </group>
      </group>
      <Line points={[[.12, .12, -.2], [.19, .9, -.2], [.8, 1.2, -.2]]} color="#242d34" lineWidth={3} />
    </group>
  </group>
}
function Fence({ at, length, rotation = 0, glass = false }) {
  const count = Math.max(1, Math.ceil(length / 1.2))
  return <group position={at} rotation={[0, rotation, 0]}>
    {[...Array(count + 1)].map((_, i) => <Solid key={i} at={[i * length / count - length / 2, 1, 0]} size={[.07, 2, .07]} color="#dba31c" />)}
    {[.15, 1.9].map(y => <Solid key={y} at={[0, y, 0]} size={[length, .055, .055]} color="#dba31c" />)}
    {glass ? <Glass at={[0, 1, 0]} size={[length, 1.65, .02]} /> : <>
      {[...Array(Math.ceil(length / .18))].map((_, i) => <Solid key={i} at={[-length / 2 + i * .18, 1, 0]} size={[.012, 1.65, .014]} color="#424c4d" />)}
      {[...Array(9)].map((_, i) => <Solid key={i} at={[0, .3 + i * .18, 0]} size={[length, .012, .014]} color="#424c4d" />)}
    </>}
  </group>
}
function CNC({ state, phase }) {
  return <group>
    <Solid at={[0, .2, 0]} size={[2.5, .4, 1.9]} color="#257e82" />
    <Solid at={[0, 1.4, -.7]} size={[2.45, 2.4, .5]} color="#d5dcdd" />
    <Solid at={[-1.02, 1.3, 0]} size={[.42, 2.2, 1.65]} />
    <Solid at={[1.02, 1.3, 0]} size={[.42, 2.2, 1.65]} />
    <Solid at={[0, 2.45, 0]} size={[2.45, .25, 1.85]} color="#eef0ed" />
    <Solid at={[0, .63, .05]} size={[1.55, .42, 1.35]} color="#596773" />
    {[-.5, -.25, 0, .25, .5].map(x => <Solid key={x} at={[x, .855, .05]} size={[.055, .015, 1.05]} color="#c1cbce" />)}
    <Solid at={[0, 1.87 + (state === 'PROCESSING' ? Math.sin(phase * Math.PI) * .13 : 0), -.1]} size={[.35, .7, .4]} color="#76838a" />
    <Cylinder at={[0, 1.38, -.1]} radius={.07} length={.32} color="#c9d2d4" />
    <Glass at={[0, 1.58, .88]} size={[1.62, 1.6, .045]} />
    {[-.82, 0, .82].map(x => <Solid key={x} at={[x, 1.58, .91]} size={[.04, 1.65, .03]} color="#7c8d92" />)}
    <Solid at={[.12, 1.45, .97]} size={[.03, .36, .055]} color="#343f46" />
    <Solid at={[.97, 1.9, .88]} size={[.38, .56, .16]} color="#3f5059" />
    <Solid at={[.97, 1.99, .97]} size={[.27, .22, .015]} color="#62adb4" />
    <StackLight position={[.98, 2.58, -.4]} state={state} />
    <Sign at={[0, 2.47, .99]}>ARIA · CNC 500</Sign>
    <Sign at={[-1, 1.4, .87]} small color="#e5b521">⚠</Sign>
  </group>
}
function Pallet({ at = [0, 0, 0], totes = false }) {
  return <group position={at}>
    {[-.5, 0, .5].map(z => <Solid key={z} at={[0, .09, z]} size={[1.2, .18, .13]} color="#8a7150" />)}
    {[-.48, -.24, 0, .24, .48].map(x => <Solid key={x} at={[x, .23, 0]} size={[.2, .1, 1.2]} color="#b49a70" />)}
    {totes && [0, 1].map(y => <group key={y} position={[0, .3 + y * .32, 0]}>
      <Solid at={[0, .05, 0]} size={[1.05, .1, 1.05]} color="#728d9b" />
      {[-.51, .51].map(z => <Solid key={z} at={[0, .16, z]} size={[1.05, .32, .04]} color="#829da9" />)}
      {[-.51, .51].map(x => <Solid key={x} at={[x, .16, 0]} size={[.04, .32, 1.05]} color="#829da9" />)}
    </group>)}
  </group>
}
export function Equipment({ component: c, resource, part, time }) {
  const active = resource?.state === 'PROCESSING'
  const phase = part ? Math.min(1, Math.max(0, (time - part.entered) / Math.max(.01, part.due - part.entered))) : 0
  if (c.kind === 'Machine') return <>
    <CNC state={resource?.state} phase={phase} />
    <group position={[.45, 0, 2.05]} rotation={[0, Math.PI, 0]}><Robot active={active} phase={phase} /></group>
    <Fence at={[0, 0, 3.05]} length={3} /><Fence at={[-1.55, 0, 2]} length={2.1} rotation={Math.PI / 2} />
    <Pendant at={[1.55, 0, 2.7]} />
    {c.capacity > 1 && <Sign at={[0, 3.45, 0]}>{c.capacity} PARALLEL PROCESS SLOTS</Sign>}
  </>
  if (c.kind === 'Inspection') return <>
    <Solid at={[0, .46, 0]} size={[2.4, .92, 1.9]} color="#c8d2d4" />
    <Solid at={[0, .96, 0]} size={[2.5, .08, 2]} color="#596970" />
    <group position={[-.6, .99, -.35]} scale={.7}><Robot active={active} phase={phase} /></group>
    <Solid at={[.55, 1, .35]} size={[.72, .05, .65]} color="#c7d1cf" />
    {[-1.2, 1.2].map(x => <Solid key={x} at={[x, 2, -.8]} size={[.12, 2.2, .13]} color="#adbcc0" />)}
    <Solid at={[0, 3.1, -.8]} size={[2.52, .18, .28]} color="#dce3e3" />
    <Solid at={[.45, 2.8, -.8]} size={[.35, .42, .35]} color="#4c5b64" />
    <Cylinder at={[.45, 2.54, -.8]} radius={.1} length={.16} color="#171f26" />
    <Glass at={[0, 1.95, 1.02]} size={[2.5, 1.9, .025]} />
    {[-1.25, 1.25].map(x => <Glass key={x} at={[x, 1.95, .1]} size={[.025, 1.9, 1.8]} />)}
    <StackLight position={[-1, 3.2, -.75]} state={resource?.state} />
    <Pendant at={[1.5, 0, 1.3]} /><Sign at={[0, .65, 1.02]}>ARIA · VISION CELL</Sign>
  </>
  if (c.kind === 'Source') return <><Pallet totes /><Pallet at={[-.7, 0, 1.7]} totes /><Solid at={[.83, .7, 0]} size={[.1, 1.4, 1.4]} color="#267f88" /><Sign at={[0, 1.5, 0]}>MATERIAL INFEED</Sign></>
  if (c.kind === 'Buffer') return <>
    {[-.8, .8].flatMap(x => [-.6, .6].map(z => <Solid key={`${x}-${z}`} at={[x, .7, z]} size={[.1, 1.4, .1]} color="#225a88" />))}
    {[.25, .83].map(y => <Solid key={y} at={[0, y, 0]} size={[1.8, .1, 1.4]} color="#d79627" />)}
    <Sign at={[0, 1.6, 0]}>FIFO / BUFFER {c.capacity}</Sign>
  </>
  if (c.kind === 'Diverter') return <>
    <Solid at={[0, .48, 0]} size={[1.25, .96, 1.25]} color="#bac6ca" />
    <Cylinder at={[0, 1, 0]} radius={.65} length={.12} color="#61737c" />
    <Solid at={[0, 1.13, 0]} size={[1.25, .16, .16]} color="#e8b034" rotation={[0, part?.verdict === 'NG' ? -.6 : .6, 0]} />
  </>
  if (c.kind === 'Sink') return <><Pallet /><group position={[0, .3, 0]}>
    <Solid at={[0, .04, 0]} size={[1.4, .08, 1.3]} color="#546873" />
    {[-.68, .68].map(x => <Solid key={x} at={[x, .4, 0]} size={[.06, .8, 1.3]} color="#81949e" />)}
    {[-.62, .62].map(z => <Solid key={z} at={[0, .4, z]} size={[1.4, .8, .06]} color="#81949e" />)}
    <Sign at={[0, .47, .665]}>{c.id.includes('GOOD') ? 'FINISHED' : c.id.includes('HOLD') ? 'QUARANTINE' : 'REJECT'} · {resource?.completed || 0}</Sign>
  </group></>
  return null
}

export function FactoryBuilding({ components }) {
  const bounds = useMemo(() => {
    const xs = components.map(c => c.position[0]), zs = components.map(c => c.position[2])
    return { left: Math.min(...xs) - 4, right: Math.max(...xs) + 4, back: Math.min(...zs) - 4.5, front: Math.max(...zs) + 5 }
  }, [components])
  const { left, right, back, front } = bounds
  const width = right - left, depth = front - back, center = [(left + right) / 2, -.13, (back + front) / 2]
  return <group>
    <Solid at={center} size={[width, .25, depth]} color="#9ca5a5" metal={.05} />
    {Array.from({ length: Math.ceil(width / 2) }, (_, i) => <Line key={`x${i}`} points={[[left + i * 2, .005, back], [left + i * 2, .005, front]]} color="#7f898b" lineWidth={.6} />)}
    {Array.from({ length: Math.ceil(depth / 2) }, (_, i) => <Line key={`z${i}`} points={[[left, .005, back + i * 2], [right, .005, back + i * 2]]} color="#7f898b" lineWidth={.6} />)}
    <Solid at={[(left + right) / 2, 2.1, back]} size={[width, 4.2, .22]} color="#c6ccca" metal={.08} />
    <Solid at={[left, 2.1, (back + front) / 2]} size={[.22, 4.2, depth]} color="#bcc5c5" metal={.08} />
    {Array.from({ length: Math.floor(width / 3) }, (_, i) => <group key={i} position={[left + 1.5 + i * 3, 0, back + .14]}>
      <Solid at={[0, 3, 0]} size={[1.9, 1.25, .07]} color="#526f7c" />
      <Solid at={[0, 3, .05]} size={[1.65, 1, .015]} color="#85b8cc" />
      <Solid at={[1.47, 2.1, .03]} size={[.12, 4.2, .24]} color="#808e94" />
    </group>)}
    <Solid at={[(left + right) / 2, 4.25, back + .1]} size={[width, .16, .36]} color="#50636c" />
    <Sign at={[(left + right) / 2, 1.6, back + .18]}>ARIA INDUSTRIAL · FLEXIBLE MANUFACTURING</Sign>
    <Solid at={[(left + right) / 2, .018, front - 1.8]} size={[width - 1, .016, 1.2]} color="#488898" metal={0} />
    {[front - 2.5, front - 1.1].map(z => <Solid key={z} at={[(left + right) / 2, .03, z]} size={[width - 1, .015, .065]} color="#efcb4a" metal={0} />)}
    {components.filter(c => ['Machine', 'Inspection'].includes(c.kind)).map(c => <group key={c.id} position={c.position} rotation={[0, c.rotation, 0]}>
      <Line points={[[-1.8, .03, -1.25], [1.8, .03, -1.25], [1.8, .03, 3.4], [-1.8, .03, 3.4], [-1.8, .03, -1.25]]} color="#eac245" lineWidth={2} />
    </group>)}
    <Solid at={[left + .5, .75, back + 1]} size={[.5, 1.5, .6]} color="#b7473a" />
  </group>
}
