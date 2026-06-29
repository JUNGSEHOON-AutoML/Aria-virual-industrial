// KpiBarPanel — G2: operator=YIELD위계+OK/NG비율바+STATE+VERDICT / expert=진단 8개.
// 색 규약: 정상=녹(#34d399) / 경고=황(#facc15) / 불량·정지=적(#f87171).
import { Box, Paper, Typography } from '@mui/material'
import { useSignalStore } from '../signalStore'
import { useUiMode } from '../uiMode'

function Card({ label, value, color, big }) {
  return (
    <Paper elevation={0} sx={{
      flex: 1, minWidth: big ? 110 : 82, px: 1.5, py: big ? 1.2 : 0.8,
      bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 2, textAlign: 'center',
    }}>
      <Typography sx={{
        fontSize: big ? 28 : 18, fontWeight: 800, color: color || 'text.primary',
        lineHeight: 1.0, fontFamily: "'Courier New', monospace",
      }}>
        {value}
      </Typography>
      <Typography sx={{ fontSize: 9, color: 'text.secondary', letterSpacing: 1, mt: 0.3 }}>
        {label}
      </Typography>
    </Paper>
  )
}

const stateColor = s => {
  const v = String(s || '').toLowerCase()
  if (v === 'running' || v === 'run') return '#34d399'
  if (v === 'stopped' || v === 'stop' || v === 'error') return '#f87171'
  return '#9aa0aa'
}

// G2: 수율 최우선 — 가장 크게 + 목표 대비 맥락 라인 (한국어)
function YieldCard({ yieldRate }) {
  const pct = Math.round((yieldRate ?? 0) * 100)
  const delta = pct - 90
  const color = pct >= 90 ? '#34d399' : pct >= 80 ? '#facc15' : '#f87171'
  const ctxLabel = delta >= 0
    ? `목표(90%) 달성 +${delta}%p`
    : delta >= -10
      ? `수율 경고: 목표(90%) 대비 낮음`
      : `수율 위험: 목표(90%) 대비 -${Math.abs(delta)}%p`
  return (
    <Paper elevation={0} sx={{ flex: '0 0 auto', minWidth: 130, px: 2, py: 1,
      bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 2 }}>
      <Typography sx={{ fontSize: 42, fontWeight: 900, color, lineHeight: 1,
        fontFamily: "'Courier New', monospace" }}>
        {pct}%
      </Typography>
      <Typography sx={{ fontSize: 9, color: 'text.secondary', letterSpacing: 1, mt: 0.2 }}>
        수율
      </Typography>
      <Typography sx={{ fontSize: 9, color: delta < 0 ? color : '#4b9e6f', mt: 0.2 }}>
        {ctxLabel}
      </Typography>
    </Paper>
  )
}

// G2: 양품/불량품 비율 게이지 바 (한국어)
function OkNgBar({ nOk, nNg }) {
  const total = nOk + nNg
  const okPct = total > 0 ? (nOk / total) * 100 : 50
  const ngPct = total > 0 ? (nNg / total) * 100 : 50
  const empty = total === 0
  return (
    <Box sx={{ flex: 1, px: 1.5, py: 0.8, bgcolor: 'rgba(255,255,255,0.04)',
      borderRadius: 2, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 0.5,
      minWidth: 120 }}>
      <Typography sx={{ fontSize: 9, color: 'text.secondary', letterSpacing: 0.5 }}>양품 / 불량품</Typography>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8, mb: 0.2 }}>
        <Typography sx={{ fontSize: 9, color: '#34d399' }}>OK</Typography>
        <Box sx={{ flex: 1, height: 8, borderRadius: 1, overflow: 'hidden',
          bgcolor: 'rgba(255,255,255,0.06)', display: 'flex' }}>
          <Box sx={{ width: `${okPct}%`, bgcolor: empty ? 'rgba(52,211,153,0.25)' : '#34d399',
            transition: 'width 0.5s ease' }} />
          <Box sx={{ width: `${ngPct}%`, bgcolor: empty ? 'rgba(248,113,113,0.2)' : '#f87171',
            transition: 'width 0.5s ease' }} />
        </Box>
        <Typography sx={{ fontSize: 9, color: nNg > 0 ? '#f87171' : '#4b5563' }}>NG</Typography>
      </Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
        <Typography sx={{ fontSize: 9, color: '#34d399', fontFamily: "'Courier New', monospace" }}>
          {nOk}건 ({okPct.toFixed(0)}%)
        </Typography>
        <Typography sx={{ fontSize: 9, color: nNg > 0 ? '#f87171' : '#4b5563',
          fontFamily: "'Courier New', monospace" }}>
          {nNg}건 ({ngPct.toFixed(0)}%)
        </Typography>
      </Box>
    </Box>
  )
}

// 가동 상태 카드 — 한국어 값
function StateCard({ state }) {
  const v = String(state || '').toLowerCase()
  const ko = v === 'running' || v === 'run' ? '가동 중'
    : v === 'stopped' || v === 'stop' ? '정지'
    : v === 'error' ? '오류'
    : '대기'
  const color = stateColor(state)
  return (
    <Paper elevation={0} sx={{ flex: 1, minWidth: 110, px: 1.5, py: 1.2,
      bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 2, textAlign: 'center' }}>
      <Typography sx={{ fontSize: 9, color: 'text.secondary', letterSpacing: 0.5, mb: 0.4 }}>
        가동 상태
      </Typography>
      <Typography sx={{ fontSize: 20, fontWeight: 800, color, lineHeight: 1.1,
        fontFamily: "'Courier New', monospace" }}>
        {ko}
      </Typography>
    </Paper>
  )
}

export default function KpiBarPanel() {
  const k = useSignalStore(s => s.kpi) || {}
  const lines = useSignalStore(s => s.lines)
  const scan = useSignalStore(s => s.scan)
  const uiMode = useUiMode()

  const fats = Object.values(lines || {}).map(l => l.fat_verdict).filter(Boolean)
  const fat = fats.includes('FAIL') ? 'FAIL' : fats.includes('PASS') ? 'PASS' : '—'
  const ack = k.ack_max_ms ?? 0

  // VERDICT: scan.verdict 우선, 없으면 fat_verdict
  const verdict = scan?.verdict || fat
  const verdictColor = verdict === 'OK' || verdict === 'PASS' ? '#34d399'
    : verdict === 'NG' || verdict === 'FAIL' ? '#f87171' : '#9aa0aa'

  const ngCount = k.n_ng ?? 0

  // ── Operator: G2 위계 — 수율 > 양품/불량 > 최종판정 > 가동상태 (한국어) ──
  if (uiMode === 'operator') {
    return (
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'stretch', height: '100%' }}>
        <YieldCard yieldRate={k.yield_rate ?? 0} />
        <OkNgBar nOk={k.n_ok ?? 0} nNg={ngCount} />
        <Card label="최종 판정" value={verdict} color={verdictColor} big />
        <StateCard state={k.state} />
      </Box>
    )
  }

  // ── Expert: 진단 8개 ────────────────────────────────────────────────────
  return (
    <Box sx={{ display: 'flex', gap: 1, alignItems: 'stretch' }}>
      <Card label="STATE" value={k.state || 'IDLE'} color={stateColor(k.state)} />
      <Card label="YIELD" value={`${((k.yield_rate ?? 0) * 100).toFixed(0)}%`} color="#1FB8CD" />
      <Card label="TACT" value={`${(k.tact_time_ms ?? 0).toFixed(0)}ms`} />
      <Card label="ACK max" value={`${ack.toFixed(1)}ms`} color={ack < 20 ? '#34d399' : '#f87171'} />
      <Card label="QUEUE" value={`${k.queue_depth ?? 0}/4`}
        color={(k.queue_depth ?? 0) > 0 ? '#facc15' : undefined} />
      <Card label="DROP" value={`${k.drop_count ?? 0}`}
        color={(k.drop_count ?? 0) > 0 ? '#f87171' : undefined} />
      <Card label="OK/NG" value={`${k.n_ok ?? 0}/${ngCount}`} />
      <Card label="FAT" value={fat}
        color={fat === 'PASS' ? '#34d399' : fat === 'FAIL' ? '#f87171' : undefined} />
    </Box>
  )
}
