// 상단 KPI 바 — inspector_state(WS) + class_result(FAT) 바인딩.
import { useTwinSignal, useTwinStatus } from './useTwin'

function Chip({ label, value, tone = 'muted' }) {
  const colors = {
    muted: ['#9aa0aa', 'rgba(255,255,255,0.05)'],
    cyan: ['#1FB8CD', 'rgba(31,184,205,0.14)'],
    ok: ['#34d399', 'rgba(52,211,153,0.14)'],
    err: ['#f87171', 'rgba(248,113,113,0.14)'],
    warn: ['#facc15', 'rgba(250,204,21,0.14)'],
  }[tone] || ['#9aa0aa', 'rgba(255,255,255,0.05)']
  return (
    <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 6, padding: '4px 10px',
      borderRadius: 7, background: colors[1], fontFamily: "'Courier New', monospace", fontSize: 11.5 }}>
      <span style={{ color: '#6b7280', fontSize: 10, letterSpacing: 0.5 }}>{label}</span>
      <span style={{ color: colors[0], fontWeight: 700 }}>{value}</span>
    </span>
  )
}

export default function KpiBar() {
  const s = useTwinSignal('inspector_state') || {}
  const cls = useTwinSignal('class_result')
  const wsStatus = useTwinStatus()
  const fat = cls?.fat_verdict || s.fat_verdict
  const running = s.state === 'RUN'

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
      padding: '9px 14px', background: 'rgba(255,255,255,0.03)', borderRadius: 10 }}>
      <span style={{ fontFamily: "'Courier New', monospace", fontSize: 12.5, color: '#1FB8CD',
        fontWeight: 700, letterSpacing: 1, marginRight: 4 }}>ARIA · TWIN</span>
      <Chip label="STATE" value={s.state || 'IDLE'} tone={running ? 'ok' : 'muted'} />
      <Chip label="YIELD" value={`${((s.yield_rate ?? 0) * 100).toFixed(0)}%`} tone="cyan" />
      <Chip label="TACT" value={`${(s.tact_time_ms ?? 0).toFixed(0)}ms`} />
      <Chip label="ACK" value={`${(s.ack_max_ms ?? 0).toFixed(1)}ms`} tone={(s.ack_max_ms ?? 0) < 20 ? 'ok' : 'err'} />
      <Chip label="QUEUE" value={`${s.queue_depth ?? 0}`} tone={(s.queue_depth ?? 0) > 0 ? 'warn' : 'muted'} />
      <Chip label="DROP" value={`${s.drop_count ?? 0}`} tone={(s.drop_count ?? 0) > 0 ? 'err' : 'muted'} />
      <Chip label="OK/NG" value={`${s.n_ok ?? 0}/${s.n_ng ?? 0}`} />
      {fat && <Chip label="FAT" value={fat} tone={fat === 'PASS' ? 'ok' : 'err'} />}
      <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 5,
        fontFamily: "'Courier New', monospace", fontSize: 10, color: '#6b7280' }}>
        <span style={{ width: 7, height: 7, borderRadius: '50%',
          background: wsStatus === 'open' ? '#34d399' : '#f87171' }} />
        WS {wsStatus}
      </span>
    </div>
  )
}
