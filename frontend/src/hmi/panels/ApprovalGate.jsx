// ApprovalGate — Simulate-then-Approve 승인 모달. 명세 §4·A4.
// 에이전트가 가상 시연 후 권고한 실 액션을 운영자가 승인할 때만 /api 호출. 자동 실행 절대 금지.
import { Box, Typography, Button } from '@mui/material'
import { useSignalStore } from '../signalStore'

export default function ApprovalGate() {
  const approvals = useSignalStore(s => s.approvals) || []
  const resolveApproval = useSignalStore(s => s.resolveApproval)
  const logEpisode = useSignalStore(s => s.logEpisode)
  const action = useSignalStore(s => s.action)

  const pending = approvals.filter(a => a.status === 'pending')
  if (!pending.length) return null
  const ap = pending[0]   // 한 번에 하나씩

  const approve = async () => {
    // ★실 시스템 변경은 여기(승인) 뒤에서만 — request_real_action
    let result = 'sent'
    try { await action(ap.action) } catch { result = 'error' }
    resolveApproval(ap.id, 'approved')
    logEpisode({ ts: Date.now(), event: `approve ${ap.assetName}`, assetId: ap.assetId,
      action: ap.action, approval: 'approved', result })
  }
  const reject = () => {
    resolveApproval(ap.id, 'rejected')
    logEpisode({ ts: Date.now(), event: `reject ${ap.assetName}`, assetId: ap.assetId,
      action: ap.action, approval: 'rejected', result: 'skipped' })
  }

  return (
    <Box sx={{ position: 'absolute', bottom: 16, left: '50%', transform: 'translateX(-50%)',
      zIndex: 12, width: 'min(520px, 92%)', p: 1.6, borderRadius: 2,
      bgcolor: 'rgba(17,20,27,0.97)', border: '1px solid #facc15',
      boxShadow: '0 6px 24px rgba(0,0,0,0.5)', fontFamily: "'Courier New',monospace" }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.8 }}>
        <span style={{ color: '#facc15', fontSize: 15 }}>⚠</span>
        <Typography sx={{ fontSize: 12, color: '#facc15', letterSpacing: 0.5 }}>
          승인 게이트 — 실 시스템 액션 (운영자 승인 필요)
        </Typography>
      </Box>
      <Typography sx={{ fontSize: 12, color: '#e2e8f0', mb: 0.3 }}>
        에이전트 권고: <b style={{ color: '#1FB8CD' }}>{ap.assetName}</b> →{' '}
        <b style={{ color: '#facc15' }}>{ap.actionLabel}</b>
      </Typography>
      <Typography sx={{ fontSize: 10, color: '#6b7280', mb: 1.2 }}>
        {ap.kind === 'inspection'
          ? `점검/조치 실행 결정 — 원인 확정 아님(가설). 승인 시에만 실제 ${ap.action} 호출 (/api).`
          : `가상 트윈 수리 시연 완료. 승인 시에만 실제 ${ap.action} 호출 (/api). 미승인 시 미실행.`}
      </Typography>
      <Box sx={{ display: 'flex', gap: 1 }}>
        <Button size="small" variant="contained" color="success" onClick={approve}
          sx={{ flex: 1, minHeight: 42, fontWeight: 700 }}>✓ 승인 (실행)</Button>
        <Button size="small" variant="outlined" color="inherit" onClick={reject}
          sx={{ flex: 1, minHeight: 42 }}>✕ 거부</Button>
      </Box>
      {pending.length > 1 && (
        <Typography sx={{ fontSize: 9, color: '#6b7280', mt: 0.6 }}>
          대기 중 승인 {pending.length - 1}건 더
        </Typography>
      )}
    </Box>
  )
}
