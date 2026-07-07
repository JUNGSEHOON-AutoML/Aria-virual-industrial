// ActionBar — operator: 가동/정지·긴급정지(항상) / expert: +detector모드·클래스스캔.
// 터치 타깃 ≥44px (minHeight 설정).
import { useState, useEffect } from 'react'
import { Box, Typography, Button, Stack, ToggleButtonGroup, ToggleButton } from '@mui/material'
import { useSignalStore } from '../signalStore'
import { useUiMode } from '../uiMode'

export default function ActionBar() {
  const startNode = useSignalStore(s => s.startNode)
  const stopNode = useSignalStore(s => s.stopNode)
  const startLanes = useSignalStore(s => s.startLanes)
  const stopLanes = useSignalStore(s => s.stopLanes)
  const loadClasses = useSignalStore(s => s.loadClasses)
  const action = useSignalStore(s => s.action)
  // 기본 = combined(PatchCore 이상탐지 + YOLO 결함분류, GPU). mock/patchcore는 expert에서 선택.
  const [det, setDet] = useState('combined')
  const [running, setRunning] = useState(false)
  const [err, setErr] = useState(null)
  const uiMode = useUiMode()
  const isExpert = uiMode === 'expert'
  const classReady = !!useSignalStore(s => s.trained)?.bottle?.ready   // F2: 현재 클래스 준비 여부
  const replayActive = useSignalStore(s => s.replay.active)            // 리플레이 중 액션 비활성
  const nodeState = useSignalStore(s => s.kpi?.state)                  // 백엔드 가동 상태

  // 검사 완료/정지(백엔드) 시 가동 버튼 자동 리셋
  useEffect(() => {
    const st = String(nodeState || '').toLowerCase()
    if (st === 'done' || st === 'idle' || st === 'stopped') setRunning(false)
  }, [nodeState])

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

  const [lanesOn, setLanesOn] = useState(false)
  const startMulti = async () => {
    setErr(null)
    const r = await startLanes({ mode: det, lane_count: 3, line_hz: det === 'mock' ? 12 : 5, tau: 0.5 })
      .catch(e => ({ ok: false, error: String(e) }))
    if (r?.ok) setLanesOn(true); else setErr(r?.error || '멀티레인 시작 실패')
  }
  const stopMulti = async () => { await stopLanes().catch(() => {}); setLanesOn(false) }

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

      {/* F2: 현재 클래스 학습 완료 배지 */}
      <Typography sx={{ fontSize: 10, mb: 0.6,
        color: classReady ? '#34d399' : '#facc15', fontFamily: "'Courier New', monospace" }}>
        bottle · {classReady ? '✓ 학습 완료(검사 준비됨)' : '⌛ 미학습 — 먼저 학습 필요'}
      </Typography>

      {replayActive && (
        <Typography sx={{ fontSize: 10, mb: 0.6, color: '#1FB8CD',
          fontFamily: "'Courier New', monospace" }}>
          ⏪ 리플레이 중 — 액션 비활성(읽기 전용)
        </Typography>
      )}

      <Stack spacing={0.8}>
        <Button size="small" variant="outlined" disabled={replayActive || lanesOn}
          color={running ? 'error' : 'success'}
          onClick={running ? stop : start}
          sx={{ minHeight: 44, fontSize: 11 }}>
          {running ? '■ 노드 정지' : '▶ 단일 가동'}
        </Button>

        {/* 멀티레인(3) — 레인별 다른 클래스, 끝나면 다음 클래스 자동 */}
        <Button size="small" variant={lanesOn ? 'contained' : 'outlined'} disabled={replayActive || running}
          color={lanesOn ? 'error' : 'primary'}
          onClick={lanesOn ? stopMulti : startMulti}
          sx={{ minHeight: 44, fontSize: 11, fontWeight: 700 }}>
          {lanesOn ? '■ 멀티레인 정지' : '▶ 멀티레인 가동 (3)'}
        </Button>

        {/* 클래스 스캔 — expert만 */}
        {isExpert && (
          <Button size="small" variant="outlined" onClick={loadClasses}
            sx={{ minHeight: 36 }}>
            클래스 스캔
          </Button>
        )}

        {/* 긴급 정지 (리플레이 중 비활성) */}
        <Button size="small" variant="outlined" color="error" onClick={emergency} disabled={replayActive}
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
