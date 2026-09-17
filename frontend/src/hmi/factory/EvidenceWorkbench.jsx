import SceneErrorBoundary from '../panels/SceneErrorBoundary'
import { Suspense, useEffect, useRef, useState } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { OrbitControls, useTexture, Html, Line } from '@react-three/drei'
import { factoryApi, useFactory } from './factoryStore'

function EvidencePlate({evidence,overlay,zoom}) {
  const texture=useTexture(overlay?evidence.overlay_url:evidence.original_url)
  const aspect=evidence.original_size[0]/evidence.original_size[1]
  const width=2.6*aspect,height=2.6
  const [u,v]=evidence.peak_uv
  const target=[(u-.5)*width,(.5-v)*height,.04]
  const {camera}=useThree();const control=useRef()
  useEffect(()=>{if(!control.current)return;control.current.target.set(...(zoom?target:[0,0,0]));camera.position.set(zoom?target[0]:1.7,zoom?target[1]:1,zoom?1.8:5);control.current.update()},[zoom,evidence.id])
  return <>
    <mesh position={[0,0,-.08]}><boxGeometry args={[width+.12,height+.12,.13]}/><meshStandardMaterial color="#385263" metalness={.45} roughness={.4}/></mesh>
    <mesh><planeGeometry args={[width,height]}/><meshBasicMaterial map={texture}/></mesh>
    <Line points={[[target[0]-.16,target[1],.02],[target[0]+.16,target[1],.02]]} color="#30ffff" lineWidth={2}/>
    <Line points={[[target[0],target[1]-.16,.02],[target[0],target[1]+.16,.02]]} color="#30ffff" lineWidth={2}/>
    <Html position={[target[0],target[1]+.22,.04]} center><span className="evidence-pin">최대 반응 패치 · {evidence.peak_pixel.join(', ')} px</span></Html>
    <OrbitControls ref={control} minDistance={.7} maxDistance={9} maxPolarAngle={Math.PI*.85}/>
  </>
}
export default function EvidenceWorkbench({onClose}) {
  const snap=useFactory(s=>s.snapshot)
  const [catalog,setCatalog]=useState(null),[image,setImage]=useState(''),[result,setResult]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[overlay,setOverlay]=useState(true),[zoom,setZoom]=useState(false)
  useEffect(()=>{factoryApi('/inspection/catalog').then(c=>{setCatalog(c);setImage(c.images.find(i=>i.label!=='good')?.path||c.images[0]?.path||'')}).catch(e=>setError(e.message))},[])
  const recent=[...(snap.inspections||[])].reverse().filter(x=>x.evidence)
  const e=result?.evidence
  async function inspect(){setBusy(true);setError('');try{const item=catalog.images.find(i=>i.path===image),bundle=catalog.bundles.find(b=>b.category===item.category);setResult(await factoryApi('/inspection/preview',{image,run_id:bundle.run_id}));setZoom(false)}catch(err){setError(err.message)}finally{setBusy(false)}}
  return <div className="engineering-modal" role="dialog" aria-label="입체 검사 작업대"><header><div><small>INSPECTION EVIDENCE</small><h2>입체 검사 작업대</h2></div><button onClick={onClose}>닫기 ×</button></header>
    <div className="engineering-body"><section className="engineering-canvas">
      {e?<SceneErrorBoundary><Canvas camera={{position:[1.7,1,5],fov:40}}><color attach="background" args={['#0d1e2b']}/><ambientLight intensity={1.3}/><directionalLight position={[3,4,5]} intensity={2}/><Suspense fallback={null}><EvidencePlate evidence={e} overlay={overlay} zoom={zoom}/></Suspense></Canvas></SceneErrorBoundary>:<div className="engineering-placeholder">검사 이미지를 선택한 뒤 CCIFPS 분석을 실행하세요.<br/>공정 검사 이력도 여기서 다시 열 수 있습니다.</div>}
      <div className="engineering-controls"><button onClick={()=>setOverlay(!overlay)}>{overlay?'원본 보기':'히트맵 보기'}</button><button disabled={!e} onClick={()=>setZoom(!zoom)}>{zoom?'전체 보기':'최대 반응 부위 확대'}</button><span>드래그 회전 · 휠 확대 · 우클릭 이동</span></div>
    </section><aside><h3>실제 검사 근거</h3><label>로컬 데이터셋<select aria-label="Inspection image" value={image} onChange={ev=>setImage(ev.target.value)}>{catalog?.images.map(i=><option key={i.path} value={i.path}>{i.category} / {i.label} / {i.path.split('/').pop()}</option>)}</select></label><button className="primary" disabled={busy||!image} onClick={inspect}>{busy?'CCIFPS 추론 중…':'CCIFPS 분석 실행'}</button>
      {error&&<p role="alert">{error}</p>}
      {result&&<><strong className={`evidence-verdict ${result.verdict}`}>{result.verdict}</strong><p>점수 {result.score?.toFixed(4)} / 임계값 {result.threshold?.toFixed(4)}</p><p>모델 {result.mode} · {result.run_id}</p></>}
      {e&&<><p>원본 {e.original_size.join(' × ')} px<br/>패치 맵 {e.map_shape.join(' × ')}</p><p>히트맵은 이미지별 상대 반응입니다. 표시된 최대 반응점이 반드시 결함이라는 뜻은 아닙니다.</p><a href={e.original_url} target="_blank" rel="noreferrer">원본 열기 ↗</a></>}
      <h4>공정 검사 이력</h4>{recent.length?recent.slice(0,8).map(r=><button key={r.part} onClick={()=>{setResult(r);setZoom(false)}}>{r.part} · {r.verdict}</button>):<p>실제 검사 이력이 아직 없습니다. Mock 결과에는 이미지 근거가 없습니다.</p>}
      <p className="engineering-note">2D 검사면을 공간에서 회전·확대하는 뷰입니다. 실제 깊이·뒷면 복원은 하지 않으며, 제품 결함으로 설비 고장을 단정하지 않습니다.</p>
    </aside></div></div>
}
