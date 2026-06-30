// InspectionSpecimen — 비전 부스 아래 검사 시편(클릭 대상). 명세 §1·§2·§3.
// 형상=현재 라인 클래스(partShapes). 클릭→홀로+스캔 sweep→Decal 역투영(난수 금지).
// Live=실 scan(image/heatmap/defect_xy), Standalone=합성 히트맵으로 동일 raycast(placeholder).
import { useRef, useEffect, useMemo, useState } from 'react'
import { useThree, useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { useSignalStore } from '../signalStore'
import { selectScan } from '../signalReducer'
import { injectScanShader, setScanY, buildDecal, texFromDataURI, heightTexFromDataURI } from './inspectVfx'
import { classShape, halfHeight } from './partShapes'
import LaserMarker from './LaserMarker'
import ReliefPatch from './ReliefPatch'

export default function InspectionSpecimen({ position = [0, 0.78, 0], onTrigger }) {
  const scan = useSignalStore(selectScan)
  const liveCategory = useSignalStore(s => s.liveCategory)
  const selection = useSignalStore(s => s.selection)
  const classes = useSignalStore(s => s.classes)

  const meshRef = useRef()
  const vfxRef = useRef()
  const phase = useRef('idle')
  const tScan = useRef(0)
  const [laser, setLaser] = useState(null)    // {point, normal} — LaserMarker 선언적 렌더
  const [relief, setRelief] = useState(null)  // {heightTex, size, y, score} — displacement 입체화

  // 현재 클래스: 선택 라인 > 가동 카테고리 > 첫 클래스 > bottle
  const className = useMemo(() => {
    if (selection?.group === 'line') return selection.id
    if (liveCategory) return liveCategory
    const c0 = Array.isArray(classes) && classes.length ? (classes[0]?.id || classes[0]) : null
    return c0 || 'bottle'
  }, [selection, liveCategory, classes])

  const shape = useMemo(() => classShape(className), [className])
  const half = halfHeight(shape)

  // 스캔 셰이더 머티리얼 (클래스 바뀌면 재생성)
  const mat = useMemo(() => {
    const m = new THREE.MeshStandardMaterial({
      color: new THREE.Color(shape.color), metalness: shape.metalness, roughness: shape.roughness })
    injectScanShader(m)
    return m
  }, [shape])

  // 부스 카메라(역투영용) — 시편을 위에서 내려봄. 정적.
  const boothCam = useMemo(() => {
    const c = new THREE.PerspectiveCamera(40, 1, 0.1, 6)
    c.position.set(position[0], position[1] + 1.05, position[2])
    c.lookAt(position[0], position[1], position[2])
    c.updateMatrixWorld(true); c.updateProjectionMatrix()
    return c
  }, [position[0], position[1], position[2]])

  // verdict 색 틴트
  const verdict = scan?.verdict
  useEffect(() => {
    const tint = verdict === 'NG' ? 0xf3b1b1 : verdict === 'OK' ? 0xb4e6c8 : null
    mat.color.set(tint != null ? new THREE.Color(tint) : new THREE.Color(shape.color))
  }, [verdict, mat, shape])

  function clearVfx() {
    const g = vfxRef.current
    if (g) while (g.children.length) { const c = g.children.pop(); c.geometry?.dispose?.(); c.material?.dispose?.(); g.remove(c) }
    setScanY(mat, -9999)
    setLaser(null)
    setRelief(null)
  }
  function reset() { phase.current = 'idle'; clearVfx() }

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') reset() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  function startScan(e) {
    e?.stopPropagation?.()
    clearVfx()
    phase.current = 'scanning'
    tScan.current = 0
    const holo = new THREE.Mesh(meshRef.current.geometry.clone(),
      new THREE.MeshBasicMaterial({ color: 0x1FB8CD, wireframe: true, transparent: true, opacity: 0.5 }))
    holo.position.copy(meshRef.current.position); holo.scale.setScalar(1.06)
    vfxRef.current.add(holo)
  }

  function finishScan() {
    phase.current = 'idle'
    setScanY(mat, -9999)

    // T1-A: 실 inspector_result만 사용(난수 금지). (u,v)→(x,y,z)는 coordinateTransform 단일 모듈.
    const hasLive = Array.isArray(scan?.defect_xy)
    if (hasLive) {
      const heatTex = texFromDataURI(scan.heatmap_b64)
      // F-07 blob 면적 → decal 크기 반영(있으면)
      const area = scan?.defect_blob?.area
      const sizeMul = area != null ? 1.2 + Math.min(2.2, Math.sqrt(area) * 4) : 2.0
      const built = buildDecal(meshRef.current, boothCam, scan.defect_xy, heatTex,
        Math.max(half, 0.12) * sizeMul)
      if (built) {
        vfxRef.current.add(built.decal)
        // GT 근사 링
        const ring = new THREE.Mesh(
          new THREE.RingGeometry(0.05, 0.075, 20),
          new THREE.MeshBasicMaterial({ color: 0x34d399, side: THREE.DoubleSide, transparent: true, opacity: 0.9 }))
        ring.position.copy(built.point).addScaledVector(built.normal, 0.006)
        ring.lookAt(built.point.clone().add(built.normal))
        vfxRef.current.add(ring)
        // 레이저 마커(선언적) — 결함 지시 투영
        setLaser({ point: built.point.clone(), normal: built.normal.clone() })
      }
      // 2D→3D 입체화: heatmap → displacement 요철 (부품 윗면)
      const heightTex = heightTexFromDataURI(scan.heatmap_b64)
      if (heightTex) {
        const sc = scan?.score != null && scan.score >= 0 ? scan.score : 0.5
        setRelief({ heightTex, size: Math.max(half, 0.12) * 2.4, y: position[1] + half + 0.005, score: sc })
      }
    }
    onTrigger?.(null)   // PiP는 실 store.scan만 표시(합성 override 없음)
  }

  useFrame((_, dt) => {
    if (phase.current !== 'scanning') return
    tScan.current += dt
    const k = Math.min(1, tScan.current / 1.1)
    const top = position[1] + half, bot = position[1] - half
    setScanY(mat, top - (top - bot) * k)
    if (k >= 1) finishScan()
  })

  return (
    <group>
      <mesh ref={meshRef} position={position} material={mat} castShadow onClick={startScan}
        onPointerOver={() => (document.body.style.cursor = 'pointer')}
        onPointerOut={() => (document.body.style.cursor = 'default')}>
        {shape.render === 'slab' && <boxGeometry args={shape.args} />}
        {shape.render === 'box' && <boxGeometry args={shape.args} />}
        {shape.render === 'cylinder' && <cylinderGeometry args={shape.args} />}
        {shape.render === 'capsule' && <capsuleGeometry args={shape.args} />}
      </mesh>
      <group ref={vfxRef} />
      {laser && <LaserMarker point={laser.point} normal={laser.normal} />}
      {relief && <ReliefPatch heightTex={relief.heightTex} size={relief.size} y={relief.y} score={relief.score} />}
    </group>
  )
}
