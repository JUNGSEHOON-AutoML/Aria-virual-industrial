/**
 * ApprovalModal.jsx — Human-in-the-Loop 긴급 승인/거부 모달
 *
 * Props:
 *   open    {boolean}        — 모달 표시 여부
 *   action  {string}         — 승인 요청 액션 설명 (e.g. "에이전트 행동 승인")
 *   onApprove {() => void}   — 승인 콜백
 *   onAbort   {() => void}   — 거부/취소 콜백
 */

import { useEffect } from 'react'
import { ShieldAlert, CheckCircle2, OctagonX } from 'lucide-react'

export default function ApprovalModal({ open, action, onApprove, onAbort }) {
  // ESC 키로 닫기
  useEffect(() => {
    if (!open) return
    const handler = (e) => { if (e.key === 'Escape') onAbort() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onAbort])

  if (!open) return null

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onAbort() }}>
      <div className="modal-panel">
        {/* 헤더 */}
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-[rgba(251,191,36,0.1)] border border-[rgba(251,191,36,0.3)]">
            <ShieldAlert size={20} className="text-[var(--amber)]" />
          </div>
          <div>
            <div className="text-[11px] font-black uppercase tracking-widest text-[var(--amber)]">
              Human-in-the-Loop
            </div>
            <div className="text-[13px] font-bold text-[var(--text-primary)] mt-0.5">
              승인 요청
            </div>
          </div>
        </div>

        {/* 내용 */}
        <div className="rounded-xl p-4 border border-[rgba(251,191,36,0.15)] bg-[rgba(251,191,36,0.04)]">
          <div className="text-[11px] text-[var(--text-muted)] uppercase tracking-widest mb-1 font-bold">
            요청 내용
          </div>
          <div className="text-[13px] leading-snug text-[var(--text-secondary)]">
            {action || '에이전트가 중요 행동 실행 전 승인을 요청합니다.'}
          </div>
        </div>

        {/* 경고 */}
        <div className="text-[10px] text-[var(--text-muted)] text-center leading-relaxed">
          이 작업은 되돌릴 수 없을 수 있습니다. 신중하게 결정하세요.
        </div>

        {/* 버튼 */}
        <div className="flex gap-3">
          <button
            onClick={onAbort}
            className="btn-red flex-1 gap-2 py-2.5"
          >
            <OctagonX size={14} />
            <span>ABORT</span>
          </button>
          <button
            onClick={onApprove}
            className="btn-green flex-1 gap-2 py-2.5"
            style={{ fontWeight: 900 }}
          >
            <CheckCircle2 size={14} />
            <span>APPROVE</span>
          </button>
        </div>
      </div>
    </div>
  )
}
