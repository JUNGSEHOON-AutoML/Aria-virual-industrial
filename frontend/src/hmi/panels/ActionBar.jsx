// ActionBar — operator: 가동/정지·긴급정지(항상) / expert: +detector모드·클래스스캔.
// 터치 타깃 ≥44px (minHeight 설정).
import { useState } from 'react'
import { Box, Typography, Button, Stack, ToggleButtonGroup, ToggleButton } from '@mui/material'
import { useSignalStore } from '../signalStore'
import { useUiMode } from '../uiMode'

export default function ActionBar() {
  const startNode = useSignalStore(s => s.startNode)
  const stopNode = useSignalStore(s => s.stopNode)
  const loadClasses = useSignalStore(s => s.loadClasses)
  const action = useSignalStore(s => s.action)
  // 기본 = combined(PatchCore 이상탐지 + YOLO 결함분류, GPU). mock/patchcore는 expert에서 선택.
  const [det, setDet] = useState('combined')
  const [running, setRunning] = useState(false)
  const [err, setErr] = useState(null)
  const uiMode = useUiMode()
  const isExpert = uiMode === 'expert'

  const start = async () => {
    setErr(null)
    // patchcore는 추론 ~150ms라 라인 속도를 낮춰 과도 드롭 방지(mock은 20Hz)
    const isMock = det === 'mock'
    const r = await startNode({
      mode: det, category: 'bottle',
      line_hz: isMock ? 20 : 6, queue: 4, infer_ms: 40, inflate_ms: 0, tau: 0.5,
    }).catch(e => ({ ok: false, error: String(e) }))
    if (r?.ok) setRunning(true); else setErr(r?.error || '시작 실패')
  }
  const stop = async () => { await stopNode().catch(() => {}); setRunning(false) }
  const emergency = () => { action('emergency_stop'); setRunning(false) }

  return (
    <Box sx={{ height: '100%', p: 1, bgcolor: 'rgba(255,255,255,0.03)',
      borderRadius: 2, overflowY: 'auto' }}>
      {isExpert && (
        <Typography sx={{ fontSize: 9, color: '#6b7280', letterSpacing: 1, mb: 1,
          fontFamily: "'Courier New', monospace" }}>
          ACTIONS
        </Typography>
      )}

      {/* Detector 모드 — expert만 */}
      {isExpert && (
        <ToggleButtonGroup size="small" exclusive value={det}
          onChange={(_, v) => v && setDet(v)} sx={{ mb: 1 }}>
          {['mock', 'patchcore', 'combined'].map(m =>
            <ToggleButton key={m} value={m} sx={{ fontSize: 9, py: 0.2, px: 0.8 }}>{m}</ToggleButton>)}
        </ToggleButtonGroup>
      )}

      <Stack spacing={0.8}>
        <Button size="small" variant="outlined"
          color={running ? 'error' : 'success'}
          onClick={running ? stop : start}
          sx={{ minHeight: 44, fontSize: 11 }}>
          {running ? '■ 노드 정지' : '▶ 노드 가동'}
        </Button>

        {/* 클래스 스캔 — expert만 */}
        {isExpert && (
          <Button size="small" variant="outlined" onClick={loadClasses}
            sx={{ minHeight: 36 }}>
            클래스 스캔
          </Button>
        )}

        {/* 긴급 정지 — 항상 */}
        <Button size="small" variant="outlined" color="error" onClick={emergency}
          sx={{ minHeight: 44, fontSize: 11, fontWeight: 700 }}>
          ⛔ 긴급 정지
        </Button>
      </Stack>

      {err && (
        <Typography sx={{ fontSize: 10, color: '#f87171', mt: 1,
          fontFamily: "'Courier New', monospace" }}>
          {err}
        </Typography>
      )}
    </Box>
  )
}
