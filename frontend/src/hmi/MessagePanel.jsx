// 하단 메시지/알람 피드 — agent_status, training, inspector_result(NG 알람), class_result.
import { useTwinFeed } from './useTwin'

const TYPES = ['agent_status', 'training', 'inspector_result', 'class_result']

function mapMsg(d, t) {
  if (t === 'agent_status') {
    const kind = d.state === 'error' || d.state === 'idle' ? 'err' : d.state === 'done' ? 'ok' : 'info'
    return { kind, tag: (d.agent || 'AGENT').toUpperCase(), text: d.detail || d.state }
  }
  if (t === 'training') {
    return { kind: d.status === 'error' ? 'err' : d.status === 'done' ? 'ok' : 'info',
      tag: 'TRAIN', text: `${d.status} · ${d.step ?? ''}/${d.total_steps ?? ''}` }
  }
  if (t === 'inspector_result') {
    if (d.verdict === 'NG') return { kind: 'err', tag: 'ALARM', text: `${d.part_id} NG ${d.defect_class || ''}`.trim() }
    if (d.verdict === 'SKIPPED') return { kind: 'warn', tag: 'SKIP', text: `${d.part_id} (backpressure)` }
    return null  // OK 결과는 피드 안 쌓음(과다 방지)
  }
  if (t === 'class_result') return { kind: 'ok', tag: 'CLASS', text: `${d.classId} ${d.fat_verdict || ''}`.trim() }
  return null
}

const COLOR = { info: '#9aa0aa', ok: '#34d399', err: '#f87171', warn: '#facc15' }

export default function MessagePanel() {
  const feed = useTwinFeed(TYPES, mapMsg, 80)
  return (
    <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 10, padding: '8px 12px', height: '100%',
      display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ fontSize: 10.5, color: '#6b7280', letterSpacing: 1, marginBottom: 6, flexShrink: 0 }}>
        MESSAGES / ALARMS
      </div>
      <div style={{ overflowY: 'auto', fontFamily: "'Courier New', monospace", fontSize: 11.5, lineHeight: 1.75, flex: 1, minHeight: 0 }}>
        {feed.length === 0 && <div style={{ color: '#6b7280' }}>대기 중 — 가동하면 이벤트가 흐릅니다…</div>}
        {feed.map((m, i) => (
          <div key={i} style={{ display: 'flex', gap: 8 }}>
            <span style={{ color: COLOR[m.kind], flex: '0 0 64px', fontWeight: 700 }}>{m.tag}</span>
            <span style={{ color: '#cbd5e1', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.text}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
