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
    {target&&<button className="patrol-fault" disabled={busy} onClick={()=>action('/maintenance/fault',{component:target.id,cause:target.kind==='Inspection'?'camera_disconnect':'gripper_jam'})}>자율 수리 시나리오 · {target.id}</button>}
    <small>가상 고장 주입 → 로봇 현장 도착 → 진단 → 허용 도구 → 재검사. 설비는 검증 통과 후 재가동 가능하며, 생산 Run은 별도입니다.</small>
    {patrol.maintenance?.slice(0,3).map(t=><article key={t.id} className="maintenance-card"><b>{t.component} · {t.state}</b><span>{t.robot||'출동 대기'} · {t.elapsed.toFixed(1)}s</span><ol className="maintenance-trace">{t.trace.map((x,i)=><li key={i}><b>{x.state}</b><small>{x.tool}</small></li>)}</ol><details><summary>실행·검증 근거</summary><pre>{JSON.stringify(t.trace,null,2)}</pre></details></article>)}
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
