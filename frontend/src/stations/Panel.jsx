import React,{useEffect,useState} from 'react'
export function StationPanel({selected,clock,close,live}){
 const [data,setData]=useState(null),[error,setError]=useState('')
 const run=selected?.live?null:selected?.data?.run_id
 useEffect(()=>{setData(null);setError('');if(!run)return;let alive=true,timer;const c=new AbortController()
  async function poll(){try{const r=await fetch(`/api/dt/runs/${run}/stations/detail?t=${clock.read()}`,{signal:c.signal});if(!r.ok)throw Error('검사 근거를 읽지 못했습니다.');const d=await r.json();if(alive)setData(d)}catch(e){if(e.name!=='AbortError')setError(e.message)}if(alive)timer=setTimeout(poll,1500)}
  poll();return()=>{alive=false;c.abort();clearTimeout(timer)}
 },[run,clock])
 useEffect(()=>{if(!selected?.live||!live?.snapshot?.station)return;const s=live.snapshot,projection=s.station,recent=projection.recent.slice().reverse()
  setData({time:s.time,class_name:'bottle',camera:{image_resolution:projection.camera_resolution||[],inference_resolution:[224,224]},threshold:recent[0]?.threshold,latency_ms:projection.latency_ms,products:[],parameters:projection.parameters,recent:recent.map(r=>({...r,part_id:r.id,original:r.evidence?.original_url,overlay:r.evidence?.overlay_url}))})
 },[selected?.live,live?.snapshot])
 if(!selected)return null
 return <aside className="station-panel card" aria-label="검사 스테이션 상세"><button className="station-close" onClick={close}>닫기 ×</button>
  <h2>{selected.site.name}</h2><p>{selected.selector} · 고정 카메라 검사</p>
  {error?<p role="alert">{error}</p>:!data?<p>저장된 검사 근거를 읽고 있습니다.</p>:<>
   <dl><dt>촬영 방향</dt><dd>위에서 수직 하향 · 데이터셋 기준</dd><dt>원본 / 모델 입력</dt><dd>{data.camera.image_resolution.join(' × ')} / 224 × 224 px</dd><dt>임계값</dt><dd>{data.threshold?.toFixed(6)??'검사 대기'}</dd><dt>검사 지연 p50 / p95</dt><dd>{data.latency_ms.p50?.toFixed(2)??'—'} / {data.latency_ms.p95?.toFixed(2)??'—'} ms</dd></dl>
   <small>{selected.live?'실제 CPU 검사 시간':'저장된 실측 지연'} · {data.time.toFixed(2)}s까지 · 측면 카메라 비활성</small>
   {data.products.length>0&&<section><h3>{data.class_name==='carpet'?'완료 롤 등급':'완료 OK 통'}</h3><p>팔레트는 대표 형상 · 완료 목록은 실제 ID
용량·등급 규칙 assumed · 원본 판정/생산량 보존</p>{data.class_name==='carpet'&&<small>A ≤ {data.parameters.grade_a_max_labels.value}개 / B ≤ {data.parameters.grade_b_max_labels.value}개 / C 초과</small>}{data.products.map(p=><details key={p.id}><summary>{p.id.split(':').slice(-2).join(' ')} · {p.grade??p.parts.length+'개'}</summary><p>구간/부품 {p.parts.length}개{p.labels&&` · 라벨 ${p.labels.length}개 · 미확정 ${p.unresolved}개`}</p>{p.unlabelled_defects_evaluated!=null&&<p>감긴 무라벨 결함: {p.unlabelled_defects_evaluated}개 · 미탐(OK 판정 결함): {p.false_negatives_evaluated}개 (사후 평가)</p>}</details>)}</section>}
   <h3>최근 판정 {data.recent.length}개</h3><small>{selected.live?'실제 CPU 검사 근거':'원본 모델 입력과 저장 점수 히트맵 · 새 추론 없음'}</small>
   <div className="station-evidence">{data.recent.map(p=><article key={p.part_id}><div><b>{p.part_id}</b><strong data-verdict={p.verdict}>{p.verdict}</strong><span>{p.score?.toFixed(4)??'—'}</span></div><div>{p.original&&<img src={p.original} alt={`${p.part_id} 상부 촬영 입력`} loading="lazy"/>}{p.overlay&&<img src={p.overlay} alt={`${p.part_id} 저장 이상 점수 히트맵`} loading="lazy"/>}</div></article>)}</div>
  </>}
 </aside>
}
