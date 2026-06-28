import React from 'react'

/**
 * AgentSwarm — §3 LED 동적 확장 / §5 가독성 개선
 *
 * v4 §3: agents prop 키를 런타임에 읽어 칩 자동 생성.
 * - KNOWN_AGENTS 배열로 우선순위 순서(표시 순서) 지정.
 * - agents prop에 없는 KNOWN_AGENTS 항목은 idle 상태로 표시.
 * - agents prop에 있지만 KNOWN_AGENTS에 없는 키는 자동 칩으로 추가.
 * - scout / debate / detector 칩은 §2 escalation 경로에서 동적 등장.
 * v4 §5: 이름 잘림 제거, LED 크기 확대, 범례 추가.
 */

// 표시 순서 + 아이콘 정의 (여기에 없어도 자동 칩으로 렌더됨)
const KNOWN_AGENTS = [
  { key: 'router',      label: 'Router',      icon: '⚡' },
  { key: 'vision',      label: 'Vision',       icon: '👁' },
  { key: 'scout',       label: 'Scout',        icon: '🔭' },  // §3: VLM 전처리
  { key: 'detector',    label: 'Detector',     icon: '🎯' },  // §3: 채택 탐지기
  { key: 'debate',      label: 'Debate',       icon: '⚔️' },  // §3: Debate Path
  { key: 'research',    label: 'Research',     icon: '🔬' },
  { key: 'code',        label: 'Code',         icon: '💻' },
  { key: 'verifier',    label: 'Verifier',     icon: '✔️' },
  { key: 'synthesizer', label: 'Synthesizer',  icon: '✍' },
]

const KNOWN_KEYS = new Set(KNOWN_AGENTS.map(a => a.key))

const LED_STYLE = {
  running: 'bg-accent-amber animate-glow-pulse-amber lamp-running-glow shadow-[0_0_12px_rgba(251,191,36,0.65)]',
  ok:      'bg-accent-green shadow-[0_0_12px_rgba(74,222,128,0.7)]',
  error:   'bg-accent-red shadow-[0_0_16px_rgba(248,113,113,0.85)]',
  idle:    'bg-zinc-600',
}

// §5: 상태별 한국어 라벨
const LED_LABEL = { running: '실행 중', ok: '완료', error: '오류', idle: '대기' }

function getLedStyle(state) {
  return LED_STYLE[state] || LED_STYLE.idle
}

export default function AgentSwarm({ agents }) {
  // 1. KNOWN_AGENTS 순서대로 항목 구성 (agents에 없으면 idle)
  const orderedItems = KNOWN_AGENTS.map(({ key, label, icon }) => ({
    key,
    label,
    icon,
    status: agents[key] || { state: 'idle', detail: '대기 중' },
  }))

  // 2. agents에만 있고 KNOWN_AGENTS에 없는 미등록 에이전트 → 자동 칩
  const extraItems = Object.entries(agents)
    .filter(([k]) => !KNOWN_KEYS.has(k))
    .map(([k, v]) => ({
      key: k,
      label: k.charAt(0).toUpperCase() + k.slice(1),
      icon: '🤖',
      status: v || { state: 'idle', detail: '대기 중' },
    }))

  const allItems = [...orderedItems, ...extraItems]
  const activeCount = Object.values(agents).filter(a => a?.state === 'running').length

  return (
    <div className="glass-panel flex-shrink-0">
      <div className="panel-header">
        <span className="panel-label">
          <span style={{ color: 'var(--violet)' }}>◈</span>
          Agent Swarm Monitor
        </span>
        {activeCount > 0 && (
          <span className="text-[8px] font-mono text-accent-amber font-black">
            ⚡ {activeCount} ACTIVE
          </span>
        )}
      </div>

      {/* §5 범례 — 한눈에 상태 4종 구분 */}
      <div className="px-3 pt-2 pb-0 flex gap-3 flex-wrap border-b border-[rgba(63,63,70,0.2)]">
        {[
          ['idle',    'bg-zinc-600',    '대기'],
          ['running', 'bg-accent-amber','실행'],
          ['ok',      'bg-accent-green','완료'],
          ['error',   'bg-accent-red',  '오류'],
        ].map(([s, cls, lbl]) => (
          <span key={s} className="flex items-center gap-1 text-[8px] text-[var(--text-muted)] pb-2">
            <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${cls}`} />
            {lbl}
          </span>
        ))}
      </div>

      <div className="p-3 grid grid-cols-2 gap-2">
        {allItems.map(({ key, label, icon, status }) => {
          const state  = status?.state  || 'idle'
          const detail = status?.detail || '대기 중'
          const isRegistered = KNOWN_KEYS.has(key)
          const isPresent    = Boolean(agents[key])

          // KNOWN_AGENTS이지만 agents prop에 아직 없으면 반투명
          const opacity = (isRegistered && !isPresent) ? 0.35 : 1.0

          return (
            <div
              key={key}
              className="flex items-start gap-2 px-2.5 py-2 rounded-lg border border-[rgba(63,63,70,0.3)] bg-[rgba(0,0,0,0.15)] transition-all hover:border-[rgba(167,139,250,0.25)]"
              style={{ opacity }}
              title={`${label}: ${detail}`}
            >
              {/* §5 LED — 크기 w-2→w-3 h-2→h-3, 위쪽 정렬 */}
              <span className={`w-3 h-3 rounded-full shrink-0 mt-0.5 transition-all ${getLedStyle(state)}`} />

              {/* §5 Agent Label — truncate 제거, 2줄 허용 */}
              <div className="flex flex-col min-w-0 flex-1">
                <span className="text-[10px] font-bold text-[var(--text-primary)] font-mono uppercase tracking-wide leading-tight break-words">
                  {icon} {label}
                </span>
                <span className="text-[8px] text-[var(--text-muted)] capitalize mt-0.5">
                  {LED_LABEL[state] || state}
                </span>
              </div>

              {/* 미등록 자동 칩 배지 */}
              {!isRegistered && (
                <span className="text-[7px] font-black uppercase tracking-wider px-1 py-0.5 rounded shrink-0"
                  style={{ color: '#a78bfa', background: 'rgba(167,139,250,0.08)' }}>
                  NEW
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
