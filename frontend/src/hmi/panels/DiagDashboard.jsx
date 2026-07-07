// DiagDashboard — G4: 행동 유도 알람 드로어.
// error_code → action 매핑 테이블 (클라이언트 사이드, 새 엔드포인트 없음).
// 소스: inspector_result(NG) → alarms / diagnostic_result → messages.
import { useState } from 'react'
import { Box, Button, Chip, Divider, Drawer, Typography } from '@mui/material'
import { useSignalStore } from '../signalStore'

// error_code → { label, actionLabel, kind } 매핑
const CODE_MAP = {
  ALARM:      { label: '이상 검출 (NG)', actionLabel: '상세 보기', kind: 'detail' },
  SKIP:       { label: '백프레셔 스킵',   actionLabel: '큐 확인',   kind: 'info'   },
  CAM_CALIB:  { label: '카메라 교정 오류', actionLabel: '해결 매뉴얼', kind: 'manual' },
  ROBOT_SYNC: { label: '로봇 동기화 오류', actionLabel: '재시작',    kind: 'restart' },
  NG_SCORE:   { label: '이상 검출(NG)',   actionLabel: '히트맵 보기', kind: 'detail' },
}

// 알람 객체 → 구조화된 표시 정보. BottomPanel AlarmTicker에서도 import.
export function parseAlarm(a) {
  const code = a.tag || 'ALARM'
  const mapped = CODE_MAP[code] || { label: a.text || code, actionLabel: '—', kind: 'info' }
  const textParts = (a.text || '').split(' ')
  return {
    ...mapped,
    partId: textParts[0] || '—',
    errorCode: code,
    ts: a.ts,
    raw: a.text,
  }
}

export function DiagDashboardButton() {
  const [open, setOpen] = useState(false)
  const alarms = useSignalStore(s => s.alarms)
  const action = useSignalStore(s => s.action)
  const active = (alarms || []).filter(a => a.level === 'error').length

  return (
    <>
      <Button size="small" variant="outlined"
        color={active > 0 ? 'error' : 'inherit'}
        onClick={() => setOpen(true)}
        sx={{ fontSize: 9, py: 0.3, px: 1, minHeight: 28, whiteSpace: 'nowrap',
          fontFamily: "'Courier New', monospace", letterSpacing: 0.5 }}>
        {active > 0 ? `⚠ 문제 해결 (${active})` : '문제 해결 대시보드'}
      </Button>

      <Drawer anchor="bottom" open={open} onClose={() => setOpen(false)}
        PaperProps={{ sx: { bgcolor: '#11141b', p: 2, maxHeight: '60vh',
          borderRadius: '12px 12px 0 0' } }}>
        <Box sx={{ overflowY: 'auto', flex: 1 }}>
          <Typography sx={{ fontSize: 13, color: '#1FB8CD', mb: 1.5,
            fontFamily: "'Courier New', monospace", letterSpacing: 1 }}>
            ⚠ 문제 해결 대시보드
          </Typography>

          {(alarms || []).length === 0 ? (
            <Typography sx={{ fontSize: 12, color: '#34d399' }}>✓ 활성 결함 없음</Typography>
          ) : (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.8 }}>
              {(alarms || []).slice(0, 20).map((a, i) => {
                const p = parseAlarm(a)
                const isErr = a.level === 'error'
                return (
                  <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 1.5,
                    px: 1.2, py: 0.9, borderRadius: 1.5,
                    bgcolor: 'rgba(255,255,255,0.03)',
                    border: `1px solid ${isErr ? 'rgba(248,113,113,0.22)' : 'rgba(255,255,255,0.07)'}` }}>
                    <Chip size="small" label={p.errorCode} variant="outlined"
                      color={isErr ? 'error' : 'default'}
                      sx={{ fontSize: 9, height: 20, flexShrink: 0 }} />
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography sx={{ fontSize: 11, color: isErr ? '#f87171' : '#9aa0aa',
                        fontFamily: "'Courier New', monospace" }}>
                        {p.label}
                      </Typography>
                      <Typography sx={{ fontSize: 10, color: '#6b7280' }}>
                        {p.partId} · {new Date(p.ts).toLocaleTimeString()}
                      </Typography>
                    </Box>
                    <Button size="small" variant="text"
                      color={isErr ? 'error' : 'inherit'}
                      sx={{ fontSize: 9, py: 0.2, px: 0.8, minHeight: 28, flexShrink: 0,
                        fontFamily: "'Courier New', monospace" }}
                      onClick={() => {
                        if (p.kind === 'restart') action('inspector_restart')
                        setOpen(false)
                      }}>
                      {p.actionLabel}
                    </Button>
                  </Box>
                )
              })}
            </Box>
          )}

          <Divider sx={{ my: 1.5, borderColor: 'rgba(255,255,255,0.08)' }} />
          <Button size="small" variant="outlined" color="error" fullWidth
            onClick={() => { action('emergency_stop'); setOpen(false) }}
            sx={{ minHeight: 44, fontFamily: "'Courier New', monospace", fontWeight: 700 }}>
            ⛔ 긴급 정지
          </Button>
        </Box>
      </Drawer>
    </>
  )
}
