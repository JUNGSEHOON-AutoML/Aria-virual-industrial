// BottomPanel — G4: operator=구조화 알람티커+DiagDashboard / expert=전체알람+ECharts.
import { useRef, useEffect } from 'react'
import { Box, Typography } from '@mui/material'
import * as echarts from 'echarts'
import { useSignalStore } from '../signalStore'
import { useUiMode } from '../uiMode'
import { DiagDashboardButton, parseAlarm } from './DiagDashboard'

const LEVEL_COLOR = { error: '#f87171', warn: '#facc15', info: '#9aa0aa', ok: '#34d399' }

// ── Operator: G4 구조화 알람 티커 — 인라인 액션 버튼 형식 ──────────────
function AlarmTicker() {
  const alarms = useSignalStore(s => s.alarms)
  const action = useSignalStore(s => s.action)
  const ng = (alarms || []).filter(a => a.level === 'error').slice(0, 3)
  return (
    <Box sx={{ height: '100%', display: 'flex', alignItems: 'center', gap: 1,
      px: 1.5, fontFamily: "'Courier New', monospace", overflow: 'hidden' }}>
      <Typography sx={{ fontSize: 9, color: '#6b7280', letterSpacing: 1, flexShrink: 0 }}>
        NG ALERT:
      </Typography>
      <Box sx={{ width: 1, height: 18, bgcolor: 'rgba(255,255,255,0.1)', flexShrink: 0 }} />
      {ng.length === 0 ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8 }}>
          <span style={{ color: '#34d399', fontSize: 13 }}>●</span>
          <Typography sx={{ fontSize: 11, color: '#34d399' }}>ALL CLEAR</Typography>
        </Box>
      ) : ng.map((a, i) => {
        const p = parseAlarm(a)
        return (
          <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 0.5,
            bgcolor: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.22)',
            borderRadius: 1, pl: 1, pr: 0.5, py: 0.35, flexShrink: 0, minHeight: 28 }}>
            <span style={{ color: '#f87171', fontSize: 11 }}>⚠</span>
            <Typography sx={{ fontSize: 10, color: '#f87171', whiteSpace: 'nowrap' }}>
              {p.partId}: {p.label}
            </Typography>
            {/* 인라인 액션 버튼 — Gemini 이상안: "[해결 매뉴얼]" / "[재시작]" 형식 */}
            <Box component="span"
              onClick={() => { if (p.kind === 'restart') action('inspector_restart') }}
              sx={{ fontSize: 10, color: '#1FB8CD', cursor: 'pointer', px: 0.5,
                '&:hover': { color: '#38d9f5' }, whiteSpace: 'nowrap' }}>
              [{p.actionLabel}]
            </Box>
          </Box>
        )
      })}
      {/* 구분선 + 대시보드 버튼 */}
      <Box sx={{ ml: 'auto', flexShrink: 0 }}>
        <DiagDashboardButton />
      </Box>
    </Box>
  )
}

// ── Expert: 전체 알람 리스트 ──────────────────────────────────────────────
function Alarms() {
  const alarms = useSignalStore(s => s.alarms)
  return (
    <Box sx={{ height: '100%', overflowY: 'auto', fontFamily: "'Courier New', monospace", fontSize: 11.5 }}>
      <Typography sx={{ fontSize: 9, color: '#6b7280', letterSpacing: 1, mb: 0.5 }}>ALARMS / MESSAGES</Typography>
      {(!alarms || alarms.length === 0) && <Box sx={{ color: '#6b7280' }}>대기 중…</Box>}
      {(alarms || []).map((a, i) => (
        <Box key={i} sx={{ display: 'flex', gap: 1 }}>
          <span style={{ color: LEVEL_COLOR[a.level] || '#9aa0aa', fontWeight: 700, flex: '0 0 52px' }}>
            {a.tag}
          </span>
          <span style={{ color: '#cbd5e1', flex: 1, overflow: 'hidden',
            textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {a.text}
          </span>
        </Box>
      ))}
    </Box>
  )
}

// ── Expert: LIVE ECharts (ack/infer/loss) ────────────────────────────────
function Trend() {
  const ref = useRef()
  useEffect(() => {
    const chart = echarts.init(ref.current, 'dark', { renderer: 'canvas' })
    chart.setOption({
      backgroundColor: 'transparent',
      grid: { left: 38, right: 8, top: 20, bottom: 20 },
      legend: { top: 0, textStyle: { fontSize: 9, color: '#9aa0aa' }, data: ['ack max', 'infer p95', 'loss'] },
      xAxis: { type: 'time', axisLabel: { fontSize: 9, color: '#6b7280' } },
      yAxis: { type: 'value', name: 'ms', nameTextStyle: { fontSize: 9 },
        axisLabel: { fontSize: 9, color: '#6b7280' } },
      series: [
        { name: 'ack max', type: 'line', showSymbol: false, smooth: true,
          lineStyle: { width: 2, color: '#34d399' }, data: [],
          markLine: { silent: true, symbol: 'none',
            data: [{ yAxis: 20 }], lineStyle: { color: '#f87171', type: 'dashed' } } },
        { name: 'infer p95', type: 'line', showSymbol: false, smooth: true,
          lineStyle: { width: 2, color: '#facc15' }, data: [] },
        { name: 'loss', type: 'line', showSymbol: false,
          lineStyle: { width: 2, color: '#1FB8CD' }, data: [] },
      ],
    })
    let ack = [], infer = [], loss = []
    const onResize = () => chart.resize()
    window.addEventListener('resize', onResize)
    const unsub = useSignalStore.subscribe((state, prev) => {
      if (state.kpi !== prev.kpi && state.kpi) {
        const t = Date.now()
        ack = [...ack, [t, state.kpi.ack_max_ms ?? 0]].slice(-120)
        infer = [...infer, [t, state.kpi.infer_latency_p95_ms ?? 0]].slice(-120)
        chart.setOption({ series: [{ data: ack }, { data: infer }, {}] })
      }
      if (state.training !== prev.training && state.training?.metrics?.loss != null) {
        loss = [...loss, [Date.now(), state.training.metrics.loss]].slice(-200)
        chart.setOption({ series: [{}, {}, { data: loss }] })
      }
    })
    return () => { unsub(); window.removeEventListener('resize', onResize); chart.dispose() }
  }, [])
  return <div ref={ref} style={{ width: '100%', height: '100%', minHeight: 150 }} />
}

export default function BottomPanel() {
  const uiMode = useUiMode()

  if (uiMode === 'operator') {
    return <AlarmTicker />
  }

  return (
    <Box sx={{ height: '100%', display: 'grid', gridTemplateColumns: '1fr 360px', gap: 1, minHeight: 0 }}>
      <Box sx={{ p: 1, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 2, minHeight: 0 }}>
        <Alarms />
      </Box>
      <Box sx={{ p: 1, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 2, minHeight: 0 }}>
        <Typography sx={{ fontSize: 9, color: '#6b7280', letterSpacing: 1,
          fontFamily: "'Courier New', monospace" }}>
          LIVE · ack vs infer p95 · loss
        </Typography>
        <Box sx={{ height: 'calc(100% - 14px)' }}><Trend /></Box>
      </Box>
    </Box>
  )
}
