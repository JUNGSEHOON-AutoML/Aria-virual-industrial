import { useEffect, useState } from 'react'
import { useFactory, factoryApi, subscribeFactory } from './factoryStore'
import FactoryScene from './FactoryScene'
import PatrolPanel from './PatrolPanel'
import SceneErrorBoundary from '../panels/SceneErrorBoundary'
import './factory.css'

const KINDS = ['Source', 'Conveyor', 'Buffer', 'Machine', 'Inspection', 'Diverter', 'Sink']
const ICONS = ['↥', '═', '▤', '⚙', '◎', '⑂', '▣']
const number = (n, digits = 1) => Number(n || 0).toFixed(digits)

function Properties({ c, revision }) {
  const action = useFactory(s => s.action)
  const busy = useFactory(s => s.busy)
  const [draft, setDraft] = useState(c)
  const [target, setTarget] = useState('')
  const [condition, setCondition] = useState('always')
  const snapshot = useFactory(s => s.snapshot)
  useEffect(() => { setDraft(c) }, [c.id, revision])
  const fields = ['capacity', ...(c.kind === 'Source' ? ['interarrival', 'batch_size'] : []),
    ...(c.kind === 'Conveyor' ? ['length', 'speed'] : []),
    ...(['Machine', 'Inspection'].includes(c.kind) ? ['processing_time', 'setup_time', 'mtbf', 'mttr', 'availability'] : []),
    ...(c.kind === 'Inspection' ? ['defect_rate', 'threshold'] : [])]
  const resource = snapshot.metrics.resources[c.id]
  return <div className="factory-properties">
    <h3>{c.id}</h3><span className="factory-tag">{c.kind} · {resource.state}</span>
    <label>Name<input value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} /></label>
    {fields.map(k => <label key={k}>{k.replaceAll('_', ' ')}<input aria-label={k} type="number" step="any" value={draft[k]} onChange={e => setDraft({ ...draft, [k]: Number(e.target.value) })} /></label>)}
    <div className="factory-xyz">{['X', 'Y', 'Z'].map((k, i) => <label key={k}>{k}<input aria-label={`position ${k}`} type="number" step=".5" value={draft.position[i]} onChange={e => setDraft({ ...draft, position: draft.position.map((v, j) => j === i ? Number(e.target.value) : v) })} /></label>)}</div>
    <label>Rotation (rad)<input aria-label="rotation" type="number" step=".1" value={draft.rotation} onChange={e => setDraft({ ...draft, rotation: Number(e.target.value) })} /></label>
    {c.kind === 'Buffer' && <label>Queue<select value={draft.queue_discipline} onChange={e => setDraft({ ...draft, queue_discipline: e.target.value })}><option>FIFO</option><option>LIFO</option></select></label>}
    {c.kind === 'Inspection' && <>
      <label>Inspection mode<select value={draft.inspection_mode} onChange={e => setDraft({ ...draft, inspection_mode: e.target.value })}>{['mock', 'patchcore', 'ccifps', 'combined'].map(x => <option key={x}>{x}</option>)}</select></label>
      <label>CCIFPS run ID<input value={draft.run_id} onChange={e => setDraft({ ...draft, run_id: e.target.value })} /></label>
      <label>Bank path<input value={draft.bank} placeholder="banks/bottle.npy" onChange={e => setDraft({ ...draft, bank: e.target.value })} /></label>
      <label>Product images (one path per line)<textarea value={draft.image_paths.join('\n')} onChange={e => setDraft({ ...draft, image_paths: e.target.value.split('\n').filter(Boolean) })} /></label>
      <small>실제 모드는 기존 검출기를 사용합니다. 이미지·모델 오류는 SKIPPED로 분류됩니다.</small>
    </>}
    <label className="factory-check"><input type="checkbox" checked={draft.maintenance} onChange={e => setDraft({ ...draft, maintenance: e.target.checked })} /> Maintenance</label>
    <button className="primary" disabled={busy} onClick={() => {
      const changes = Object.fromEntries(Object.entries(draft).filter(([k, v]) => k !== 'id' && JSON.stringify(v) !== JSON.stringify(c[k])))
      action(`/components/${c.id}`, changes, 'PATCH')
    }}>Review changes</button>
    <h4>CONNECTION</h4>
    <select aria-label="Connection target" value={target} onChange={e => setTarget(e.target.value)}><option value="">Choose target</option>{snapshot.model.components.filter(n => n.id !== c.id && n.kind !== 'Source').map(n => <option key={n.id}>{n.id}</option>)}</select>
    <select aria-label="Routing condition" value={condition} onChange={e => setCondition(e.target.value)}>{['always', 'OK', 'NG', 'SKIPPED'].map(x => <option key={x}>{x}</option>)}</select>
    <button disabled={!target || busy} onClick={() => action('/connect', { source: c.id, target, condition })}>Connect</button>
    {snapshot.model.connections.filter(e => e.source === c.id).map(e => <small key={e.condition}>{e.condition} → {e.target}</small>)}
    <h4>MEASURED</h4><small>Utilization {number(resource.utilization * 100)}%<br />Waiting {number(resource.waiting_time)}s<br />Blocked {number(resource.blocking_time)}s<br />Starved {number(resource.starvation_time)}s<br />Down {number(resource.downtime)}s</small>
    <button className="danger" disabled={busy} onClick={() => action(`/components/${c.id}`, {}, 'DELETE')}>Delete component…</button>
  </div>
}

function Approval() {
  const proposal = useFactory(s => s.proposal), decide = useFactory(s => s.decide), busy = useFactory(s => s.busy)
  if (!proposal) return null
  const before = new Map(proposal.before.components.map(c => [c.id, c]))
  const changes = []
  for (const c of proposal.after.components) {
    const old = before.get(c.id)
    if (!old) changes.push(`${c.id}: add ${c.kind}`)
    else for (const [k, value] of Object.entries(c)) if (JSON.stringify(value) !== JSON.stringify(old[k])) changes.push(`${c.id} · ${k}: ${JSON.stringify(old[k])} → ${JSON.stringify(value)}`)
    before.delete(c.id)
  }
  for (const cid of before.keys()) changes.push(`${cid}: delete`)
  if (JSON.stringify(proposal.before.connections) !== JSON.stringify(proposal.after.connections)) changes.push(`Connections: ${JSON.stringify(proposal.after.connections)}`)
  return <div className="factory-approval" role="dialog" aria-label="Review factory change">
    <h3>ARIA proposes a factory change</h3><p>{proposal.reason}</p>
    <ul>{changes.map((c, i) => <li key={i}>{c}</li>)}</ul>
    {proposal.expected && <strong>{number(proposal.expected.baseline)}/h → {number(proposal.expected.candidate)}/h · +{number(proposal.expected.improvement_percent)}%</strong>}
    <details><summary>Full before / after model</summary><pre>{JSON.stringify({ before: proposal.before, after: proposal.after }, null, 2)}</pre></details>
    <p>Apply resets the simulation and saves the new factory. 기존 실검사 라인은 유지됩니다.</p>
    <div><button className="primary" disabled={busy} onClick={() => decide('apply')}>Apply</button><button disabled={busy} onClick={() => decide('reject')}>Reject</button></div>
  </div>
}

function Experiment({ result }) {
  if (!result) return <p className="factory-empty">에이전트에게 처리량 개선을 요청하면 동일 seed의 실제 실험을 비교합니다.</p>
  const rows = [{ changes: 'Baseline', ...result.baseline }, ...result.candidates]
  return <table><thead><tr>{['Scenario', 'Throughput /h', 'Lead /s', 'Cycle /s', 'WIP', 'OEE', 'Gain'].map(x => <th key={x}>{x}</th>)}</tr></thead>
    <tbody>{rows.map((r, i) => <tr key={i}><td>{typeof r.changes === 'string' ? r.changes : Object.entries(r.changes).map(([k, v]) => `${k}=${Number.isInteger(v) ? v : Number(v.toFixed(3))}`).join(', ')}</td><td>{number(r.metrics.throughput_per_hour)}</td><td>{number(r.metrics.lead_time)}</td><td>{number(r.metrics.cycle_time)}</td><td>{r.metrics.wip}</td><td>{number(r.metrics.oee * 100)}%</td><td>{r.improvement_percent == null ? '—' : `${number(r.improvement_percent)}%`}</td></tr>)}</tbody></table>
}

export default function FactoryWorkspace() {
  const store = useFactory()
  const { snapshot: snap, selected, select, action, error, busy, messages, chat, experiment, scenarios } = store
  const [view, setView] = useState('overview'), [labels, setLabels] = useState(false), [paths, setPaths] = useState(false)
  const [speed, setSpeed] = useState('5'), [editMode, setEditMode] = useState(false), [tab, setTab] = useState('Patrol'), [input, setInput] = useState('')
  useEffect(() => {
    const unsub = subscribeFactory()
    store.refresh(); store.loadScenarios()
    // REST recovers the authoritative snapshot after reconnection or idle reload.
    const timer = setInterval(() => useFactory.getState().refresh(), 5000)
    return () => { unsub(); clearInterval(timer) }
  }, [])
  const save = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(snap.model, null, 2)], { type: 'application/json' }))
    const a = document.createElement('a'); a.href = url; a.download = `${snap.model.id}.json`; a.click(); URL.revokeObjectURL(url)
  }
  if (!snap) return <div className="factory-workspace"><p>Loading factory…</p>{error && <p role="alert">{error}</p>}</div>
  const component = snap.model.components.find(c => c.id === selected)
  const m = snap.metrics
  return <div className="factory-workspace">
    <div className="factory-toolbar"><div><b>FACTORY WORKSPACE</b><span>{snap.model.name} · seed {snap.model.seed}</span></div>
      <span className={`factory-status ${snap.status}`}>{snap.status.toUpperCase()} · {number(snap.time)}s</span>
      <select aria-label="Simulation speed" value={speed} onChange={e => setSpeed(e.target.value)}>{['1', '2', '5', '20', 'MAX'].map(s => <option key={s} value={s}>{s === 'MAX' ? 'MAX' : `${s}×`}</option>)}</select>
      <button className="primary" disabled={busy} onClick={() => action('/run', { speed })}>▶ Run</button>
      <button disabled={busy} onClick={() => action('/pause')}>Pause</button><button disabled={busy} onClick={() => action('/resume', { speed })}>Resume</button>
      <button disabled={busy} onClick={() => action('/step')}>Step</button><button disabled={busy} onClick={() => action('/reset')}>Reset</button>
      <button onClick={save}>Save JSON</button><label className="factory-file">Load JSON<input aria-label="Load factory JSON" type="file" accept=".json" onChange={async e => {
        try { const file = e.target.files[0]; if (file) await action('/model', JSON.parse(await file.text()), 'PUT') }
        catch (err) { useFactory.setState({ error: err.message }) }
        e.target.value = ''
      }} /></label>
    </div>
    {(error || snap.error || snap.storage_error) && <div className="factory-error" role="alert">{error || snap.error || snap.storage_error}<button onClick={() => useFactory.setState({ error: '' })}>×</button></div>}
    <div className="factory-kpis">{[['THROUGHPUT', `${number(m.throughput_per_hour)} /h`], ['GOOD OUTPUT', `${number(m.good_throughput_per_hour)} /h`], ['WIP', m.wip], ['LEAD TIME', `${number(m.lead_time)} s`], ['CYCLE TIME', `${number(m.cycle_time)} s`], ['DEFECT RATE', `${number(m.defect_rate * 100)}%`], ['OEE · V1', `${number(m.oee * 100)}%`]].map(([k, v]) => <div key={k}><small>{k}</small><strong>{v}</strong></div>)}</div>
    <div className="factory-main">
      <aside className="factory-palette"><h4>MATERIAL FLOW</h4>{KINDS.map((kind, i) => <button key={kind} disabled={busy} onClick={() => {
        const id = `${kind.toUpperCase()}-${snap.model.components.length + 1}-${Date.now().toString(36).slice(-4)}`
        action('/components', { id, kind, position: [0, 0, 5], capacity: kind === 'Buffer' ? 5 : 1 })
      }}><i>{ICONS[i]}</i>{kind}<span>+</span></button>)}
        <h4>FACTORY HIERARCHY</h4>{snap.model.components.map(c => <button key={c.id} className={selected === c.id ? 'active' : ''} onClick={() => select(c.id)}>{c.id}</button>)}
        <h4>LOGISTICS · V2</h4><small>AGV · Robot · Worker<br />Sensor · Camera · AI Server</small>
        <button disabled={busy} onClick={() => action('/tools/undo_factory_change')}>Undo change…</button>
      </aside>
      <div className="factory-viewport"><div className="factory-scene-caption"><span>3D PROCESS ENGINEERING</span><div className="factory-view-tools">
          <button className={view === 'overview' ? 'active' : ''} onClick={() => setView('overview')}>Factory view</button>
          <button className={view === 'top' ? 'active' : ''} onClick={() => setView('top')}>Top</button>
          <button className={view === 'cell' ? 'active' : ''} onClick={() => setView('cell')}>Cell close-up</button>
          <button className={labels ? 'active' : ''} onClick={() => setLabels(!labels)}>Labels</button>
          <button className={paths ? 'active' : ''} onClick={() => setPaths(!paths)}>Flow paths</button>
        </div><button className={editMode ? 'active' : ''} onClick={() => setEditMode(!editMode)}>{editMode ? 'Move on XZ ✓' : 'Move on XZ'}</button></div>
        <SceneErrorBoundary><FactoryScene view={view} labels={labels} paths={paths} snapshot={snap} selected={selected} onSelect={select} editMode={editMode} onMove={(id, position) => action(`/components/${id}`, { position }, 'PATCH')} /></SceneErrorBoundary>
        <div className="factory-legend">● Processing <span>● Blocked</span><em>● Down</em> · Orbit / Pan / Zoom · Robot pose follows DES processing; no collision solver</div>
      </div>
      <aside className="factory-inspector"><h4>PROPERTY INSPECTOR</h4>{component ? <Properties c={component} revision={snap.revision} /> : <p className="factory-empty">Select an object in the factory to inspect and edit its properties.</p>}</aside>
    </div>
    <div className="factory-bottom"><section className="factory-analysis"><nav>{['Patrol', 'Bottleneck', 'Events', 'Experiments', 'Scenarios'].map(t => <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>{t}</button>)}</nav>
      <div className="factory-analysis-content">
        {tab === 'Patrol' && <PatrolPanel />}
        {tab === 'Bottleneck' && <>{snap.time < 30 && <small>초기 구간입니다. 30초 이상 실행하면 병목 비교가 더 유용합니다.</small>}{snap.bottlenecks.map((b, i) => <div className="factory-bottleneck" key={b.component}><b>{i + 1}. {b.component}</b><div><span style={{ width: `${Math.min(100, b.utilization * 100)}%` }} /></div><span>{number(b.utilization * 100)}% utilization · queue {number(b.upstream_queue)} · wait {number(b.upstream_wait)}s</span></div>)}</>}
        {tab === 'Events' && <><small>Next: {snap.next_events.map(e => `${number(e.time)}s ${e.event}`).slice(0, 4).join(' · ')}</small>{[...snap.events].reverse().slice(0, 60).map((e, i) => <div className="factory-event" key={i}><span>{number(e.time, 2)}s</span>{e.type} · {e.component} · {e.part || e.state || e.event}{e.reason && ` · ${e.reason}`}</div>)}</>}
        {tab === 'Experiments' && <Experiment result={experiment} />}
        {tab === 'Scenarios' && <><button disabled={busy || scenarios.length < 2} onClick={async () => { const rows = await action('/tools/compare_scenarios', { ids: scenarios.slice(0, 12).map(s => s.id), duration: 600 }); if (rows) { useFactory.setState({ experiment: { baseline: rows[0], candidates: rows.slice(1).map(r => ({ ...r, changes: scenarios.find(s => s.id === r.id)?.name || r.id })) } }); setTab('Experiments') } }}>Compare saved scenarios</button><button disabled={busy} onClick={async () => { await action('/scenarios', { name: `Scenario ${scenarios.length + 1}` }); store.loadScenarios() }}>Save current scenario</button>{scenarios.map(s => <div className="factory-scenario" key={s.id}><b>{s.name}</b><button disabled={busy} onClick={async () => { const r = await action(`/scenarios/${s.id}/run`); if (r) { useFactory.setState({ experiment: { baseline: r, candidates: [] } }); setTab('Experiments') } }}>Run 600s</button><button disabled={busy} onClick={() => action('/model', s.model, 'PUT')}>Load…</button></div>)}</>}
      </div></section>
      <section className="factory-chat"><header><b>ARIA INDUSTRIAL AGENT</b><span>{busy ? 'Working…' : 'Local AI · measured tools'}</span></header>
        <div className="factory-chat-messages">{messages.length === 0 && <p className="factory-empty">공장의 상태를 질문하거나, 실제 실험으로 개선안을 찾아보세요.</p>}{messages.map((msg, i) => <div key={i} className={`factory-message ${msg.role}`}><small>{msg.role === 'user' ? 'YOU' : 'ARIA'}</small><p>{msg.text}</p>{msg.trace && <details><summary>{msg.trace.length} tool calls · {msg.route}</summary><ol>{msg.trace.map((s, j) => <li key={j}>{s.tool}</li>)}</ol></details>}</div>)}</div>
        <div className="factory-prompts"><button disabled={busy} onClick={() => { chat('순찰 문제 보고서를 요약해줘'); setTab('Patrol') }}>문제 보고서</button><button disabled={busy} onClick={() => chat('현재 병목을 분석해줘')}>현재 병목은?</button><button disabled={busy} onClick={() => { chat('throughput을 최소 10% 개선해줘'); setTab('Experiments') }}>처리량 10% 개선</button></div>
        <form onSubmit={e => { e.preventDefault(); if (input.trim()) { chat(input.trim()); setInput('') } }}><input aria-label="Agent message" placeholder="ARIA에게 공장 분석·설계를 요청하세요…" value={input} onChange={e => setInput(e.target.value)} /><button className="primary" disabled={busy || !input.trim()}>Send</button></form>
      </section></div>
    <Approval />
  </div>
}
