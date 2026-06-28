/**
 * Dashboard.jsx — ARIA Bento Box 관제 콘솔
 *
 * 레이아웃: 3-column responsive CSS Grid
 *   Left  (220px) : MCP Nodes + Quick Actions
 *   Center (1fr)  : Vision HUD + Diagnostic Report
 *   Right  (320px): Agent Live Terminal
 */

import { useState, useEffect, useCallback } from 'react'
import { fetchState, sendAction, fetchAgentsStatus } from '../api/apiClient'
import SwarmChat from './SwarmChat'
import InspectionViewer from './InspectionViewer'
import AgentSwarm from './AgentSwarm'
import TrainingViewer from './TrainingViewer'
import HardwarePanel from './HardwarePanel'

// ── MCP 서버 노드 ─────────────────────────────────────────────────
const MCP_COLORS = {
  filesystem: '#38bdf8',
  system:     '#4ade80',
  database:   '#a78bfa',
  huggingface:'#fb923c',
}

function McpNode({ server, isActive }) {
  const color = MCP_COLORS[server.name] || '#52525b'
  return (
    <div className={`mcp-node ${isActive ? 'active' : ''}`}>
      {/* Status LED */}
      <span
        className="w-1.5 h-1.5 rounded-full shrink-0 transition-all"
        style={{
          background: server.enabled ? color : '#3f3f46',
          boxShadow: server.enabled && isActive ? `0 0 8px ${color}` : 'none',
        }}
      />
      {/* Name */}
      <span
        className="font-mono text-[10px] flex-1 truncate"
        style={{ color: server.enabled ? 'var(--text-secondary)' : 'var(--text-muted)' }}
      >
        {server.name}
      </span>
      {/* Tool count */}
      {server.tools && (
        <span className="text-[9px] font-mono text-[var(--text-muted)]">
          {server.tools.length}T
        </span>
      )}
      {/* Status */}
      <span
        className="text-[8px] font-black uppercase tracking-wider px-1.5 py-0.5 rounded"
        style={server.enabled
          ? { color: '#4ade80', background: 'rgba(74,222,128,0.08)' }
          : { color: '#fbbf24', background: 'rgba(251,191,36,0.08)' }
        }
      >
        {server.enabled ? 'ON' : 'OFF'}
      </span>
    </div>
  )
}

// ── Header ────────────────────────────────────────────────────────
function Header({ status, clock }) {
  const BADGE = {
    normal:  { cls: 'text-[#4ade80] border-[rgba(74,222,128,0.3)]',  bg: 'rgba(74,222,128,0.06)' },
    anomaly: { cls: 'text-[#f87171] border-[rgba(248,113,113,0.35)]', bg: 'rgba(248,113,113,0.08)' },
    idle:    { cls: 'text-[#a1a1aa] border-[rgba(161,161,170,0.2)]',  bg: 'transparent' },
    stopped: { cls: 'text-[#fbbf24] border-[rgba(251,191,36,0.3)]',  bg: 'rgba(251,191,36,0.06)' },
  }
  const badge = BADGE[status] || BADGE.idle

  return (
    <header
      className="flex-shrink-0 flex items-center justify-between px-5"
      style={{
        height: '52px',
        background: 'rgba(9,9,11,0.9)',
        borderBottom: '1px solid rgba(63,63,70,0.4)',
        backdropFilter: 'blur(16px)',
        zIndex: 50,
        position: 'relative',
      }}
    >
      {/* Logo */}
      <div className="flex items-center gap-3">
        <img
          src="/static/images/aria_logo.png"
          alt="ARIA"
          className="w-7 h-7 object-contain rounded-lg"
          style={{ filter: 'drop-shadow(0 0 6px rgba(56,189,248,0.4))' }}
        />
        <div>
          <div
            className="font-black text-sm tracking-[0.08em]"
            style={{
              background: 'linear-gradient(135deg, #38bdf8 25%, #a78bfa)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}
          >
            ARIA
          </div>
          <div className="text-[8px] font-mono uppercase tracking-[0.15em] text-[var(--text-muted)] -mt-0.5">
            Anomaly Reasoning Intelligence Agent
          </div>
        </div>
      </div>

      {/* Right: clock + status */}
      <div className="flex items-center gap-5">
        <span
          className="font-mono text-[13px] font-semibold tracking-wider"
          style={{ color: 'var(--cyan)', textShadow: '0 0 10px rgba(56,189,248,0.35)' }}
        >
          {clock}
        </span>
        <span
          className={`status-badge ${badge.cls}`}
          style={{ background: badge.bg }}
        >
          <span className={`status-dot ${status === 'anomaly' ? 'animate-pulse' : ''}`} />
          {(status || 'IDLE').toUpperCase()}
        </span>
      </div>
    </header>
  )
}

// ── Dashboard Main ────────────────────────────────────────────────
export default function Dashboard() {
  const [clock, setClock]       = useState('--:--:--')
  const [status, setStatus]     = useState('idle')
  const [beaconState, setBeaconState] = useState('idle')
  const [mcpServers, setMcpServers] = useState([])
  const [activeTool, setActiveTool] = useState(null)
  const [training, setTraining]     = useState(null)
  const [mcpLoaded, setMcpLoaded]   = useState(false)
  const [agents, setAgents] = useState({
    router:      { state: 'idle', detail: '대기 중' },
    vision:      { state: 'idle', detail: '대기 중' },
    // [§3 LED] 스카웃/토론/탐지기 쳩은 이미지 분석 시만 활성화
    scout:       { state: 'idle', detail: '대기 중' },
    detector:    { state: 'idle', detail: '대기 중' },
    debate:      { state: 'idle', detail: '대기 중' },
    research:    { state: 'idle', detail: '대기 중' },
    code:        { state: 'idle', detail: '대기 중' },
    verifier:    { state: 'idle', detail: '대기 중' },
    synthesizer: { state: 'idle', detail: '대기 중' }
  })

  // 시계
  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString('ko-KR', { hour12: false }))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  // 상태 폴링 (2초)
  useEffect(() => {
    const poll = async () => {
      try {
        const data = await fetchState()
        setStatus(data.agent?.status || 'idle')
        if (data.mcp_servers) setMcpServers(data.mcp_servers)
        setMcpLoaded(true)
      } catch (_) {
        setMcpLoaded(true)
      }
    }
    poll()
    const id = setInterval(poll, 2000)
    return () => clearInterval(id)
  }, [])

  // 초기 에이전트 상태 복원
  useEffect(() => {
    const loadInitialStatus = async () => {
      try {
        const data = await fetchAgentsStatus()
        setAgents(prev => ({
          ...prev,
          ...data
        }))
      } catch (err) {
        console.error("Failed to load initial agent status:", err)
      }
    }
    loadInitialStatus()
  }, [])

  const handleAgentStatus = useCallback((data) => {
    const { agent, state, detail } = data
    // [§3] agent가 미등록 키여도 스프레드로 자동 추가
    setAgents(prev => ({
      ...prev,
      [agent]: { state, detail }
    }))

    if (state === 'ok') {
      setTimeout(() => {
        setAgents(prev => {
          if (prev[agent]?.state === 'ok') {
            return {
              ...prev,
              [agent]: { ...prev[agent], state: 'idle' }
            }
          }
          return prev
        })
      }, 3000)
    }
  }, [])

  const handleToolPulse = useCallback((tool, isActive) => {
    setActiveTool(isActive ? tool : null)
  }, [])

  const handleDiagnosticUpdate = useCallback((data) => {
    if (!data || Object.keys(data).length === 0 || data.status === 'idle') {
      setBeaconState('idle')
      setStatus('idle')
      return
    }

    if (data.status === 'inspecting') {
      setBeaconState('inspecting')
      setStatus('idle')
      return
    }

    const isContent = data.status === 'content' || data.image_domain === 'general_object'
    if (isContent) {
      setBeaconState('content')
      setStatus('normal')
    } else {
      const isAnomaly = data.status === 'anomaly' || data.status === 'detected' || data.status === 'fail' || data.verdict === 'fail'
      if (isAnomaly) {
        setBeaconState('fail')
        setStatus('anomaly')
      } else {
        setBeaconState('pass')
        setStatus('normal')
      }
    }
  }, [])


  // ── §4 Quick Actions 상태 + 핸들러 ───────────────────────────────
  const [qaModal, setQaModal] = useState(null) // { title, content }

  const handleHistory = useCallback(async () => {
    setQaModal({ title: '📊 검사 이력 조회', content: '불러오는 중...' })
    try {
      const res = await fetch('/api/history?limit=10')
      if (!res.ok) throw new Error('API 응답 오류')
      const data = await res.json()
      const rows = (data.history || data || []).map((h, i) =>
        `#${i+1} [${h.domain_type || 'N/A'}] score=${h.score?.toFixed(3) ?? 'N/A'} — ${h.heatmap_url || ''}`
      ).join('\n')
      setQaModal({ title: '📊 최근 검사 이력 (최대 10건)', content: rows || '이력 없음' })
    } catch (e) {
      setQaModal({ title: '오류', content: `조회 실패: ${e.message}` })
    }
  }, [])


  return (
    <div
      className={`flex flex-col ${beaconState === 'fail' ? 'dashboard--alarm' : ''}`}
      style={{ height: '100dvh', overflow: 'hidden', position: 'relative', zIndex: 1 }}
    >
      <Header status={status} clock={clock} />

      {/* ── Bento Grid ── */}
      <main
        className="flex-1 min-h-0 p-2.5 gap-2.5"
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(180px, 220px) 1fr minmax(280px, 320px)',
          overflow: 'hidden',
        }}
      >
        {/* ── LEFT: MCP Nodes + System Info ── */}
        <aside className="flex flex-col gap-2.5 min-h-0 overflow-y-auto scrollbar-none">

          {/* MCP Nodes */}
          <div className="glass-panel flex flex-col flex-1 min-h-0">
            <div className="panel-header flex-shrink-0">
              <span className="panel-label">
                <span style={{ color: 'var(--cyan)' }}>◈</span>
                MCP Nodes
              </span>
              <span
                className="text-[8px] font-black uppercase tracking-widest flex items-center gap-1"
                style={{ color: '#4ade80' }}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                LIVE
              </span>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto p-2 flex flex-col gap-1.5 scrollbar-none">
              {mcpServers.length > 0 ? (
                mcpServers.map((s) => (
                  <McpNode
                    key={s.name}
                    server={s}
                    isActive={activeTool?.includes(s.name)}
                  />
                ))
              ) : (
                <div className="text-center text-[10px] font-mono text-[var(--text-muted)] py-6">
                  {mcpLoaded ? '연결된 MCP 노드 없음' : 'Initializing nodes...'}
                </div>
              )}
            </div>
          </div>

          {/* Hardware Telemetry Panel */}
          <HardwarePanel />

          {/* Agent Swarm Monitor */}
          <AgentSwarm agents={agents} />

          {/* Quick Action Shortcuts — §4 onClick 배선 */}
          <div className="glass-panel flex-shrink-0">
            <div className="panel-header">
              <span className="panel-label">
                <span style={{ color: 'var(--amber)' }}>⚡</span>
                Quick Actions
              </span>
            </div>
            <div className="p-2.5 flex flex-col gap-2">
              {[
                { label: '📊 검사 이력 조회',          color: 'var(--violet)', onClick: handleHistory },
              ].map(({ label, color, onClick }) => (
                <button
                  key={label}
                  onClick={onClick}
                  className="w-full text-left px-3 py-2 rounded-lg border text-[10px] font-mono
                             transition-all hover:-translate-y-px cursor-pointer"
                  style={{
                    borderColor: 'rgba(63,63,70,0.4)',
                    background: 'rgba(0,0,0,0.15)',
                    color: 'var(--text-muted)',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = color + '40'
                    e.currentTarget.style.color = color
                    e.currentTarget.style.background = color + '0a'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = 'rgba(63,63,70,0.4)'
                    e.currentTarget.style.color = 'var(--text-muted)'
                    e.currentTarget.style.background = 'rgba(0,0,0,0.15)'
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </aside>

        {/* §4 결과 모달 */}
        {qaModal && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center"
            style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(6px)' }}
            onClick={() => setQaModal(null)}
          >
            <div
              className="glass-panel max-w-lg w-full mx-4 p-5"
              style={{ maxHeight: '70vh', overflowY: 'auto' }}
              onClick={e => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-[13px] font-bold text-[var(--text-primary)] font-mono">{qaModal.title}</span>
                <button
                  onClick={() => setQaModal(null)}
                  className="text-[var(--text-muted)] hover:text-white text-xl leading-none"
                >×</button>
              </div>
              <pre className="text-[10px] font-mono text-[var(--text-secondary)] whitespace-pre-wrap break-all leading-relaxed">
                {qaModal.content}
              </pre>
            </div>
          </div>
        )}


        {/* ── CENTER: Vision HUD ── */}
        <section className="min-h-0 flex flex-col overflow-hidden">
          <TrainingViewer training={training} />
          <InspectionViewer
            beaconState={beaconState}
            onDiagnosticUpdate={handleDiagnosticUpdate}
            onAgentStatus={handleAgentStatus}
          />
        </section>

        {/* ── RIGHT: Agent Live Terminal ── */}
        <aside className="glass-panel min-h-0 flex flex-col overflow-hidden">
          <SwarmChat onToolPulse={handleToolPulse} onAgentStatus={handleAgentStatus} onTrainingUpdate={setTraining} />
        </aside>
      </main>
    </div>
  )
}
