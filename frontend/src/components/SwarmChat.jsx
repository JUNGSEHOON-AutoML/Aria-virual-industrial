/**
 * SwarmChat.jsx — ARIA Agent Live Terminal
 *
 * 주요 변경사항:
 * - 메시지 버블 → 터미널 라인 스타일 (term-line, term-prefix)
 * - agent 타입 메시지: Typewriter 효과 (글자 단위 렌더링)
 * - Human-in-the-Loop: 인라인 버튼 대신 ApprovalModal 팝업
 * - Quick Launch: 3개 커맨드 숏컷 (최하단)
 * - 연결 상태: 헤더 LIVE/OFFLINE 배지
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { Terminal, Wrench, Brain, AlertTriangle } from 'lucide-react'
import { getWebSocketUrl, sendChatHttp, sendAction } from '../api/apiClient'
import ApprovalModal from './ApprovalModal'

// ── Typewriter Hook ───────────────────────────────────────────────
function useTypewriter(text, speed = 18) {
  const [displayed, setDisplayed] = useState('')
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (!text) return
    setDisplayed('')
    setDone(false)
    let i = 0
    const id = setInterval(() => {
      i++
      setDisplayed(text.slice(0, i))
      if (i >= text.length) {
        clearInterval(id)
        setDone(true)
      }
    }, speed)
    return () => clearInterval(id)
  }, [text, speed])

  return { displayed, done }
}

// ── Terminal Line ─────────────────────────────────────────────────
function AgentLine({ text }) {
  const { displayed, done } = useTypewriter(text, 14)
  return (
    <div className="term-line type-agent animate-fade-in-up">
      <span className="term-prefix">▸ ARIA</span>
      <span className="term-content">
        {displayed}
        {!done && <span className="typewriter-cursor" />}
      </span>
    </div>
  )
}

function TermLine({ type, text }) {
  // agent 타입은 별도 처리
  if (type === 'agent') return <AgentLine text={text} />

  const prefixMap = {
    user:    '▸ USER',
    thought: '▸ THINK',
    tool:    '▸ MCP',
    error:   '▸ ERR',
    system:  '──────',
  }
  const prefix = prefixMap[type] || '▸'

  // URL markdown 파싱
  const parsed = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener" style="text-decoration:underline;color:var(--cyan)">$1 ↗</a>'
    )
    // fix double-escaped br from above
    .replace(/&lt;br&gt;/g, '<br>')

  return (
    <div className={`term-line type-${type} animate-fade-in-up`}>
      {type !== 'system' && (
        <span className="term-prefix">{prefix}</span>
      )}
      <span
        className="term-content"
        style={type === 'system' ? { textAlign: 'center', width: '100%' } : {}}
        dangerouslySetInnerHTML={{ __html: parsed }}
      />
    </div>
  )
}

// ── SwarmChat Main ────────────────────────────────────────────────
export default function SwarmChat({ onToolPulse, onAgentStatus, onTrainingUpdate }) {
  const [messages, setMessages] = useState([
    { id: 0, type: 'system', text: '── ARIA TERMINAL v2 ──' },
    { id: 1, type: 'system', text: '인터페이스 초기화 중...' },
  ])
  const [connected, setConnected]   = useState(false)
  const [oauthAlert, setOauthAlert] = useState(null)
  const [approvalModal, setApprovalModal] = useState({ open: false, action: '' })

  const socketRef         = useRef(null)
  const messagesEndRef    = useRef(null)
  const reconnectTimer    = useRef(null)
  // [LED 수정] stale closure 방지: 최신 onAgentStatus를 항상 ref로 접근
  const onAgentStatusRef  = useRef(onAgentStatus)
  useEffect(() => { onAgentStatusRef.current = onAgentStatus }, [onAgentStatus])

  const addMessage = useCallback((type, text) => {
    setMessages((prev) => [...prev, { id: Date.now() + Math.random(), type, text }])
  }, [])

  // ── WebSocket 연결 ────────────────────────────────────────────
  const connectWS = useCallback(() => {
    try {
      const ws = new WebSocket(getWebSocketUrl())
      socketRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        addMessage('system', '⚡ ARIA AI 인터페이스 연결 완료')
      }

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)

        if (data.source === 'analysis') {
          if (data.type === 'diagnostic_result') {
            addMessage('system', '🔬 분석 완료 — 우측 Diagnostic Report 참조')
          }
          if (data.type === 'agent_status') {
            onAgentStatusRef.current?.(data)
          }
          return
        }

        switch (data.type) {
          case 'thought':
            addMessage('thought', data.content)
            break
          case 'tool_start':
            addMessage('tool', `[${data.tool}] 호출 중...`)
            onToolPulse?.(data.tool, true)
            break
          case 'tool_end': {
            const snippet = (data.result || '').slice(0, 280)
            addMessage('tool', `[${data.tool}] 완료: ${snippet}`)
            onToolPulse?.(data.tool, false)
            break
          }
          case 'response':
            addMessage('agent', data.content)
            setOauthAlert(null)
            break
          case 'oauth_url':
            setOauthAlert({ server: data.server, url: data.url })
            addMessage('system', `⚠ ${data.server} OAuth 인증 필요`)
            break
          case 'agent_status':
            // [LED 수정] ref를 통해 항상 최신 onAgentStatus 함수 호출
            onAgentStatusRef.current?.(data)
            break
          case 'training':
            onTrainingUpdate?.(data)
            break
          default:
            break
        }
      }

      ws.onerror  = () => setConnected(false)
      ws.onclose  = () => {
        setConnected(false)
        reconnectTimer.current = setTimeout(connectWS, 5000)
      }
    } catch (_) {
      reconnectTimer.current = setTimeout(connectWS, 5000)
    }
  }, [addMessage, onToolPulse])

  useEffect(() => {
    connectWS()
    return () => {
      clearTimeout(reconnectTimer.current)
      socketRef.current?.close()
    }
  }, [connectWS])

  // 자동 스크롤
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── Approve / Stop ────────────────────────────────────────────
  const handleApproveClick = () => {
    setApprovalModal({ open: true, action: '에이전트 행동을 승인하시겠습니까?' })
  }
  const handleApprove = async () => {
    setApprovalModal({ open: false, action: '' })
    await sendAction('approve')
    addMessage('system', '✅ 에이전트 행동 승인됨')
  }
  const handleAbort = async () => {
    setApprovalModal({ open: false, action: '' })
  }
  const handleStop = async () => {
    await sendAction('emergency_stop')
    addMessage('system', '⛔ 긴급 정지 신호 전송됨')
  }

  return (
    <>
      <ApprovalModal
        open={approvalModal.open}
        action={approvalModal.action}
        onApprove={handleApprove}
        onAbort={handleAbort}
      />

      <div className="flex flex-col h-full min-h-0">
        {/* Header */}
        <div className="panel-header flex-shrink-0">
          <span className="panel-label">
            <Terminal size={11} style={{ color: 'var(--cyan)' }} />
            Activity Log
          </span>
          <div className="flex items-center gap-1.5">
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{
                background: connected ? 'var(--green)' : 'var(--red)',
                boxShadow: connected ? 'var(--glow-green)' : 'none',
                animation: connected ? 'pulse 2s infinite' : 'none',
              }}
            />
            <span
              className="text-[9px] font-black uppercase tracking-widest"
              style={{ color: connected ? 'var(--green)' : 'var(--red)' }}
            >
              {connected ? 'LIVE' : 'OFFLINE'}
            </span>
          </div>
        </div>

        {/* OAuth Banner */}
        {oauthAlert && (
          <div
            className="mx-3 mt-2 px-3 py-2 rounded-lg flex items-center justify-between gap-2 flex-shrink-0"
            style={{
              background: 'rgba(251,191,36,0.06)',
              border: '1px solid rgba(251,191,36,0.25)',
            }}
          >
            <span className="text-[10px] text-[var(--amber)]">
              ⚠ {oauthAlert.server} OAuth 필요
            </span>
            <a
              href={oauthAlert.url}
              target="_blank"
              rel="noopener noreferrer"
              className="px-2 py-1 rounded text-[9px] font-bold transition-colors"
              style={{
                background: 'rgba(251,191,36,0.12)',
                color: 'var(--amber)',
              }}
            >
              인증 →
            </a>
          </div>
        )}

        {/* Terminal Messages */}
        <div
          className="flex-1 min-h-0 overflow-y-auto px-3 py-3 flex flex-col gap-2"
          style={{ background: 'rgba(0,0,0,0.15)' }}
        >
          {messages.map((msg) => (
            <TermLine key={msg.id} type={msg.type} text={msg.text} />
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Control Buttons */}
        <div className="px-3 py-3 flex flex-col gap-2 flex-shrink-0 border-t" style={{ borderColor: 'rgba(63,63,70,0.3)' }}>
          <div className="flex gap-2">
            <button onClick={handleStop} className="btn-red flex-1 py-2">
              ⛔ Stop
            </button>
            <button onClick={handleApproveClick} className="btn-green flex-1 py-2">
              ✅ Approve
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
