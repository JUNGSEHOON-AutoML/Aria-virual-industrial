// 좌측 계층 트리 — Lines(mvtecScan) / Vision node / Twin I/O / MCP(fetchState). 선택 → 인스펙터 컨텍스트.
import { useState, useEffect } from 'react'
import { mvtecScan, fetchState } from '../api/apiClient'

export const DATA_ROOT = '/userHome/userhome4/sehoon/ARIArefactored/data'

function Group({ title, items, group, selected, onSelect }) {
  const [open, setOpen] = useState(true)
  return (
    <div style={{ marginBottom: 6 }}>
      <div onClick={() => setOpen(o => !o)} style={{ cursor: 'pointer', color: '#cbd5e1', fontSize: 12,
        display: 'flex', alignItems: 'center', gap: 5, padding: '3px 0' }}>
        <span style={{ color: '#6b7280', fontSize: 9 }}>{open ? '▼' : '▶'}</span>{title}
      </div>
      {open && items.map(it => {
        const active = selected?.group === group && selected?.id === it
        return (
          <div key={it} onClick={() => onSelect({ group, id: it })}
            style={{ cursor: 'pointer', fontSize: 12, padding: '2px 8px 2px 18px', borderRadius: 5,
              color: active ? '#1FB8CD' : '#9aa0aa', background: active ? 'rgba(31,184,205,0.12)' : 'transparent' }}>
            · {it}
          </div>
        )
      })}
      {open && items.length === 0 && <div style={{ fontSize: 11, color: '#4b5563', paddingLeft: 18 }}>—</div>}
    </div>
  )
}

export default function HierarchyTree({ selected, onSelect }) {
  const [lines, setLines] = useState([])
  const [mcp, setMcp] = useState([])
  useEffect(() => {
    mvtecScan(DATA_ROOT).then(r => { if (r?.ok) setLines(r.classes || []) }).catch(() => {})
    fetchState().then(s => setMcp((s?.mcp_servers || []).map(m => m.name))).catch(() => {})
  }, [])
  return (
    <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 10, padding: '10px 10px', height: '100%',
      overflowY: 'auto', fontFamily: "'Courier New', monospace" }}>
      <div style={{ fontSize: 10.5, color: '#6b7280', letterSpacing: 1, marginBottom: 8 }}>HIERARCHY</div>
      <Group title="Lines" items={lines} group="line" selected={selected} onSelect={onSelect} />
      <Group title="Vision node" items={['mock', 'patchcore', 'combined']} group="node" selected={selected} onSelect={onSelect} />
      <Group title="Twin I/O" items={['OPC UA', 'MQTT', '/ws floor']} group="twin" selected={selected} onSelect={onSelect} />
      <Group title="MCP nodes" items={mcp} group="mcp" selected={selected} onSelect={onSelect} />
    </div>
  )
}
