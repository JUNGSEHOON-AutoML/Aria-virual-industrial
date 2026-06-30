// ReplayBar — ① 3D 리플레이 블랙박스 UI. 타임라인 스크럽 + play/pause/속도 + 이슈(NG) 점프.
// 데이터만 되먹여 기존 씬이 과거를 재생. 리플레이 중엔 읽기 전용(실 액션/승인 비활성).
import { useEffect, useRef } from 'react'
import { Box, Typography, IconButton, Button, Slider, Stack } from '@mui/material'
import { useSignalStore } from '../signalStore'

const fmt = (ms) => { const s = Math.max(0, Math.floor(ms / 1000)); return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}` }

export default function ReplayBar() {
  const replay = useSignalStore(s => s.replay)
  const startReplay = useSignalStore(s => s.startReplay)
  const stopReplay = useSignalStore(s => s.stopReplay)
  const replaySeek = useSignalStore(s => s.replaySeek)
  const replayPlay = useSignalStore(s => s.replayPlay)
  const replayPause = useSignalStore(s => s.replayPause)
  const replaySpeed = useSignalStore(s => s.replaySpeed)

  // 재생 루프 — playing이면 실시간×speed로 t 전진
  const raf = useRef(0); const last = useRef(0)
  useEffect(() => {
    if (!replay.active || !replay.playing) return
    last.current = performance.now()
    const tick = (now) => {
      const dt = now - last.current; last.current = now
      const st = useSignalStore.getState().replay
      const nt = st.t + dt * st.speed
      if (nt >= st.t1) { useSignalStore.getState().replaySeek(st.t1); useSignalStore.getState().replayPause(); return }
      useSignalStore.getState().replaySeek(nt)
      raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [replay.active, replay.playing])

  // 리플레이 비활성 → 작은 진입 버튼만
  if (!replay.active) {
    return (
      <Button size="small" variant="outlined" onClick={startReplay}
        sx={{ position: 'absolute', bottom: 12, left: 12, zIndex: 9, fontSize: 10, minHeight: 30,
          fontFamily: "'Courier New',monospace", color: '#1FB8CD', borderColor: '#1FB8CD55',
          bgcolor: 'rgba(10,14,22,0.7)' }}>
        ⏪ 리플레이(블랙박스)
      </Button>
    )
  }

  const dur = replay.t1 - replay.t0
  const rel = replay.t - replay.t0
  const SP = [1, 2, 4, 8]

  return (
    <Box sx={{ position: 'absolute', bottom: 10, left: '50%', transform: 'translateX(-50%)', zIndex: 11,
      width: 'min(680px, 94%)', px: 1.6, py: 1, borderRadius: 2,
      bgcolor: 'rgba(11,15,24,0.96)', border: '1px solid #1FB8CD', fontFamily: "'Courier New',monospace",
      boxShadow: '0 6px 24px rgba(0,0,0,0.5)' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.3 }}>
        <Typography sx={{ fontSize: 11, color: '#1FB8CD', letterSpacing: 0.5 }}>
          ⏪ 리플레이 — 읽기 전용 (과거 재구성)
        </Typography>
        <Typography sx={{ fontSize: 10, color: '#9aa0aa', ml: 'auto' }}>
          {fmt(rel)} / {fmt(dur)}
        </Typography>
      </Box>

      {/* 타임라인 + NG 마커 */}
      <Box sx={{ position: 'relative' }}>
        <Slider size="small" min={replay.t0} max={replay.t1} value={replay.t}
          onChange={(_, v) => replaySeek(v)}
          sx={{ color: '#1FB8CD', py: 1 }} />
        {replay.markers.map((m, i) => {
          const left = dur > 0 ? ((m.ts - replay.t0) / dur) * 100 : 0
          return (
            <Box key={i} title={m.label} onClick={() => replaySeek(m.ts)}
              sx={{ position: 'absolute', top: 2, left: `${left}%`, width: 6, height: 6, borderRadius: '50%',
                bgcolor: m.kind === 'NG' ? '#f87171' : '#facc15', cursor: 'pointer',
                transform: 'translateX(-3px)', boxShadow: '0 0 4px currentColor' }} />
          )
        })}
      </Box>

      <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.2 }}>
        <IconButton size="small" onClick={replay.playing ? replayPause : replayPlay}
          sx={{ color: '#e2e8f0' }}>
          <span style={{ fontSize: 14 }}>{replay.playing ? '⏸' : '▶'}</span>
        </IconButton>
        {SP.map(sp => (
          <Box key={sp} onClick={() => replaySpeed(sp)} sx={{ cursor: 'pointer', fontSize: 10, px: 0.6, py: 0.2,
            borderRadius: 1, color: replay.speed === sp ? '#1FB8CD' : '#6b7280',
            border: `1px solid ${replay.speed === sp ? '#1FB8CD' : 'transparent'}` }}>
            {sp}×
          </Box>
        ))}
        {/* NG 점프 */}
        <Button size="small" variant="text" sx={{ fontSize: 10, color: '#f87171', minHeight: 28 }}
          onClick={() => {
            const ngs = replay.markers.filter(m => m.kind === 'NG')
            const next = ngs.find(m => m.ts > replay.t) || ngs[0]
            if (next) replaySeek(next.ts)
          }}>
          ⟶ NG 점프 ({replay.markers.filter(m => m.kind === 'NG').length})
        </Button>
        <Button size="small" variant="outlined" color="inherit" onClick={stopReplay}
          sx={{ ml: 'auto', fontSize: 10, minHeight: 28 }}>
          ⏏ 라이브 복귀
        </Button>
      </Stack>
    </Box>
  )
}
