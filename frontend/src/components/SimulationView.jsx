import { useRef, useState, useEffect } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, Grid, Text, Line } from '@react-three/drei'
import { sampleSceneParams, sampleCameraParams } from '../sim/randomization'
import { uploadSimDataset, getWebSocketUrl, intakeDataset, simTrain, simValidate, classTrain, classValidate, mvtecScan, classSamples } from '../api/apiClient'
import FactoryLine, { MVTEC_CLASSES, ResultGallery, ScanRig } from '../sim/factory'

/* ──────────────────────────────────────────────
   Sub-components
────────────────────────────────────────────── */

// 중앙 검사대 구성(Workbench, InspectionPart, CameraRig, LaserBeam) 제거됨

/** 조명 리그 */
function InspectionLights() {
  return (
    <group>
      {/* 탑 링라이트 (Ring light placeholder) */}
      <mesh position={[0, 2.1, 0]}>
        <torusGeometry args={[0.3, 0.025, 8, 32]} />
        <meshStandardMaterial color="#ffffff" emissive="#e0f0ff" emissiveIntensity={0.6} />
      </mesh>
      {/* 링라이트 포인트 */}
      <pointLight position={[0, 2.05, 0]} intensity={0.8} color="#e8f4ff" distance={3} />
      {/* 측면 스팟라이트 x2 */}
      <spotLight position={[-2, 3, 0]} angle={0.4} penumbra={0.5} intensity={0.6} color="#fff8f0" castShadow />
      <spotLight position={[2, 3, 0]} angle={0.4} penumbra={0.5} intensity={0.6} color="#fff8f0" castShadow />
    </group>
  )
}

// SceneLabels 및 InspectionCell 제거됨

/** GLBridge: R3F Canvas 내부의 gl, camera 컨텍스트를 외부 ref로 노출하는 브릿지 */
function GLBridge({ glRef }) {
  const { gl, camera } = useThree()
  useEffect(() => {
    glRef.current = { gl, camera }
  }, [gl, camera, glRef])
  return null
}

/* ──────────────────────────────────────────────
   HUD Overlay
────────────────────────────────────────────── */
function SimHUD() {
  return (
    <div style={{
      position: 'absolute', inset: 0, pointerEvents: 'none',
      fontFamily: "'Courier New', monospace",
    }}>
      {/* 좌상단 레이블 */}
      <div style={{
        position: 'absolute', top: 14, left: 16,
        fontSize: 11, letterSpacing: 2.5,
        color: 'rgba(154, 160, 170, 0.7)',
        textTransform: 'uppercase',
      }}>
        SIM-2 &nbsp;·&nbsp; 도메인 랜덤화
      </div>

      {/* 우상단 상태 배지 */}
      <div style={{
        position: 'absolute', top: 12, right: 16,
        display: 'flex', alignItems: 'center', gap: 6,
        fontSize: 10, letterSpacing: 1.5,
        color: '#1FB8CD',
      }}>
        <span style={{
          width: 7, height: 7, borderRadius: '50%',
          background: '#1FB8CD',
          boxShadow: '0 0 6px #1FB8CD',
          display: 'inline-block',
        }} />
        LIVE
      </div>

      {/* 좌하단 조작 힌트 */}
      <div style={{
        position: 'absolute', bottom: 140, left: 16,
        fontSize: 10, color: 'rgba(154, 160, 170, 0.5)',
        lineHeight: 1.7, letterSpacing: 1,
      }}>
        <div>🖱 좌클릭 드래그 → 회전</div>
        <div>🖱 우클릭 드래그 → 패닝</div>
        <div>🖱 휠 → 줌</div>
      </div>

      {/* 우하단 씬 정보 */}
      <div style={{
        position: 'absolute', bottom: 16, right: 16,
        fontSize: 10, color: 'rgba(154, 160, 170, 0.45)',
        textAlign: 'right', lineHeight: 1.7,
      }}>
        <div>R3F / three.js</div>
        <div>SIM-2: 도메인 랜덤화 적용됨</div>
      </div>

      {/* 코너 브래킷 오버레이 */}
      {['topLeft', 'topRight', 'bottomLeft', 'bottomRight'].map((corner) => {
        const style = {
          position: 'absolute', width: 18, height: 18,
          borderColor: 'rgba(31,184,205,0.3)', borderStyle: 'solid',
        }
        if (corner === 'topLeft')     Object.assign(style, { top: 8, left: 8, borderWidth: '1px 0 0 1px' })
        if (corner === 'topRight')    Object.assign(style, { top: 8, right: 8, borderWidth: '1px 1px 0 0' })
        if (corner === 'bottomLeft')  Object.assign(style, { bottom: 8, left: 8, borderWidth: '0 0 1px 1px' })
        if (corner === 'bottomRight') Object.assign(style, { bottom: 8, right: 8, borderWidth: '0 1px 1px 0' })
        return <div key={corner} style={style} />
      })}
    </div>
  )
}

/** CameraOrbit: 선택 시 360° 회전 검사 궤도로 서서히 이동 */
function CameraOrbit({ active, target, controlsRef }) {
  const { camera } = useThree()
  const a = useRef(0)
  useFrame((_, dt) => {
    if (!active || !controlsRef.current) return
    const delta = Math.min(dt, 0.1)
    a.current += delta * 0.7                               // 360° 천천히 궤도
    const R = 3.2
    camera.position.set(target[0] + Math.cos(a.current) * R, target[1] + 1.2, target[2] + Math.sin(a.current) * R)
    controlsRef.current.target.set(...target)
    controlsRef.current.update()
  })
  return null
}

/* ──────────────────────────────────────────────
   Main Export
────────────────────────────────────────────── */
export default function SimulationView() {
  const [params, setParams] = useState(sampleSceneParams)
  const [auto, setAuto] = useState(false)

  // 캡처 상태 및 레프
  const glRef = useRef(null)
  const controlsRef = useRef(null)
  const factoryGroupRef = useRef(null)
  const [capturing, setCapturing] = useState(false)
  const [progress, setProgress] = useState(0)
  const [defectRatio, setDefectRatio] = useState(0.3)

  // MVTec AD 데이터셋 루트 경로 및 클래스별 결과 상태 추가
  const [mvtecRoot, setMvtecRoot] = useState('/userHome/userhome4/sehoon/ARIA-Anomaly-Reasoning-Intelligence-Agent--main/data')
  const [availableClasses, setAvailableClasses] = useState([])
  const [selectedClasses, setSelectedClasses]   = useState([])
  const [activeClass, setActiveClass]           = useState(null)
  const [galleryItems, setGalleryItems]         = useState([])
  const [galleryClass, setGalleryClass]         = useState(null)
  const [selectedIdx, setSelectedIdx]           = useState(null)
  const [classResults, setClassResults] = useState({})

  // Phase 2a 상태 추가
  const [simAgents, setSimAgents]   = useState({})    // { AGENT: {state, detail} }
  const [intake, setIntake]         = useState(null)  // {status|domain|n_images|error}

  // Phase 2(A) 상태 추가
  const [lastRunId, setLastRunId]   = useState(null)
  const [trainState, setTrainState] = useState(null)   // TrainingViewer 호환 필드
  const [validation, setValidation] = useState(null)   // Phase 2(A+) 검증 결과 상태

  // Phase 2(B) Ref 기반 자율 체이닝 추가
  const runIdRef     = useRef(null)   // WS 콜백이 읽을 최신 run_id
  const chainRef     = useRef(false)  // 자율 체인 진행 중인가
  const validatedRef = useRef(false)  // 검증 1회 가드

  // Phase 2(C) 무한 반복 루프 추가
  const loopRef       = useRef(false)
  const trainDoneRef  = useRef(null)   // { resolve, reject, stallMs } | null
  const trainTimerRef = useRef(null)
  const [cycle, setCycle]       = useState(0)
  const [looping, setLooping]   = useState(false)
  const [loopError, setLoopError] = useState(null)

  function armStall(ms) {                         // 무응답 ms 지나면 정지
    clearTimeout(trainTimerRef.current)
    trainTimerRef.current = setTimeout(() => {
      const d = trainDoneRef.current
      if (d) {
        trainDoneRef.current = null
        d.reject(new Error('학습 정지(무응답)'))
      }
    }, ms)
  }

  function waitTrainingDone(stallMs = 120000) {     // 첫 사이클 모델 로딩 대비 넉넉히
    return new Promise((resolve, reject) => {
      trainDoneRef.current = { resolve, reject, stallMs }
      armStall(stallMs)
    })
  }
  const sleep = (ms) => new Promise(r => setTimeout(r, ms))

  useEffect(() => {
    let ws
    try {
      ws = new WebSocket(getWebSocketUrl())
      ws.onmessage = (e) => {
        try {
          const d = JSON.parse(e.data)
          if (d.type === 'agent_status') {
            setSimAgents(a => ({ ...a, [d.agent]: { state: d.state, detail: d.detail } }))
          } else if (d.type === 'class_result') {
            setClassResults(prev => ({ ...prev, [d.classId]: d }))
          } else if (d.type === 'training') {
            // TrainingViewer.jsx 호환 표준 필드 구조 매핑
            setTrainState({
              step: d.step,
              total_steps: d.total_steps,
              status: d.status,
              metrics: { loss: d.metrics?.loss },
              preview_image: d.preview_image
            })
            const w = trainDoneRef.current
            if (w && d.status === 'running') armStall(w.stallMs)          // ★ 하트비트: 진행 = 타임아웃 리셋
            if (d.status === 'done') {
              clearTimeout(trainTimerRef.current)
              if (w) {
                trainDoneRef.current = null
                w.resolve()
              } else if (chainRef.current && !validatedRef.current && runIdRef.current && !loopRef.current) {
                validatedRef.current = true                      // 수동 드롭 체인(루프 아닐 때만)
                simValidate(runIdRef.current)
                  .then(setValidation)
                  .catch(e => setValidation({ ok: false, error: String(e) }))
              }
            }
            if (d.status === 'error') {
              clearTimeout(trainTimerRef.current)
              if (w) {
                trainDoneRef.current = null
                w.reject(new Error('학습 실패'))
              }
              chainRef.current = false   // 학습 실패 → 체인 중단
            }
          }
        } catch {}
      }
    } catch {}
    return () => { try { ws && ws.close() } catch {} }   // 탭 이탈 시 정리(누수 방지)
  }, [])

  async function onIntake(e) {
    const f = e.target.files?.[0]; if (!f) return
    // 체인 상태 리셋
    setSimAgents({}); setTrainState(null); setValidation(null)
    validatedRef.current = false; chainRef.current = true
    setIntake({ status: 'running' })
    try {
      const r = await intakeDataset(f)                      // ① 인테이크
      setIntake(r)
      runIdRef.current = r.run_id
      setLastRunId(r.run_id)
      const t = await simTrain(r.run_id)                    // ② 자동 학습
      if (!t?.ok) {
        chainRef.current = false
        setIntake({ error: '학습 시작 실패' })
        return
      }
      // ③ 검증은 'training' done 이벤트에서 자동 (onmessage 분기)
    } catch (err) {
      chainRef.current = false                              // 실패 가드
      setIntake({ error: String(err) })
    }
  }

  async function runCycle() {
    const res = await captureDataset(24)                 // ① 합성데이터 생성
    if (!res?.run_id) throw new Error('데이터 생성 실패')
    runIdRef.current = res.run_id
    const done = waitTrainingDone()                       // ★ resolver 먼저 등록(레이스 방지)
    const t = await simTrain(res.run_id)                  // ② 학습 시작
    if (!t?.ok) throw new Error('학습 시작 실패')
    await done                                            //    학습 done 대기
    const v = await simValidate(res.run_id)               // ③ 검증
    setValidation(v)
  }

  async function showResults(cid) {
    const s = await classSamples(cid, `${mvtecRoot}/${cid}`)
    if (s?.ok) {
      setGalleryItems(s.items)
      setGalleryClass(cid)
      setSelectedIdx(null)
    }
  }

  async function factoryLoop() {
    setLoopError(null); setLooping(true); loopRef.current = true
    let cyc = 0
    const classes = (selectedClasses && selectedClasses.length) ? selectedClasses : MVTEC_CLASSES
    while (loopRef.current) {
      for (const cid of classes) {
        if (!loopRef.current) break
        if (typeof setActiveClass === 'function') {
          setActiveClass(cid)
        }
        const path = `${mvtecRoot}/${cid}`
        try {
          const t = await classTrain(cid, path)
          if (t?.ok) {
            await waitTrainingDone().catch(() => {})
            await classValidate(cid, path)
            await showResults(cid)
          }
        } catch (e) {
          console.warn('[loop] class 실패:', cid, e)
        }
        if (!loopRef.current) break
        await sleep(1500)
      }
      setCycle(++cyc)
      if (!loopRef.current) break
      await sleep(3000)
    }
    setLooping(false)
  }
  function stopLoop() { loopRef.current = false; setLooping(false); if (typeof setActiveClass === 'function') setActiveClass(null) }

  async function scanRoot() {
    const r = await mvtecScan(mvtecRoot)
    if (r?.ok) {
      setAvailableClasses(r.classes)
      setSelectedClasses(r.classes.slice(0, 3))
    } else {
      alert(r?.error || '스캔 실패')
    }
  }

  function toggleClass(cid) {
    setSelectedClasses(prev => prev.includes(cid) ? prev.filter(c => c !== cid) : [...prev, cid])
  }

  async function runAllClasses() {
    setClassResults({})
    setSimAgents({})
    const targets = selectedClasses.length > 0 ? selectedClasses : MVTEC_CLASSES
    for (const cid of targets) {
      const path = `${mvtecRoot}/${cid}`
      const t = await classTrain(cid, path)
      if (!t?.ok) continue
      await waitTrainingDone().catch(() => {})
      await classValidate(cid, path)
    }
  }

  const phase =
    validation ? '검증 완료'
    : trainState ? (trainState.status === 'done' ? '검증 중…' : '학습 중…')
    : intake?.domain ? '학습 시작…'
    : intake?.status === 'running' ? '인테이크 중…'
    : '대기';

  useEffect(() => {
    if (!auto) return
    const id = setInterval(() => setParams(sampleSceneParams()), 2000)
    return () => clearInterval(id)
  }, [auto])

  const raf = () => new Promise(r => requestAnimationFrame(r))

  async function captureDataset(n = 24) {
    if (!glRef.current) {
      if (!loopRef.current) alert('WebGL 컨텍스트가 초기화되지 않았습니다.')
      return
    }
    setCapturing(true)
    setProgress(0)
    
    if (factoryGroupRef.current) {
      factoryGroupRef.current.visible = false
    }
    
    // 캡처 중 OrbitControls 락킹
    if (controlsRef.current) {
      controlsRef.current.enabled = false
    }

    const { gl, camera } = glRef.current
    const shots = []

    try {
      for (let i = 0; i < n; i++) {
        // 1. 파라미터 랜덤화
        const newParams = sampleSceneParams()
        setParams(newParams)

        // 2. 카메라 각도 랜덤화
        const c = sampleCameraParams()
        const posX = c.dist * Math.cos(c.el) * Math.cos(c.az)
        const posY = c.dist * Math.sin(c.el)
        const posZ = c.dist * Math.cos(c.el) * Math.sin(c.az)

        camera.position.set(posX, posY, posZ)
        camera.lookAt(0, 0.8, 0)

        // 3. 2프레임 렌더링 동기화 대기
        await raf()
        await raf()

        // 4. 스냅샷 추출
        shots.push(gl.domElement.toDataURL('image/png'))
        setProgress(i + 1)
      }

      // 5. 백엔드 업로드
      const res = await uploadSimDataset(shots, defectRatio)
      if (!loopRef.current) {
        alert(`성공: 합성 데이터셋 생성 완료!\n- 정상(good): ${res.classes.good}장\n- 결함(defect): ${res.classes.defect}장\n(경로: ${res.work_dir})`)
      }
      return res
    } catch (err) {
      console.error('[Capture Error]', err)
      if (!loopRef.current) {
        alert(`데이터셋 생성 중 에러 발생: ${err.message}`)
      }
      throw err
    } finally {
      if (controlsRef.current) {
        controlsRef.current.enabled = true
      }
      if (factoryGroupRef.current) {
        factoryGroupRef.current.visible = true
      }
      setCapturing(false)
    }
  }

  const ngProb = validation?.escape_rate != null
    ? Math.min(0.5, (validation.escape_rate + (validation.fp_rate||0)) || 0.12)
    : 0.12

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative', background: '#0b0d12' }}>
      {/* 컨트롤 패널 */}
      <div style={{
        position: 'absolute', top: 45, right: 16, zIndex: 10,
        display: 'flex', flexDirection: 'column', gap: 6,
        fontFamily: "'Courier New', monospace", fontSize: 11,
        background: 'rgba(11, 13, 18, 0.85)', padding: '10px 14px', borderRadius: 8,
        border: '1px solid rgba(255, 255, 255, 0.08)', backdropFilter: 'blur(6px)',
        boxShadow: '0 4px 20px rgba(0, 0, 0, 0.5)',
      }}>
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            disabled={capturing}
            onClick={() => setParams(sampleSceneParams())}
            style={{
              padding: '6px 12px', borderRadius: 6, cursor: capturing ? 'not-allowed' : 'pointer',
              border: '1px solid rgba(31,184,205,0.45)', background: 'rgba(31,184,205,0.12)',
              color: '#1FB8CD', fontWeight: 'bold', outline: 'none', transition: 'all 0.15s',
              opacity: capturing ? 0.5 : 1
            }}
          >
            랜덤화
          </button>
          <button
            disabled={capturing}
            onClick={() => setAuto(a => !a)}
            style={{
              padding: '6px 12px', borderRadius: 6, cursor: capturing ? 'not-allowed' : 'pointer',
              border: '1px solid rgba(255,255,255,0.1)', background: auto ? 'rgba(61,202,165,0.15)' : 'transparent',
              color: auto ? '#3DCAA5' : '#6b7280', fontWeight: 'bold', outline: 'none', transition: 'all 0.15s',
              opacity: capturing ? 0.5 : 1
            }}
          >
            {auto ? '자동 ■' : '자동 ▶'}
          </button>
        </div>

        {/* 결함 합성 비율 조절 슬라이더 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 2 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: '#9aa0aa', fontSize: 10 }}>
            <span>결함 비율 (defect ratio)</span>
            <span>{(defectRatio * 100).toFixed(0)}%</span>
          </div>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={defectRatio}
            disabled={capturing}
            onChange={(e) => setDefectRatio(parseFloat(e.target.value))}
            style={{
              width: '100%',
              accentColor: '#1FB8CD',
              cursor: capturing ? 'not-allowed' : 'pointer',
              background: 'rgba(255,255,255,0.1)',
              height: 4,
              borderRadius: 2,
              outline: 'none',
              opacity: capturing ? 0.5 : 1
            }}
          />
        </div>

        <button
          disabled={capturing}
          onClick={() => captureDataset(24)}
          style={{
            marginTop: 2, padding: '7px 12px', borderRadius: 6, cursor: capturing ? 'not-allowed' : 'pointer',
            border: '1px solid rgba(255,255,255,0.15)',
            background: capturing ? 'rgba(255,255,255,0.05)' : 'rgba(255,255,255,0.07)',
            color: capturing ? '#9aa0aa' : '#e8eaf0', fontWeight: 'bold', outline: 'none',
            fontSize: 10, letterSpacing: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
            transition: 'all 0.15s'
          }}
        >
          <span>📸</span>
          <span>{capturing ? `캡처 중 (${progress}/24)` : '데이터셋 생성 (24장)'}</span>
        </button>

        <div style={{ color: '#9aa0aa', fontSize: 10, marginTop: 6, display: 'flex', flexDirection: 'column', gap: 3 }}>
          <div>ambient: {params.light.ambient.toFixed(2)}</div>
          <div>key light: {params.light.key.toFixed(2)}</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            color: <span style={{
              width: 10, height: 10, borderRadius: '50%',
              background: params.light.color, display: 'inline-block',
              border: '1px solid rgba(255,255,255,0.2)'
            }} />
            <span style={{ color: params.light.color }}>{params.light.color}</span>
          </div>
          <div>yaw: {(params.part.rotY * 180 / Math.PI).toFixed(0)}°</div>
          <div>tilt: X {(params.part.rotX * 180 / Math.PI).toFixed(1)}°, Z {(params.part.rotZ * 180 / Math.PI).toFixed(1)}°</div>
        </div>
      </div>

      <Canvas
        shadows
        camera={{ position: [4, 3, 4], fov: 50 }}
        gl={{ antialias: true, preserveDrawingBuffer: true }}
      >
        <GLBridge glRef={glRef} />
        <color attach="background" args={['#0b0d12']} />

        {/* 환경광 */}
        <ambientLight intensity={params.light.ambient} />
        {/* 주 방향광 */}
        <directionalLight
          position={[5, 8, 5]}
          intensity={params.light.key}
          color={params.light.color}
          castShadow
          shadow-mapSize-width={1024}
          shadow-mapSize-height={1024}
        />
        {/* 배경 필라이트 */}
        <directionalLight position={[-4, 3, -4]} intensity={0.2} color="#3a5080" />

        {/* 씬 조명 보존 */}
        <InspectionLights />

        <group ref={factoryGroupRef}>
          <FactoryLine classes={selectedClasses} looping={looping} cycle={cycle} validation={validation} trainState={trainState} ngProb={ngProb} classResults={classResults} />
        </group>

        {/* 3x3 입체 격자 결과물 갤러리 */}
        <ResultGallery items={galleryItems} center={[0, 2.4, 0.5]} onSelect={setSelectedIdx} />

        {/* 선택된 이미지 360도 스캔 링 이펙트 */}
        <ScanRig active={selectedIdx != null} />

        {/* 선택 이미지 360도 공전 카메라 헬퍼 */}
        <CameraOrbit active={selectedIdx != null} target={[0, 2.4, 0.5]} controlsRef={controlsRef} />

        {/* 빈 곳 클릭 시 선택 해제를 위한 레이캐스트 가드 */}
        <mesh position={[0, 0, 0]} onPointerMissed={() => setSelectedIdx(null)} visible={false}>
          <boxGeometry args={[1, 1, 1]} />
        </mesh>

        {/* 무한 그리드 */}
        <Grid
          args={[24, 24]}
          cellColor="#1c2030"
          sectionColor="#2a3040"
          infiniteGrid
          fadeDistance={28}
          fadeStrength={1.5}
          position={[0, 0, 0]}
        />

        {/* 컨트롤 */}
        <OrbitControls
          ref={controlsRef}
          enableDamping
          dampingFactor={0.08}
          makeDefault
          minDistance={1.5}
          maxDistance={14}
          maxPolarAngle={Math.PI / 2.05}
        />
      </Canvas>

      {/* HUD 오버레이 */}
      <SimHUD />

      {/* 데이터셋 인테이크 오버레이 (Phase 2(B) 자율 체이닝 / Phase 2(C) 자동 순환) */}
      <div style={{ position:'absolute', left:16, bottom:16, zIndex:10,
        display:'flex', flexDirection:'column', gap:8, fontFamily:'monospace',
        background:'rgba(11,13,18,0.72)', border:'1px solid rgba(255,255,255,0.08)',
        borderRadius:10, padding:'10px 12px', minWidth:220 }}>
        <div style={{ display:'flex', gap:6, alignItems:'center', flexWrap:'wrap', justifyContent:'space-between' }}>
          <div style={{ display:'flex', gap:6, alignItems:'center' }}>
            <label style={{ padding:'6px 12px', borderRadius:8, cursor:'pointer', fontSize:12,
              border:'1px solid rgba(31,184,205,0.45)', background:'rgba(31,184,205,0.12)',
              color:'#1FB8CD', whiteSpace:'nowrap', width:'fit-content' }}>
              데이터셋 인테이크 (zip/tar)
              <input type="file" accept=".zip,.tar,.tar.gz,.tgz" hidden onChange={onIntake} />
            </label>

            <button onClick={() => looping ? stopLoop() : factoryLoop()}
              style={{ padding:'6px 12px', borderRadius:8, cursor:'pointer', fontSize:12,
                border:`1px solid ${looping ? 'rgba(248,113,113,0.5)' : 'rgba(52,211,153,0.5)'}`,
                background: looping ? 'rgba(248,113,113,0.12)' : 'rgba(52,211,153,0.12)',
                color: looping ? '#f87171' : '#34d399', width:'fit-content', whiteSpace:'nowrap' }}>
              {looping ? '■ 순환 정지' : '▶ 자동 순환 시작'}
            </button>

            <button onClick={runAllClasses}
              style={{ padding:'6px 12px', borderRadius:8, cursor:'pointer', fontSize:12,
                border:'1px solid rgba(167,139,250,0.5)',
                background: 'rgba(167,139,250,0.12)',
                color: '#a78bfa', width:'fit-content', whiteSpace:'nowrap' }}>
              🔮 클래스별 가동 (학습+판정)
            </button>

            <button onClick={() => {
              const cid = activeClass || selectedClasses[0] || 'bottle'
              showResults(cid)
            }}
              style={{ padding:'6px 12px', borderRadius:8, cursor:'pointer', fontSize:12,
                border:'1px solid rgba(31,184,205,0.5)',
                background: 'rgba(31,184,205,0.12)',
                color: '#1FB8CD', width:'fit-content', whiteSpace:'nowrap' }}>
              🔍 결과물 보기
            </button>
          </div>

          {/* MVTec 스캔 및 다중 선택 UI */}
          <div style={{ display:'flex', gap:6, alignItems:'center', fontSize:12, marginTop: 4, width: '100%' }}>
            <input value={mvtecRoot} onChange={e=>setMvtecRoot(e.target.value)}
              placeholder="MVTec 루트 경로" style={{ flex:1, padding:'4px 8px', background:'#11141a', color:'#cbd5e1', border:'1px solid #2a2f3a', borderRadius:6, outline:'none', fontSize:11 }} />
            <button onClick={scanRoot} style={{ padding:'4px 10px', borderRadius:6, cursor:'pointer', border:'1px solid #1FB8CD', background:'rgba(31,184,205,0.12)', color:'#1FB8CD', fontSize:11, fontWeight:'bold' }}>스캔</button>
          </div>
          {availableClasses.length > 0 && (
            <div style={{ display:'flex', flexWrap:'wrap', gap:6, marginTop:4, width: '100%', borderTop:'1px solid rgba(255,255,255,0.05)', paddingTop:6 }}>
              {availableClasses.map(c => (
                <button key={c} onClick={()=>toggleClass(c)} style={{
                  padding:'3px 9px', borderRadius:12, fontSize:10, cursor:'pointer',
                  border:`1px solid ${selectedClasses.includes(c)?'#1FB8CD':'#3a4150'}`,
                  background: selectedClasses.includes(c)?'rgba(31,184,205,0.18)':'transparent',
                  color: selectedClasses.includes(c)?'#1FB8CD':'#8b94a3', transition: 'all 0.15s' }}>{c}</button>
              ))}
            </div>
          )}

          <div style={{ fontSize:11, color:'#1FB8CD', fontWeight:'bold' }}>
            자율 파이프라인 · {phase}
          </div>
        </div>

        {/* 라이브 에이전트 칩 */}
        <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
          {Object.entries(simAgents).map(([name, s]) => {
            const c = s.state === 'done' ? '#34d399' : s.state === 'running' ? '#fbbf24' : '#6b7280'
            return (
              <span key={name} style={{ fontSize:11, padding:'2px 8px', borderRadius:6,
                border:`1px solid ${c}66`, color:c, background:`${c}14` }}>
                {name} · {s.state}
              </span>
            )
          })}
        </div>

        {/* 결과 */}
        {intake?.status === 'running' && <span style={{ fontSize:11, color:'#9aa0aa' }}>인테이크 가동 중…</span>}
        {intake?.domain && <span style={{ fontSize:11, color:'#cbd5e1' }}>도메인: {intake.domain.domain || intake.domain} · {intake.n_images}장</span>}
        {intake?.error && <span style={{ fontSize:11, color:'#f87171' }}>오류: {intake.error}</span>}

        {/* 사이클 카운터 및 루프 오류 정보 */}
        {(looping || cycle > 0) && (
          <div style={{ fontSize:11, color:'#cbd5e1', fontFamily:'monospace', borderTop:'1px solid rgba(255,255,255,0.05)', paddingTop:6, marginTop:2 }}>
            사이클 {cycle} {looping ? '· 가동 중' : '· 정지'}
            {validation?.escape_rate != null && ` · escape ${(validation.escape_rate*100).toFixed(0)}%`}
          </div>
        )}
        {loopError && <span style={{ fontSize:11, color:'#f87171' }}>루프 정지: {loopError}</span>}

        {/* 학습 진행 상황 */}
        {trainState && (
          <div style={{ fontSize:11, color:'#cbd5e1', borderTop:'1px solid rgba(255,255,255,0.05)', paddingTop:6, marginTop:2, display:'flex', flexDirection:'column', gap:4 }}>
            <div style={{ display:'flex', justifyContent:'space-between' }}>
              <span>학습: {trainState.status}</span>
              <span>{trainState.step} / {trainState.total_steps}</span>
            </div>
            {trainState.metrics?.loss != null && (
              <div style={{ color:'#a78bfa' }}>loss: {Number(trainState.metrics.loss).toFixed(4)}</div>
            )}
            <div style={{ width:'100%', height:4, background:'rgba(255,255,255,0.1)', borderRadius:2, overflow:'hidden' }}>
              <div style={{
                width: `${Math.round((trainState.step / trainState.total_steps) * 100)}%`,
                height: '100%',
                background: 'linear-gradient(90deg, #1FB8CD, #a78bfa)',
                transition: 'width 0.3s ease'
              }} />
            </div>
          </div>
        )}

        {/* 검증 결과 표시 */}
        {validation?.ok && (
          <div style={{ fontSize:11, color:'#cbd5e1', borderTop:'1px solid rgba(255,255,255,0.05)', paddingTop:6, marginTop:2, lineHeight:1.6 }}>
            임계값 {validation.threshold} (good μ{validation.mean_good}+3σ)<br/>
            <span style={{ color: validation.escape_rate > 0.2 ? '#f87171' : '#34d399', fontWeight: 'bold' }}>
              escape율 {(validation.escape_rate*100).toFixed(0)}%
            </span> ({validation.escapes}/{validation.n_defect} 놓침) · 오검출 {(validation.fp_rate*100).toFixed(0)}%
            
            {/* 가상 FAT 합격 판정 배지 및 기준선 추가 */}
            <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              {validation?.fat_verdict && validation.fat_verdict !== 'N/A' && (
                <div style={{
                  display:'inline-block', padding:'4px 10px', borderRadius:6, fontWeight:700, fontSize:11,
                  color: validation.fat_verdict === 'PASS' ? '#34d399' : '#f87171',
                  border: `1.5px solid ${validation.fat_verdict === 'PASS' ? 'rgba(52,211,153,0.6)' : 'rgba(248,113,113,0.6)'}`,
                  background: validation.fat_verdict === 'PASS' ? 'rgba(52,211,153,0.12)' : 'rgba(248,113,113,0.12)' }}>
                  가상 FAT · {validation.fat_verdict}
                </div>
              )}
              {validation?.pass_criteria && (
                <span style={{ fontSize:10, color:'#94a3b8' }}>
                  기준: escape ≤ {(validation.pass_criteria.max_escape_rate*100).toFixed(0)}% ·
                  FP ≤ {(validation.pass_criteria.max_fp_rate*100).toFixed(0)}%
                </span>
              )}
            </div>
          </div>
        )}
        {validation?.ok === false && (
          <span style={{ fontSize:11, color:'#f87171', borderTop:'1px solid rgba(255,255,255,0.05)', paddingTop:6, marginTop:2 }}>{validation.error}</span>
        )}
      </div>
    </div>
  )
}
