// 우측 컨텍스트 인스펙터 — 좌측 계층 선택에 따라 내용 전환.
//  line → 샘플/결과/학습 ·  node → 검사노드 제어+게이지 ·  twin → 연동 상태 ·  mcp → 도구.
import { useState, useEffect } from 'react'
import {
  classSamples, classTrain, classValidate,
  inspectorStart, inspectorStop, inspectorSetLatency,
} from '../api/apiClient'
import { useTwinSignal } from './useTwin'
import { DATA_ROOT } from './HierarchyTree'

const card = { background: 'rgba(255,255,255,0.03)', borderRadius: 10, padding: '12px', height: '100%',
  overflowY: 'auto', fontFamily: "'Courier New', monospace", color: '#cbd5e1' }
const head = { fontSize: 10.5, color: '#6b7280', letterSpacing: 1, marginBottom: 8 }
const btn = (tone) => ({ padding: '6px 10px', borderRadius: 6, cursor: 'pointer', fontSize: 11, border: '1px solid',
  borderColor: tone === 'go' ? 'rgba(52,211,153,0.5)' : tone === 'stop' ? 'rgba(248,113,113,0.5)' : 'rgba(31,184,205,0.4)',
  background: tone === 'go' ? 'rgba(52,211,153,0.12)' : tone === 'stop' ? 'rgba(248,113,113,0.12)' : 'rgba(31,184,205,0.1)',
  color: tone === 'go' ? '#34d399' : tone === 'stop' ? '#f87171' : '#1FB8CD' })

function Row({ k, v, c }) {
  return <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
    <span style={{ color: '#6b7280' }}>{k}</span><span style={{ color: c || '#e2e8f0' }}>{v}</span></div>
}

function LineContext({ classId }) {
  const [items, setItems] = useState([])
  const cls = useTwinSignal('class_result')
  const r = cls && cls.classId === classId ? cls : null
  useEffect(() => {
    setItems([])
    classSamples(classId, `${DATA_ROOT}/${classId}`).then(s => { if (s?.ok) setItems(s.items || []) }).catch(() => {})
  }, [classId])
  const path = `${DATA_ROOT}/${classId}`
  return (
    <>
      <div style={head}>LINE · {classId.toUpperCase()}</div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
        <button style={btn()} onClick={() => classTrain(classId, path)}>학습</button>
        <button style={btn()} onClick={() => classValidate(classId, path)}>판정</button>
      </div>
      {r && <div style={{ marginBottom: 10, fontSize: 11.5 }}>
        <Row k="verdict" v={r.fat_verdict || '—'} c={r.fat_verdict === 'PASS' ? '#34d399' : '#f87171'} />
        <Row k="escape" v={r.escape_rate != null ? `${(r.escape_rate * 100).toFixed(0)}%` : '—'} />
      </div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 4 }}>
        {items.slice(0, 9).map((it, i) => (
          <div key={i} style={{ position: 'relative' }}>
            <img src={it.url} alt="" style={{ width: '100%', height: 52, objectFit: 'cover', borderRadius: 4,
              border: `1px solid ${it.label === 'NG' ? '#f87171' : '#34d399'}` }} />
          </div>
        ))}
      </div>
    </>
  )
}

function NodeContext({ mode }) {
  const s = useTwinSignal('inspector_state') || {}
  const [category, setCategory] = useState('bottle')
  const [lineHz, setLineHz] = useState(20)
  const [lat, setLat] = useState(mode === 'mock' ? 40 : 0)
  const [running, setRunning] = useState(false)
  const [err, setErr] = useState(null)
  const isReal = mode !== 'mock'

  async function start() {
    setErr(null)
    const r = await inspectorStart({ mode, category, line_hz: lineHz, queue: 4,
      infer_ms: isReal ? 40 : lat, inflate_ms: isReal ? lat : 0, tau: 0.5 }).catch(e => ({ ok: false, error: String(e) }))
    if (r?.ok) setRunning(true); else setErr(r?.error || '시작 실패')
  }
  async function stop() { await inspectorStop().catch(() => {}); setRunning(false) }
  function onLat(v) {
    setLat(v)
    if (running) inspectorSetLatency(isReal ? { inflate_ms: v } : { infer_ms: v }).catch(() => {})
  }
  return (
    <>
      <div style={head}>VISION NODE · {mode.toUpperCase()}</div>
      {isReal && <input value={category} onChange={e => setCategory(e.target.value)} placeholder="category"
        style={{ width: '100%', padding: '5px 8px', borderRadius: 6, marginBottom: 8, fontSize: 11,
          background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', color: '#e2e8f0' }} />}
      <div style={{ fontSize: 10.5, color: '#9aa0aa' }}>라인 {lineHz} parts/s</div>
      <input type="range" min={2} max={50} value={lineHz} onChange={e => setLineHz(+e.target.value)} style={{ width: '100%' }} />
      <div style={{ fontSize: 10.5, color: '#9aa0aa', marginTop: 6 }}>
        {isReal ? '추가 지연(인위)' : '추론 지연(목)'}: <b style={{ color: '#facc15' }}>{lat}ms</b></div>
      <input type="range" min={0} max={isReal ? 1500 : 400} value={lat} onChange={e => onLat(+e.target.value)} style={{ width: '100%' }} />
      <button onClick={running ? stop : start} style={{ ...btn(running ? 'stop' : 'go'), width: '100%', marginTop: 10, fontWeight: 700 }}>
        {running ? '■ 노드 정지' : '▶ 노드 가동'}</button>
      {err && <div style={{ fontSize: 10.5, color: '#f87171', marginTop: 6 }}>{err}</div>}
      <div style={{ marginTop: 12, fontSize: 11.5 }}>
        <Row k="ack max" v={`${(s.ack_max_ms ?? 0).toFixed(1)}ms`} c={(s.ack_max_ms ?? 0) < 20 ? '#34d399' : '#f87171'} />
        <Row k="infer p95" v={`${(s.infer_latency_p95_ms ?? 0).toFixed(0)}ms`} c="#facc15" />
        <Row k="queue" v={`${s.queue_depth ?? 0}/4`} />
        <Row k="drop" v={`${s.drop_count ?? 0}`} c={(s.drop_count ?? 0) > 0 ? '#f87171' : '#e2e8f0'} />
        <Row k="OK / NG" v={`${s.n_ok ?? 0} / ${s.n_ng ?? 0}`} />
      </div>
    </>
  )
}

function InfoContext({ title, lines }) {
  return <><div style={head}>{title}</div>
    {lines.map((l, i) => <div key={i} style={{ fontSize: 11.5, color: '#9aa0aa', lineHeight: 1.7 }}>{l}</div>)}</>
}

export default function InspectorContext({ selected }) {
  let body
  if (!selected) body = <InfoContext title="INSPECTOR" lines={['좌측 계층에서 항목을 선택하세요.']} />
  else if (selected.group === 'line') body = <LineContext classId={selected.id} />
  else if (selected.group === 'node') body = <NodeContext mode={selected.id} />
  else if (selected.group === 'twin') body = <InfoContext title={`TWIN · ${selected.id}`}
    lines={['동일 텔레메트리 동시 송출.', 'OPC UA/MQTT 실연동:', 'pip install asyncua paho-mqtt', '/ws floor 는 항상 활성.']} />
  else body = <InfoContext title={`MCP · ${selected.id}`} lines={['MCP 서버 노드.', '도구 호출은 에이전트 경유.']} />
  return <div style={card}>{body}</div>
}
