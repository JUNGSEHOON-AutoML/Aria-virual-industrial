import React, { Suspense, useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Canvas, useThree } from '@react-three/fiber'
import { CameraControls, ContactShadows, Environment, OrthographicCamera } from '@react-three/drei'
import * as THREE from 'three'
import { Scene } from './scene'
import './style.css'

const VIEWS = {
  overview: { label: '전체 보기', target: [0, 0, 1], zoom: 32 },
  line: { label: '검사 라인', target: [0, .4, 0], zoom: 76 },
  reinspection: { label: '재검사 구역', target: [3, .6, 4.7], zoom: 102 },
}
function Camera({ view, revision }) {
  const controls = useRef()
  const { camera, size, invalidate } = useThree()
  useEffect(() => {
    const { target: [x,y,z], zoom } = VIEWS[view]
    controls.current?.zoomTo(zoom * Math.min(size.width / 1440, size.height / 900), false)
    controls.current?.setLookAt(x+20, y+19.8, z+20, x,y,z, false)
    invalidate()
  }, [view, revision, size.width, size.height, camera, invalidate])
  return <CameraControls ref={controls} makeDefault minAzimuthAngle={Math.PI/4-Math.PI/9} maxAzimuthAngle={Math.PI/4+Math.PI/9} minPolarAngle={Math.PI/2-35*Math.PI/180} maxPolarAngle={Math.PI/2-35*Math.PI/180} minZoom={16} maxZoom={160} smoothTime={.6}/>
}
function Lighting() {
  return <><Suspense fallback={null}><Environment files="/d0/potsdamer_platz_1k.hdr" environmentIntensity={.25}/></Suspense><ambientLight intensity={.55}/><hemisphereLight args={['#ffffff','#d0d7ed',.35]}/>
    <directionalLight position={[-8,20,12]} intensity={1.1} castShadow shadow-mapSize={[2048,2048]} shadow-camera-left={-25} shadow-camera-right={25} shadow-camera-top={25} shadow-camera-bottom={-25} shadow-camera-far={70} shadow-normalBias={.035}/>
    <ContactShadows position={[0,-.012,0]} opacity={.22} scale={55} blur={2.5} far={5} resolution={512} frames={1} color="#6174ac"/>
  </>
}
function Diagnostics() {
  const { gl, scene } = useThree()
  useEffect(() => {
    window.__d0 = { renderer: gl.getContext().getParameter(gl.getContext().getExtension('WEBGL_debug_renderer_info')?.UNMASKED_RENDERER_WEBGL || gl.getContext().RENDERER), scene, ready:true, audit: () => {
      scene.updateMatrixWorld(true)
      const grounded=[]
      scene.traverse(o=>{if(o.userData.grounded){const b=new THREE.Box3().setFromObject(o);grounded.push({name:o.name,bottom:b.min.y,top:b.max.y})}})
      return {grounded, floating:grounded.filter(x=>x.bottom>.02), belowFloor:grounded.filter(x=>x.bottom<-.02), cameraZoom:window.__d0.camera?.zoom}
    } }
    return () => { delete window.__d0 }
  }, [gl,scene])
  return null
}
function App() {
  const initial = new URLSearchParams(location.search).get('view')
  const [view,setView] = useState(VIEWS[initial] ? initial : 'overview')
  const [revision,reset] = useState(0)
  return <main>
    <div className="viewport"><Canvas shadows frameloop="demand" dpr={1} gl={{antialias:true,toneMapping:THREE.ACESFilmicToneMapping,toneMappingExposure:1.25,preserveDrawingBuffer:true}}>
      <color attach="background" args={['#E4E9F7']}/><OrthographicCamera makeDefault position={[20,19.8,21]} near={.1} far={150} zoom={32}/>
      <Lighting/><Suspense fallback={null}><Scene/></Suspense><Camera view={view} revision={revision}/><Diagnostics/>
    </Canvas></div>
    <header><div className="brand"><span className="brand-icon">A</span><div>ARIA <b>Inspection Lab</b></div></div><span className="divider"/><span className="site">검사동 <b>01</b></span><span className="mode">D0 · 룩데브</span><span className="header-note">고정 장면 · 데이터 연결 전</span></header>
    <section className="caption"><small>INSPECTION CAMPUS</small><h1>{VIEWS[view].label}</h1><p>투입에서 분류까지, 한눈에 보는 검사 공정</p></section>
    <nav aria-label="고정 시점">{Object.entries(VIEWS).map(([id,v],i)=><button key={id} aria-pressed={view===id} onClick={()=>{setView(id);history.replaceState(null,'',`?view=${id}`)}}><span>0{i+1}</span>{v.label}</button>)}<button className="reset" onClick={()=>reset(n=>n+1)}>시점 초기화 ↺</button></nav>
    <footer><div><b>장면 검토</b><span>드래그 회전 · 우클릭 이동 · 휠 확대</span></div><span>배치·소품은 룩데브용 고정 예시입니다</span><span className="gate">D0 승인 대기</span></footer>
  </main>
}
createRoot(document.getElementById('root')).render(<App/> )
