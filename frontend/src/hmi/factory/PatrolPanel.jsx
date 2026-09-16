import { useFactory, factoryApi } from './factoryStore'

const labels={equipment_down:'설비 고장',flow_blocked:'물류 정체',material_starvation:'자재 공급 부족',inspection_skipped:'검사 누락'}
export default function PatrolPanel() {
  const patrol=useFactory(s=>s.patrol),selected=useFactory(s=>s.selected),snapshot=useFactory(s=>s.snapshot)
  const action=useFactory(s=>s.action),busy=useFactory(s=>s.busy),select=useFactory(s=>s.select)
  if (!patrol) return <p>순찰 서비스에 연결 중…</p>
  const target=snapshot.model.components.find(c=>c.id===selected && ['Machine','Inspection'].includes(c.kind)) || snapshot.model.components.find(c=>c.kind==='Machine')
  return <div className="patrol-panel">
    <header><b>ARIA FIELD TEAM · {patrol.open_incidents} active</b><div>
      <button onClick={async()=>{const p=await action('/patrol/control',{enabled:!patrol.enabled});if(p)useFactory.setState({patrol:p})}}>{patrol.enabled?'Pause patrol':'Resume patrol'}</button>
      <a href="/api/factory/patrol/report" download>Download report ↓</a>
    </div></header>
    <small>생산 정지 중에도 순찰합니다. 보고서 근거는 가상 공장의 실제 DES 신호입니다.</small>
    <div className="patrol-team">{patrol.robots.map(r=><button key={r.id} onClick={()=>r.target&&select(r.target)}><strong>{r.id}</strong><span>{r.state}</span><small>{r.target} · {r.visits} inspections</small></button>)}</div>
    {target&&<button className="patrol-fault" disabled={busy} onClick={()=>action('/patrol/fault',{component:target.id,duration:60})}>고장 시나리오 실행 · {target.id} (60s)</button>}
    <small>고장 시나리오는 시뮬레이션을 시작합니다. 로봇이 임의 수리하거나 공장 설정을 바꾸지 않습니다.</small>
    {patrol.storage_error&&<p role="alert">보고서 저장 오류: {patrol.storage_error}</p>}
    {!patrol.reports.length&&<p className="factory-empty">현재까지 관찰된 이상이 없습니다. 설비 상태가 변하면 보고 에이전트가 근거와 대응 상태를 기록합니다.</p>}
    {patrol.reports.map(r=><article key={r.id} className={`patrol-incident ${r.severity}`}>
      <div><button onClick={()=>select(r.component)}>{r.component}</button><b>{labels[r.kind]||r.kind}</b><span>{r.status}</span></div>
      <p>{r.id} · {Number(r.detected_sim_time).toFixed(1)}s · {r.source}</p>
      <p>현장 확인: {r.verified_by||'출동/확인 대기'}</p>
      <details><summary>Evidence & report</summary><pre>{JSON.stringify(r.evidence,null,2)}</pre><p>{r.recommendation}</p><p>{r.outcome}</p>{r.visits.map((v,i)=><p key={i}>{v.robot} · {v.state} · {Number(v.sim_time).toFixed(1)}s</p>)}</details>
    </article>)}
  </div>
}
