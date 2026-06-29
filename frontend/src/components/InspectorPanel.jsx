import { useState, useEffect, useRef } from 'react'
import {
  getWebSocketUrl, inspectorStart, inspectorStop, inspectorSetLatency, inspectorState,
} from '../api/apiClient'

const C = '#1FB8CD'
const SLA_MS = 20

function Gauge({ label, value, max, unit = '', color = C, warn = false }) {
  const pct = max ? Math.min(100, (value / max) * 100) : 0
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#9aa0aa', marginBottom: 3 }}>
        <span>{label}</span>
        <span style={{ color: warn ? '#f87171' : '#e2e8f0', fontFamily: 'monospace' }}>
          {value}{unit}{max ? ` / ${max}${unit}` : ''}
        </span>
      </div>
      <div style={{ height: 8, background: 'rgba(255,255,255,0.06)', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: warn ? '#f87171' : color, transition: 'width 0.2s' }} />
      </div>
    </div>
  )
}

function Stat({ label, value, color = '#e2e8f0' }) {
  return (
    <div style={{ flex: 1, textAlign: 'center', padding: '8px 4px', background: 'rgba(255,255,255,0.03)', borderRadius: 6 }}>
      <div style={{ fontSize: 18, fontWeight: 700, color, fontFamily: 'monospace' }}>{value}</div>
      <div style={{ fontSize: 10, color: '#6b7280', letterSpacing: 1 }}>{label}</div>
    </div>
  )
}

export default function InspectorPanel() {
  const [mode, setMode] = useState('mock')
  const [category, setCategory] = useState('bottle')
  const [lineHz, setLineHz] = useState(20)
  const [queueCap] = useState(4)
  const [inferMs, setInferMs] = useState(40)      // mock 추론 지연
  const [inflateMs, setInflateMs] = useState(0)   // patchcore 추가 지연
  const [running, setRunning] = useState(false)
  const [snap, setSnap] = useState(null)
  const [results, setResults] = useState([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const latencyTimer = useRef(null)

  // WS 수신
  useEffect(() => {
    let ws
    try {
      ws = new WebSocket(getWebSocketUrl())
      ws.onmessage = (e) => {
        try {
          const d = JSON.parse(e.data)
          if (d.type === 'inspector_state') {
            setSnap(d)
          } else if (d.type === 'inspector_result') {
            setResults(prev => [d, ...prev].slice(0, 30))
          }
        } catch {}
      }
    } catch {}
    return () => { try { ws && ws.close() } catch {} }
  }, [])

  // 마운트 시 가동 상태 동기화
  useEffect(() => {
    inspectorState().then(s => { if (s?.running) { setRunning(true); setMode(s.mode); setCategory(s.category) } }).catch(() => {})
  }, [])

  async function start() {
    setBusy(true); setErr(null)
    try {
      const r = await inspectorStart({ mode, category, line_hz: lineHz, queue: queueCap,
        infer_ms: inferMs, inflate_ms: inflateMs, tau: 0.5 })
      if (r?.ok) { setRunning(true); setResults([]) }
      else setErr(r?.error || '시작 실패')
    } catch (e) { setErr(String(e)) }
    setBusy(false)
  }
  async function stop() {
    setBusy(true)
    try { await inspectorStop(); setRunning(false) } catch (e) { setErr(String(e)) }
    setBusy(false)
  }
  // 지연 슬라이더 → 디바운스 set_latency (라이브)
  const isReal = mode !== 'mock'
  function onLatency(v) {
    if (isReal) setInflateMs(v); else setInferMs(v)
    if (!running) return
    clearTimeout(latencyTimer.current)
    latencyTimer.current = setTimeout(() => {
      inspectorSetLatency(isReal ? { inflate_ms: v } : { infer_ms: v }).catch(() => {})
    }, 120)
  }

  const s = snap || {}
  const ackMax = s.ack_max_ms ?? 0
  const inferP95 = s.infer_latency_p95_ms ?? 0
  const ackWarn = ackMax >= SLA_MS
  const latVal = isReal ? inflateMs : inferMs
  const latLabel = isReal ? '추가 추론 지연(인위)' : '추론 지연(목)'
  const ngRecent = results.filter(r => r.verdict === 'NG').slice(0, 8)

  return (
    <div style={{ height: '100%', overflow: 'auto', padding: 20, background: '#0b0d12', color: '#e2e8f0',
      fontFamily: "'Courier New', monospace" }}>
      <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>

        {/* ── 좌: 제어 + 비병목 증거 ── */}
        <div style={{ flex: '1 1 420px', minWidth: 360 }}>
          <h2 style={{ fontSize: 14, letterSpacing: 2, color: C, marginTop: 0 }}>VISION INSPECTION NODE · 비병목 검사 노드</h2>

          {/* 제어 */}
          <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 10, padding: 14, marginBottom: 14 }}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
              {['mock', 'patchcore', 'combined'].map(m => (
                <button key={m} disabled={running} onClick={() => setMode(m)}
                  style={{ padding: '5px 12px', borderRadius: 6, cursor: running ? 'default' : 'pointer', fontSize: 11,
                    border: `1px solid ${mode === m ? 'rgba(31,184,205,0.5)' : 'rgba(255,255,255,0.1)'}`,
                    background: mode === m ? 'rgba(31,184,205,0.12)' : 'transparent',
                    color: mode === m ? C : '#6b7280', opacity: running ? 0.5 : 1 }}>
                  {m === 'mock' ? '목 추론(빠름)' : m === 'patchcore' ? '실 PatchCore' : 'PatchCore+YOLO'}
                </button>
              ))}
              {(mode === 'patchcore' || mode === 'combined') && (
                <input value={category} disabled={running} onChange={e => setCategory(e.target.value)}
                  placeholder="category(bottle)" style={{ width: 110, padding: '4px 8px', borderRadius: 6, fontSize: 11,
                    background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', color: '#e2e8f0' }} />
              )}
            </div>

            <div style={{ fontSize: 11, color: '#9aa0aa', marginBottom: 4 }}>
              라인 인입 {lineHz} parts/s
            </div>
            <input type="range" min={2} max={50} value={lineHz} disabled={running}
              onChange={e => setLineHz(Number(e.target.value))} style={{ width: '100%' }} />

            <div style={{ fontSize: 11, color: '#9aa0aa', margin: '8px 0 4px' }}>
              {latLabel}: <b style={{ color: '#facc15' }}>{latVal} ms</b>
              <span style={{ color: '#6b7280' }}> ← 올려도 ack는 평평해야 함</span>
            </div>
            <input type="range" min={0} max={isReal ? 1500 : 400} value={latVal}
              onChange={e => onLatency(Number(e.target.value))} style={{ width: '100%' }} />

            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button onClick={running ? stop : start} disabled={busy}
                style={{ flex: 1, padding: '8px', borderRadius: 8, cursor: 'pointer', fontSize: 12, fontWeight: 700,
                  border: `1px solid ${running ? 'rgba(248,113,113,0.5)' : 'rgba(52,211,153,0.5)'}`,
                  background: running ? 'rgba(248,113,113,0.12)' : 'rgba(52,211,153,0.12)',
                  color: running ? '#f87171' : '#34d399' }}>
                {busy ? '...' : running ? '■ 노드 정지' : '▶ 노드 가동'}
              </button>
            </div>
            {err && <div style={{ fontSize: 11, color: '#f87171', marginTop: 8 }}>{err}</div>}
          </div>

          {/* ★ 비병목 증거 */}
          <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 10, padding: 14 }}>
            <div style={{ fontSize: 12, color: C, letterSpacing: 1, marginBottom: 10 }}>★ 비병목 증거 (§10-1)</div>
            <Gauge label={`트리거 ack max (SLA ${SLA_MS}ms)`} value={ackMax} max={SLA_MS} unit="ms"
              color="#34d399" warn={ackWarn} />
            <Gauge label="추론 latency p95" value={inferP95} max={Math.max(SLA_MS, inferP95, 1)} unit="ms" color="#facc15" />
            <div style={{ fontSize: 10, color: '#6b7280', marginTop: 6, lineHeight: 1.5 }}>
              추론 지연을 올리면 p95는 치솟지만 <b style={{ color: '#34d399' }}>ack는 SLA 아래로 평평</b> 유지 ·
              과부하분은 <b style={{ color: '#f87171' }}>drop(SKIPPED)</b>으로 흡수되어 라인 미정지.
            </div>
          </div>
        </div>

        {/* ── 우: 게이지 + 결과 스트림 ── */}
        <div style={{ flex: '1 1 420px', minWidth: 360 }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
            <Stat label="STATE" value={s.state || (running ? 'RUN' : 'IDLE')} color={running ? '#34d399' : '#6b7280'} />
            <Stat label="YIELD" value={`${((s.yield_rate ?? 0) * 100).toFixed(0)}%`} color={C} />
            <Stat label="TACT" value={`${(s.tact_time_ms ?? 0).toFixed(0)}ms`} />
            <Stat label="TRIGGER" value={s.n_trigger ?? 0} />
          </div>

          <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 10, padding: 14, marginBottom: 14 }}>
            <Gauge label="QUEUE DEPTH" value={s.queue_depth ?? 0} max={queueCap} color={C}
              warn={(s.queue_depth ?? 0) >= queueCap} />
            <Gauge label="DROP COUNT (SKIPPED)" value={s.drop_count ?? 0}
              max={Math.max(10, s.drop_count ?? 0)} unit="" color="#f87171" warn={(s.drop_count ?? 0) > 0} />
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <Stat label="OK" value={s.n_ok ?? 0} color="#34d399" />
              <Stat label="NG" value={s.n_ng ?? 0} color="#f87171" />
              <Stat label="SKIPPED" value={s.n_skipped ?? 0} color="#facc15" />
            </div>
          </div>

          {/* 결과 스트림 + NG */}
          <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 10, padding: 14 }}>
            <div style={{ fontSize: 12, color: C, letterSpacing: 1, marginBottom: 8 }}>
              최근 결과 {ngRecent.length > 0 && <span style={{ color: '#f87171' }}>· NG {ngRecent.length}</span>}
            </div>
            <div style={{ maxHeight: 220, overflow: 'auto', fontSize: 11 }}>
              {results.length === 0 && <div style={{ color: '#6b7280' }}>가동하면 결과가 흐릅니다…</div>}
              {results.slice(0, 20).map((r, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 6, padding: '3px 6px',
                  borderBottom: '1px solid rgba(255,255,255,0.04)',
                  color: r.verdict === 'NG' ? '#f87171' : r.verdict === 'SKIPPED' ? '#facc15' : '#9aa0aa' }}>
                  <span style={{ flex: '0 0 70px' }}>{r.part_id}</span>
                  <span style={{ fontWeight: 700, flex: '0 0 36px' }}>{r.verdict}</span>
                  <span style={{ flex: '0 0 48px' }}>{r.score != null && r.score >= 0 ? r.score.toFixed(3) : '—'}</span>
                  <span style={{ flex: 1, color: '#fca5a5', fontSize: 10 }}>{r.defect_class || ''}</span>
                  <span style={{ color: '#6b7280', flex: '0 0 50px', textAlign: 'right' }}>{r.latency_ms != null ? `${r.latency_ms.toFixed(0)}ms` : ''}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
