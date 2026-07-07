// 설정 드로어(탭) — Model(인테이크/분석) · Visual · Interfaces · AI(에이전트/제어). 기존 API 재연결.
import { useState, useEffect } from 'react'
import { intakeDataset, analyzeImage, fetchAgentsStatus, sendAction } from '../api/apiClient'
import { useTwinStatus } from './useTwin'

const TABS = ['Model', 'Visual', 'Interfaces', 'AI']
const btn = { padding: '5px 10px', borderRadius: 6, cursor: 'pointer', fontSize: 11,
  border: '1px solid rgba(31,184,205,0.4)', background: 'rgba(31,184,205,0.1)', color: '#1FB8CD' }
const mono = { fontFamily: "'Courier New', monospace", color: '#cbd5e1' }

function ModelTab() {
  const [msg, setMsg] = useState('')
  async function onIntake(e) {
    const f = e.target.files?.[0]; if (!f) return
    setMsg('인테이크 중…')
    const r = await intakeDataset(f).catch(e => ({ error: String(e) }))
    setMsg(r?.error ? `오류: ${r.error}` : `도메인 ${r.domain || '?'} · ${r.n_images || 0}장 · ${(r.classes || []).length || ''}클래스`)
  }
  async function onAnalyze(e) {
    const f = e.target.files?.[0]; if (!f) return
    setMsg('분석 중…')
    const r = await analyzeImage(f, true).catch(e => ({ error: String(e) }))
    setMsg(r?.error ? `오류: ${r.error}` : `verdict ${r.verdict || r.status} · score ${r.score?.toFixed?.(3) ?? '?'}`)
  }
  return (
    <div style={{ fontSize: 11.5, ...mono }}>
      <label style={{ ...btn, display: 'inline-block', marginRight: 6 }}>데이터셋 인테이크
        <input type="file" accept=".zip,.tar,.gz" onChange={onIntake} style={{ display: 'none' }} /></label>
      <label style={{ ...btn, display: 'inline-block' }}>이미지 분석
        <input type="file" accept="image/*" onChange={onAnalyze} style={{ display: 'none' }} /></label>
      {msg && <div style={{ marginTop: 8, color: '#9aa0aa' }}>{msg}</div>}
    </div>
  )
}

function AiTab() {
  const [agents, setAgents] = useState({})
  useEffect(() => {
    let on = true
    const tick = () => fetchAgentsStatus().then(a => on && setAgents(a || {})).catch(() => {})
    tick(); const id = setInterval(tick, 2500); return () => { on = false; clearInterval(id) }
  }, [])
  const color = (st) => st === 'error' || st === 'idle' ? '#f87171' : st === 'done' || st === 'ok' ? '#34d399'
    : st === 'running' ? '#facc15' : '#6b7280'
  return (
    <div style={{ ...mono, fontSize: 11.5 }}>
      <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
        <button style={{ ...btn, borderColor: 'rgba(248,113,113,0.5)', background: 'rgba(248,113,113,0.12)', color: '#f87171' }}
          onClick={() => sendAction('emergency_stop')}>정지</button>
        <button style={{ ...btn, borderColor: 'rgba(52,211,153,0.5)', background: 'rgba(52,211,153,0.12)', color: '#34d399' }}
          onClick={() => sendAction('approve')}>승인</button>
        <button style={btn} onClick={() => sendAction('resume')}>재개</button>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {Object.entries(agents).map(([k, v]) => (
          <span key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 10.5,
            padding: '3px 8px', borderRadius: 5, background: 'rgba(255,255,255,0.04)' }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: color(v?.state) }} />{k}</span>
        ))}
        {Object.keys(agents).length === 0 && <span style={{ color: '#6b7280' }}>에이전트 상태 없음</span>}
      </div>
    </div>
  )
}

export default function SettingsDrawer() {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState('Model')
  const ws = useTwinStatus()
  return (
    <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 10, padding: '8px 12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {TABS.map(t => (
          <span key={t} onClick={() => { setTab(t); setOpen(true) }}
            style={{ fontSize: 11.5, padding: '4px 11px', borderRadius: 6, cursor: 'pointer', fontFamily: "'Courier New', monospace",
              color: tab === t && open ? '#1FB8CD' : '#6b7280',
              background: tab === t && open ? 'rgba(31,184,205,0.12)' : 'transparent' }}>{t}</span>
        ))}
        <span onClick={() => setOpen(o => !o)} style={{ marginLeft: 'auto', cursor: 'pointer', fontSize: 11,
          color: '#6b7280', fontFamily: "'Courier New', monospace" }}>{open ? '설정 ▲' : '설정 ▼'}</span>
      </div>
      {open && (
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
          {tab === 'Model' && <ModelTab />}
          {tab === 'Visual' && <div style={{ ...mono, fontSize: 11.5, color: '#9aa0aa' }}>도메인 랜덤화는 뷰포트/캡처 파이프라인에서 적용(part pose·조명). 범위는 sim/randomization.js.</div>}
          {tab === 'Interfaces' && <div style={{ ...mono, fontSize: 11.5, color: '#9aa0aa' }}>WS: {ws} · 내부 /ws floor 활성. 외부 OPC UA/MQTT 실연동은 `pip install asyncua paho-mqtt` 후 twin_bridge enable.</div>}
          {tab === 'AI' && <AiTab />}
        </div>
      )}
    </div>
  )
}
