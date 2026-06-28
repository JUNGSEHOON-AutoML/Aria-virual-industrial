import { useState } from 'react'
import Dashboard from './components/Dashboard'
import SimulationView from './components/SimulationView'

export default function App() {
  const [view, setView] = useState('simulation')

  const tab = (id, label, icon) => (
    <button
      id={`tab-${id}`}
      onClick={() => setView(id)}
      style={{
        padding: '6px 18px',
        fontFamily: "'Courier New', monospace",
        fontSize: 11,
        letterSpacing: 1.5,
        cursor: 'pointer',
        borderRadius: 6,
        border: '1px solid',
        borderColor: view === id ? 'rgba(31,184,205,0.45)' : 'rgba(255,255,255,0.07)',
        background: view === id
          ? 'rgba(31,184,205,0.10)'
          : 'rgba(255,255,255,0.02)',
        color: view === id ? '#1FB8CD' : '#6b7280',
        transition: 'all 0.18s ease',
        display: 'flex', alignItems: 'center', gap: 6,
        outline: 'none',
      }}
    >
      <span>{icon}</span>
      <span>{label}</span>
    </button>
  )

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: '#0b0d12' }}>
      {/* 상단 탭 네비게이션 */}
      <nav style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '7px 14px',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        background: 'rgba(11,13,18,0.95)',
        backdropFilter: 'blur(8px)',
        flexShrink: 0,
      }}>
        {tab('inspection', '검사', '🔍')}
        {tab('simulation', '시뮬레이션', '🧊')}
        <div style={{
          marginLeft: 'auto',
          fontSize: 10,
          letterSpacing: 1.5,
          color: 'rgba(154,160,170,0.4)',
          fontFamily: 'monospace',
        }}>
          ARIA · {view === 'simulation' ? 'SIM-4' : 'INSPECTION'}
        </div>
      </nav>

      {/* 뷰 컨텐츠 */}
      <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
        {view === 'simulation' ? <SimulationView /> : <Dashboard />}
      </div>
    </div>
  )
}
