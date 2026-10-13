import React,{useState} from 'react'
const stages=['MOVE_PICK','GRIP','MOVE_INSPECT','INSPECT','MOVE_PLACE','RELEASE','RETURN_HOME']
const names=['집기 이동','그립','검사 이동','실제 검사','분류 이동','놓기','복귀']
export function LivePanel({live,closeup,setCloseup,onSelect}){
 const [speed,setSpeed]=useState(1),s=live.snapshot,resource=s?.metrics.resources['AI-INSPECTION'],robot=resource?.robot,task=s?.patrol.maintenance[0]
 const decisions=s?.live_events.filter(e=>e.type==='live_inspection_ready').slice(-6).reverse()||[]
 return <>
  <aside className="live-panel card" aria-label="Live 운영 상태"><div className="live-title"><span className={live.connected?'online-dot':'offline-dot'}/><b>LIVE OPERATIONS</b><span>CPU</span></div><h2>BOTTLE · CCIFPS</h2><p>실제 이미지 검사 · M0609 가상 제어</p>
   <div className="live-stats"><span><b>{s?.time.toFixed(1)??'—'}<small>s</small></b>공정 시간</span><span><b>{s?.metrics.wip??'—'}</b>진행 부품</span><span><b>{s?.metrics.completed??'—'}</b>완료</span></div>
   <div className="live-counts">OK <b>{s?.metrics.counts.OK??0}</b> NG <b>{s?.metrics.counts.NG??0}</b> HOLD <b>{s?.metrics.counts.SKIPPED??0}</b></div>
   <div className="live-equipment"><b>M0609</b><span>{resource?.state??'연결 중'}</span><small>{robot?.gripper??'—'} · {s?.parts.find(p=>p.robot)?.id??'부품 대기'}</small></div>
   <ol className="live-stages">{stages.map((stage,i)=><li key={stage} data-active={robot?.stage===stage} data-done={robot?.completed_steps?.includes(stage)}><span>{i+1}</span>{names[i]}</li>)}</ol>
   {s?.inspection_busy&&<p className="live-busy" role="status">CPU로 이미지를 검사하고 있습니다. 결과가 나올 때까지 부품을 잡고 대기합니다.</p>}
   <button className="live-focus" aria-pressed={closeup} onClick={()=>setCloseup(v=>!v)}>{closeup?'공정 전체 보기':'로봇 셀 확대'}</button>
   <div className="live-maintenance"><b>설비 복구</b><button disabled={!live.connected||live.pending||s?.status!=='running'||resource?.state==='DOWN'} onClick={()=>live.command('fault',{cause:'gripper_jam'})}>고장 주입</button><p>{task?`${task.robot||'순찰 로봇 배정 중'} · ${task.state}`:'고장 → 현장 확인 → 진단 → 수리 → 재검사 → 재개'}</p>{task&&<div>{task.trace.map(t=><span key={t.state}>{t.state} · {t.sim_time.toFixed(1)}s</span>)}</div>}</div>
   <details><summary>운영 범위</summary><p>BOTTLE CCIFPS 한 레인을 CPU로 검사합니다. 다른 클래스·모델은 Replay에서 볼 수 있습니다. 연구 실험과 분리된 시연이며 투입·형상·NG 위치는 assumed입니다.</p></details>
  </aside>
  <aside className="live-evidence-list card"><b>최근 실제 검사</b><small>부품 또는 결과를 눌러 근거를 확인하세요</small>{decisions.length?decisions.map(d=><button key={d.part} onClick={()=>onSelect({id:d.part,live_inspection:d})}><span>{d.part}</span><strong data-verdict={d.verdict}>{d.verdict}</strong><span>{d.score?.toFixed(4)??'—'}</span></button>):<p>Live 시작 후 첫 검사 결과가 표시됩니다.</p>}</aside>
  <section className="live-controls card" aria-label="Live 제어"><span>{live.connected?(s?.inspection_busy?'CPU 검사 중':s?.status==='running'?'가동 중':'일시정지'):'서버 연결 중'}</span><button data-action="live-toggle" disabled={!live.connected||live.pending||s?.status==='completed'} onClick={()=>live.command(`control/${s?.status==='running'?'pause':'start'}`,{speed})}>{live.pending?'요청 중…':s?.status==='running'?'일시정지':'Live 시작'}</button><select aria-label="Live 속도" value={speed} disabled={live.pending} onChange={e=>{const v=Number(e.target.value);setSpeed(v);if(s?.status==='running')live.command('control/start',{speed:v})}}>{[1,2,5,20].map(v=><option key={v} value={v}>{v}×</option>)}</select><small>서버 DES 시계 · sim=1</small></section>
  {(live.error||s?.error)&&<aside className="error card" role="alert">{live.error||s.error}</aside>}
 </>
}
export function LiveEvidence({part,close}){
 if(!part)return null
 const d=part.live_inspection
 return <aside className="live-evidence card" aria-label="실제 검사 근거"><button className="live-evidence-close" onClick={close}>닫기 ×</button><h2>{part.id} · {d?.verdict||'검사 대기'}</h2>{d?<><p>CCIFPS · score {d.score?.toFixed(6)??'—'} · threshold {d.threshold?.toFixed(6)??'—'}</p>{d.evidence?<div><figure><img src={d.evidence.original_url} alt={`${part.id} 실제 검사 원본`}/><figcaption>실제 입력 이미지</figcaption></figure><figure><img src={d.evidence.overlay_url} alt={`${part.id} 실제 이상 탐지 히트맵`}/><figcaption>모델 이상 점수 히트맵</figcaption></figure></div>:<p>{d.reason||'근거 이미지 없음'}</p>}</>:<p>이 부품은 아직 검사되지 않았습니다.</p>}</aside>
}
