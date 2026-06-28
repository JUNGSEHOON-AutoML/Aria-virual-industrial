import { useRef, useState, Suspense } from 'react'
import { useFrame } from '@react-three/fiber'
import { Text, useTexture } from '@react-three/drei'

// 라인별 MVTec AD 클래스 (설정형 — 원하는 클래스로 교체 가능)
export const MVTEC_CLASSES = ['bottle', 'carpet', 'screw']

function ConveyorBelt() {
  const stripes = useRef()
  useFrame((_, dt) => {
    if (stripes.current) {
      const delta = Math.min(dt, 0.1)
      stripes.current.position.x = (stripes.current.position.x + delta * 1.2)
      if (stripes.current.position.x > 0.5) {
        stripes.current.position.x -= 0.5
      }
    }
  })
  return (
    <group position={[0, 0.5, 3]}>
      {/* 메인 벨트 구조물 */}
      <mesh receiveShadow>
        <boxGeometry args={[10, 0.1, 1.2]} />
        <meshStandardMaterial color="#1a1c23" metalness={0.7} roughness={0.5} />
      </mesh>
      {/* 벨트 프레임 (외곽 가이드) */}
      <mesh position={[0, 0.05, 0.61]}>
        <boxGeometry args={[10, 0.12, 0.02]} />
        <meshStandardMaterial color="#3a3f4b" metalness={0.8} roughness={0.3} />
      </mesh>
      <mesh position={[0, 0.05, -0.61]}>
        <boxGeometry args={[10, 0.12, 0.02]} />
        <meshStandardMaterial color="#3a3f4b" metalness={0.8} roughness={0.3} />
      </mesh>
      {/* 흐르는 벨트 줄무늬 */}
      <group ref={stripes}>
        {[...Array(22)].map((_, i) => (
          <mesh key={i} position={[-5.25 + i * 0.5, 0.055, 0]}>
            <boxGeometry args={[0.08, 0.01, 1.18]} />
            <meshStandardMaterial color="#1f4861" emissive="#1f4861" emissiveIntensity={0.2} />
          </mesh>
        ))}
      </group>
    </group>
  )
}

function FactoryParts({ ngProb, onResult, cap = 18 }) {
  const parts = useRef([])
  const acc = useRef(0)
  const id = useRef(0)
  const [, forceUpdate] = useState(0)

  useFrame((_, dt) => {
    const delta = Math.min(dt, 0.1)
    acc.current += delta
    
    // 1.1초마다 부품 스폰 (최대 cap개)
    if (acc.current > 1.1 && parts.current.length < cap) {
      acc.current = 0
      id.current++
      parts.current.push({
        id: id.current,
        x: -5,
        verdict: null,
        lane: 0,
        targetLane: 0,
        color: '#9aa3b2'
      })
    }

    for (const p of parts.current) {
      p.x += delta * 1.6
      
      // 게이트(x=0)에서 판정
      if (p.verdict === null && p.x >= 0) {
        const isNG = Math.random() < ngProb
        p.verdict = isNG ? 'NG' : 'OK'
        p.targetLane = isNG ? 0.35 : -0.35
        p.color = isNG ? '#f87171' : '#34d399'
        
        onResult?.(p.verdict)
      }

      // 게이트를 지난 후 targetLane으로 부드럽게 이동 (lerp)
      if (p.verdict !== null) {
        p.lane += (p.targetLane - p.lane) * delta * 4
      }
    }

    // 끝 도달 시 소멸
    parts.current = parts.current.filter(p => p.x < 5.2)
    
    forceUpdate(n => n + 1)
  })

  return (
    <group position={[0, 0.61, 3]}>
      {parts.current.map(p => (
        <mesh key={p.id} position={[p.x, 0.09, p.lane]} castShadow>
          <boxGeometry args={[0.26, 0.18, 0.26]} />
          <meshStandardMaterial
            color={p.color}
            emissive={p.color}
            emissiveIntensity={p.verdict ? 0.35 : 0.0}
            metalness={0.4}
            roughness={0.5}
          />
        </mesh>
      ))}
    </group>
  )
}

function ResultTile({ item, pos, onClick }) {
  const tex = useTexture(item.url)
  const col = item.label === 'NG' ? '#f87171' : '#34d399'
  return (
    <group position={pos} onPointerDown={(e)=>{ e.stopPropagation(); onClick() }}>
      {/* 입체 테두리 */}
      <mesh>
        <boxGeometry args={[0.92, 0.92, 0.08]} />
        <meshStandardMaterial color={col} emissive={col} emissiveIntensity={0.25} />
      </mesh>
      {/* 2D 이미지 평면 */}
      <mesh position={[0, 0, 0.05]}>
        <planeGeometry args={[0.8, 0.8]} />
        <meshBasicMaterial map={tex} toneMapped={false} />
      </mesh>
      {/* 라벨 텍스트 */}
      <Text
        position={[0, -0.6, 0.05]}
        fontSize={0.11}
        color={col}
        anchorX="center"
        anchorY="middle"
      >
        {item.label}
      </Text>
    </group>
  )
}

export function ResultGallery({ items = [], center = [0, 2.2, 0], onSelect }) {
  const gap = 1.05
  if (!items || items.length === 0) return null
  return (
    <group position={center}>
      {items.slice(0, 9).map((it, i) => {
        const r = Math.floor(i / 3), c = i % 3
        return (
          <Suspense key={i} fallback={null}>
            <ResultTile item={it} pos={[(c - 1) * gap, (1 - r) * gap, 0]} onClick={() => onSelect(i)} />
          </Suspense>
        )
      })}
    </group>
  )
}

export function ScanRig({ active }) {
  const ring = useRef()
  const beam = useRef()
  useFrame((s, dt) => {
    if (!active) return
    const delta = Math.min(dt, 0.1)
    if (ring.current) ring.current.rotation.z += delta * 2.2
    if (beam.current) beam.current.position.y = Math.sin(s.clock.elapsedTime * 2) * 0.5
  })
  if (!active) return null
  return (
    <group position={[0, 2.4, 0.5]}>
      {/* 스캔 링 */}
      <mesh ref={ring} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.9, 0.03, 8, 48]} />
        <meshStandardMaterial color="#1fb8cd" emissive="#1fb8cd" emissiveIntensity={1.2} />
      </mesh>
      {/* 스캔 레이저 빔 */}
      <mesh ref={beam} position={[0, 0, 0.06]}>
        <planeGeometry args={[1.8, 0.04]} />
        <meshBasicMaterial color="#1fb8cd" transparent opacity={0.6} />
      </mesh>
    </group>
  )
}

function InspectionGantry() {
  const laserRef = useRef()
  
  useFrame((state) => {
    if (laserRef.current) {
      // 위아래로 쓸어내리는 모션
      laserRef.current.position.y = 0.55 + Math.sin(state.clock.elapsedTime * 6) * 0.35
    }
  })

  return (
    <group position={[0, 0.5, 3]}>
      {/* 아치 프레임 - 좌측 다리 */}
      <mesh position={[0, 0.6, -0.65]} castShadow>
        <boxGeometry args={[0.15, 1.2, 0.08]} />
        <meshStandardMaterial color="#2d3240" metalness={0.7} roughness={0.3} />
      </mesh>
      {/* 아치 프레임 - 우측 다리 */}
      <mesh position={[0, 0.6, 0.65]} castShadow>
        <boxGeometry args={[0.15, 1.2, 0.08]} />
        <meshStandardMaterial color="#2d3240" metalness={0.7} roughness={0.3} />
      </mesh>
      {/* 아치 프레임 - 탑 헤더 */}
      <mesh position={[0, 1.2, 0]} castShadow>
        <boxGeometry args={[0.16, 0.12, 1.38]} />
        <meshStandardMaterial color="#1a1d26" metalness={0.8} roughness={0.2} />
      </mesh>
      {/* 검사 센서 렌즈 */}
      <mesh position={[0, 1.12, 0]}>
        <boxGeometry args={[0.1, 0.04, 0.3]} />
        <meshStandardMaterial color="#111" />
      </mesh>
      {/* 스캔 라인 레이저 광원 */}
      <mesh ref={laserRef} position={[0, 0.55, 0]}>
        <boxGeometry args={[0.02, 0.015, 1.15]} />
        <meshBasicMaterial color="#1fb8cd" transparent opacity={0.65} />
      </mesh>
    </group>
  )
}

function ResultBins({ okCount, ngCount }) {
  return (
    <group position={[4.8, 0.5, 3]}>
      {/* OK 수거함 (초록) */}
      <group position={[0, 0.05, -0.45]}>
        <mesh castShadow receiveShadow>
          <boxGeometry args={[0.7, 0.25, 0.5]} />
          <meshStandardMaterial color="#1a2e26" roughness={0.6} />
        </mesh>
        <mesh position={[0, 0.13, 0]}>
          <boxGeometry args={[0.72, 0.02, 0.52]} />
          <meshStandardMaterial color="#34d399" emissive="#34d399" emissiveIntensity={0.3} />
        </mesh>
      </group>

      {/* NG 수거함 (빨강) */}
      <group position={[0, 0.05, 0.45]}>
        <mesh castShadow receiveShadow>
          <boxGeometry args={[0.7, 0.25, 0.5]} />
          <meshStandardMaterial color="#2d1d1d" roughness={0.6} />
        </mesh>
        <mesh position={[0, 0.13, 0]}>
          <boxGeometry args={[0.72, 0.02, 0.52]} />
          <meshStandardMaterial color="#f87171" emissive="#f87171" emissiveIntensity={0.3} />
        </mesh>
      </group>

      {/* 카운터 텍스트 (Drei Text) */}
      <Text
        position={[0, 0.6, 0]}
        rotation={[0, -Math.PI / 2, 0]}
        fontSize={0.13}
        color="#ffffff"
        anchorX="center"
        anchorY="middle"
      >
        {`OK ${okCount} · NG ${ngCount}`}
      </Text>
    </group>
  )
}

function ProductionLine({ z = 3, ngProb = 0.12, cap = 10, classId = '', result = null }) {
  const [ok, setOk] = useState(0)
  const [ng, setNg] = useState(0)
  const onResult = (v) => v === 'OK' ? setOk(c => c + 1) : setNg(c => c + 1)
  
  // 실제 escape율이 존재하면 그 확률을 부품 생성 확률(effectiveNgProb)에 바인딩 (폴백 0.12)
  const effectiveNgProb = result?.escape_rate != null ? Math.min(0.5, Math.max(0.02, result.escape_rate)) : ngProb

  return (
    <group position={[0, 0, z - 3]}>
      <ConveyorBelt />
      <FactoryParts ngProb={effectiveNgProb} onResult={onResult} cap={cap} />
      <InspectionGantry />
      <ResultBins okCount={ok} ngCount={ng} />
      {classId && (
        <Text
          position={[-5.6, 1.05, 0]}
          fontSize={0.32}
          color="#1FB8CD"
          anchorX="left"
          anchorY="middle"
          rotation={[0, 0, 0]}
          characters="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 -–—·"
        >
          {`LINE · ${classId.toUpperCase()}`}
        </Text>
      )}
      {result?.fat_verdict && (
        <Text
          position={[-5.6, 0.7, 0]}
          fontSize={0.22}
          color={result.fat_verdict === 'PASS' ? '#34d399' : '#f87171'}
          anchorX="left"
          anchorY="middle"
          rotation={[0, 0, 0]}
          characters="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 -–—·%."
        >
          {`escape ${(result.escape_rate * 100 || 0).toFixed(0)}% · ${result.fat_verdict}`}
        </Text>
      )}
    </group>
  )
}

function Worker({ position, hue = '#f59e0b', phase = 0 }) {
  const ref = useRef()
  useFrame((s) => {
    if (ref.current) {
      ref.current.position.y = position[1] + Math.sin(s.clock.elapsedTime * 1.5 + phase) * 0.03
      ref.current.rotation.y = Math.sin(s.clock.elapsedTime * 0.4 + phase) * 0.25
    }
  })
  return (
    <group ref={ref} position={position}>
      {/* 몸통 */}
      <mesh position={[0, 0.55, 0]} castShadow>
        <cylinderGeometry args={[0.16, 0.2, 0.7, 8]} />
        <meshStandardMaterial color="#2d3340" />
      </mesh>
      {/* 머리 */}
      <mesh position={[0, 1.0, 0]} castShadow>
        <sphereGeometry args={[0.15, 12, 12]} />
        <meshStandardMaterial color="#e8c39e" />
      </mesh>
      {/* 안전모 */}
      <mesh position={[0, 1.08, 0]}>
        <sphereGeometry args={[0.17, 12, 12, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshStandardMaterial color={hue} metalness={0.3} />
      </mesh>
    </group>
  )
}

function Workers() {
  const spots = [
    [-3.2, 0, 2.0, 0],
    [1.5, 0, 2.0, 1.2],
    [-1.0, 0, 4.0, 2.0],
    [3.0, 0, 5.6, 0.7],
    [-3.5, 0, 6.2, 3.1]
  ]
  return (
    <group>
      {spots.map(([x, y, z, p], i) => (
        <Worker key={i} position={[x, y, z]} phase={p} hue={i % 2 ? '#1FB8CD' : '#f59e0b'} />
      ))}
    </group>
  )
}

function RobotArm({ position }) {
  const j1 = useRef()
  const j2 = useRef()
  useFrame((s) => {
    const t = s.clock.elapsedTime
    if (j1.current) j1.current.rotation.y = Math.sin(t * 0.5) * 0.6
    if (j2.current) j2.current.rotation.z = Math.sin(t * 0.7) * 0.5 + 0.3
  })
  return (
    <group position={position}>
      <mesh castShadow>
        <cylinderGeometry args={[0.25, 0.3, 0.3, 12]} />
        <meshStandardMaterial color="#2d3240" metalness={0.7} />
      </mesh>
      <group ref={j1} position={[0, 0.2, 0]}>
        <mesh position={[0, 0.4, 0]} castShadow>
          <boxGeometry args={[0.14, 0.8, 0.14]} />
          <meshStandardMaterial color="#3a4150" metalness={0.6} />
        </mesh>
        <group ref={j2} position={[0, 0.8, 0]}>
          <mesh position={[0.3, 0, 0]} castShadow>
            <boxGeometry args={[0.6, 0.12, 0.12]} />
            <meshStandardMaterial color="#3a4150" metalness={0.6} />
          </mesh>
          <mesh position={[0.6, 0, 0]}>
            <boxGeometry args={[0.1, 0.18, 0.18]} />
            <meshStandardMaterial color="#1FB8CD" emissive="#1FB8CD" emissiveIntensity={0.4} />
          </mesh>
        </group>
      </group>
    </group>
  )
}

function Equipment() {
  return (
    <group>
      <RobotArm position={[-4.5, 0.5, 4.2]} />
      <RobotArm position={[4.5, 0.5, 5.8]} />
      {/* 제어판 */}
      <group position={[-5.5, 0.5, 3]}>
        <mesh position={[0, 0.5, 0]} castShadow>
          <boxGeometry args={[0.5, 1, 0.8]} />
          <meshStandardMaterial color="#23262f" metalness={0.5} />
        </mesh>
        <mesh position={[0.26, 0.7, 0]}>
          <boxGeometry args={[0.02, 0.4, 0.6]} />
          <meshStandardMaterial color="#1FB8CD" emissive="#1FB8CD" emissiveIntensity={0.5} />
        </mesh>
      </group>
      {/* 바닥 위험표시(통로 라인) */}
      {[2.5, 4.0, 7.4].map((z, i) => (
        <mesh key={i} position={[0, 0.011, z]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[11, 0.12]} />
          <meshStandardMaterial color="#f5c518" />
        </mesh>
      ))}
      {/* 기둥 + 오버헤드 빔(공장 골조) */}
      {[[ -6, 8 ], [ 6, 8 ], [ -6, 1 ], [ 6, 1 ]].map(([x, z], i) => (
        <mesh key={i} position={[x, 2, z]} castShadow>
          <boxGeometry args={[0.3, 4, 0.3]} />
          <meshStandardMaterial color="#3a4150" metalness={0.4} />
        </mesh>
      ))}
      <mesh position={[0, 3.9, 4.5]}>
        <boxGeometry args={[13, 0.2, 0.2]} />
        <meshStandardMaterial color="#3a4150" />
      </mesh>
    </group>
  )
}

function StatusBoard({ cycle, validation, looping }) {
  const verdict = validation?.fat_verdict || 'N/A'
  const escapeRate = validation?.escape_rate != null 
    ? `${(validation.escape_rate * 100).toFixed(0)}%` 
    : 'N/A'
  
  const verdictColor = verdict === 'PASS' ? '#34d399' : verdict === 'FAIL' ? '#f87171' : '#9aa3b8'
  
  return (
    <group position={[0, 2.2, 1.6]}>
      {/* 전광판 배경보드 */}
      <mesh castShadow>
        <boxGeometry args={[2.5, 1.2, 0.05]} />
        <meshStandardMaterial color="#111318" metalness={0.8} roughness={0.2} />
      </mesh>
      {/* 테두리 에미시브 라인 */}
      <mesh position={[0, 0, 0.03]}>
        <boxGeometry args={[2.52, 1.22, 0.01]} />
        <meshStandardMaterial color="#1fb8cd" emissive="#1fb8cd" emissiveIntensity={0.15} wireframe />
      </mesh>
      
      <Text
        position={[-0.9, 0.35, 0.04]}
        fontSize={0.1}
        color="#9aa0aa"
        anchorX="left"
        anchorY="middle"
      >
        ARIA FACTORY MONITOR
      </Text>
      
      <Text
        position={[-0.9, 0.1, 0.04]}
        fontSize={0.09}
        color="#ffffff"
        anchorX="left"
        anchorY="middle"
      >
        {`CYCLE: ${cycle}`}
      </Text>

      <Text
        position={[-0.9, -0.1, 0.04]}
        fontSize={0.09}
        color="#ffffff"
        anchorX="left"
        anchorY="middle"
      >
        {`ESCAPE: ${escapeRate}`}
      </Text>

      <Text
        position={[-0.9, -0.3, 0.04]}
        fontSize={0.09}
        color="#ffffff"
        anchorX="left"
        anchorY="middle"
      >
        STATUS:
      </Text>
      
      <Text
        position={[-0.4, -0.3, 0.04]}
        fontSize={0.09}
        color={looping ? '#34d399' : '#e2e8f0'}
        anchorX="left"
        anchorY="middle"
      >
        {looping ? 'RUNNING' : 'IDLE'}
      </Text>

      <Text
        position={[0.3, -0.05, 0.04]}
        fontSize={0.11}
        color="#9aa0aa"
        anchorX="left"
        anchorY="middle"
      >
        FAT VERDICT
      </Text>
      
      <Text
        position={[0.5, -0.25, 0.04]}
        fontSize={0.2}
        color={verdictColor}
        anchorX="center"
        anchorY="middle"
        fontWeight="bold"
      >
        {verdict}
      </Text>
    </group>
  )
}

function LearningCore({ trainState }) {
  const coreRef = useRef()
  const isRunning = trainState?.status === 'running'

  useFrame((state, dt) => {
    if (coreRef.current) {
      const speed = isRunning ? 4.5 : 0.8
      coreRef.current.rotation.y += dt * speed
      coreRef.current.rotation.x += dt * speed * 0.5
      
      const scale = isRunning 
        ? 1.0 + Math.sin(state.clock.elapsedTime * 12) * 0.15
        : 1.0 + Math.sin(state.clock.elapsedTime * 2.5) * 0.05
      
      coreRef.current.scale.set(scale, scale, scale)
      
      if (coreRef.current.material) {
        const targetIntensity = isRunning 
          ? 1.8 + Math.sin(state.clock.elapsedTime * 12) * 0.6
          : 0.3 + Math.sin(state.clock.elapsedTime * 2.5) * 0.1
        coreRef.current.material.emissiveIntensity = targetIntensity
      }
    }
  })

  return (
    <group position={[-2.2, 1.8, -1.0]}>
      <mesh ref={coreRef} castShadow>
        <icosahedronGeometry args={[0.3, 1]} />
        <meshStandardMaterial
          color={isRunning ? '#a78bfa' : '#1fb8cd'}
          emissive={isRunning ? '#a78bfa' : '#1fb8cd'}
          emissiveIntensity={0.4}
          metalness={0.9}
          roughness={0.1}
        />
      </mesh>
      
      <mesh rotation={[Math.PI / 4, 0, 0]}>
        <torusGeometry args={[0.5, 0.02, 8, 32]} />
        <meshStandardMaterial color="#4b5563" metalness={0.8} />
      </mesh>
      <mesh rotation={[-Math.PI / 4, Math.PI / 2, 0]}>
        <torusGeometry args={[0.52, 0.02, 8, 32]} />
        <meshStandardMaterial color="#4b5563" metalness={0.8} />
      </mesh>
      
      {isRunning && (
        <pointLight
          color="#a78bfa"
          intensity={1.5}
          distance={4}
          decay={2}
        />
      )}
    </group>
  )
}

export default function FactoryLine({ classes = [], classResults = {}, looping, cycle, validation, trainState }) {
  const lines = (classes && classes.length) ? classes : MVTEC_CLASSES
  const baseZ = 3, gap = 2.0
  return (
    <group>
      {lines.map((cid, i) => (
        <ProductionLine key={cid} z={baseZ + i * gap} classId={cid}
          result={classResults[cid]} cap={10}
          ngProb={classResults[cid]?.escape_rate ?? 0.12} />
      ))}
      <Workers />
      <Equipment />
      <StatusBoard cycle={cycle} validation={validation} looping={looping} />
      <LearningCore trainState={trainState} />
    </group>
  )
}
