// 통합 디지털트윈 HMI 셸 — KPI · 설정탭 · [계층 | 3D 뷰포트 | 인스펙터] · [메시지 | 차트].
import { useState, useEffect } from 'react'
import { ensureConnected } from './twinStore'
import KpiBar from './KpiBar'
import SettingsDrawer from './SettingsDrawer'
import HierarchyTree from './HierarchyTree'
import ViewportPanel from './ViewportPanel'
import InspectorContext from './InspectorContext'
import MessagePanel from './MessagePanel'
import ChartPanel from './ChartPanel'

export default function HmiShell() {
  const [selected, setSelected] = useState(null)
  useEffect(() => { ensureConnected() }, [])
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 8, padding: 8,
      background: '#0b0d12', boxSizing: 'border-box' }}>
      <KpiBar />
      <SettingsDrawer />
      <div style={{ flex: 1, minHeight: 0, display: 'grid', gridTemplateColumns: '162px 1fr 214px', gap: 8 }}>
        <HierarchyTree selected={selected} onSelect={setSelected} />
        <div style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.06)' }}>
          <ViewportPanel />
        </div>
        <InspectorContext selected={selected} />
      </div>
      <div style={{ height: 210, display: 'grid', gridTemplateColumns: '1fr 360px', gap: 8 }}>
        <MessagePanel />
        <ChartPanel />
      </div>
    </div>
  )
}
