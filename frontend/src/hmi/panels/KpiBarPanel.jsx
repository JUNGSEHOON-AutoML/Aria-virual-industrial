// KpiBarPanel — G2: operator=YIELD위계+OK/NG비율바+STATE+VERDICT / expert=진단 8개.
// 색 규약: 정상=녹(#34d399) / 경고=황(#facc15) / 불량·정지=적(#f87171).
import { Box, Paper, Typography } from '@mui/material'
import { useSignalStore } from '../signalStore'
import { useUiMode } from '../uiMode'

// 경량 스파크라인(SVG, 라이브러리 없음) — 추세(시간축) 표시.
function Sparkline({ data, color = '#34d399', tau, height = 22, width = 96 }) {
  if (!data || data.length < 2) return (
    <svg width={width} height={height}><text x="2" y={height - 6} fontSize="8" fill="#4b5563">데이터 누적 중…</text></svg>
  )
  const n = data.length
  const min = Math.min(...data), max = Math.max(...data)
  const span = max - min || 1
  const pts = data.map((v, i) => {
    const x = (i / (n - 1)) * (width - 2) + 1
    const y = height - 2 - ((v - min) / span) * (height - 4)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  // τ 기준선(이상점수용)
  const tauY = tau != null ? height - 2 - ((tau - min) / span) * (height - 4) : null
  const last = data[n - 1]
  const lastColor = tau != null ? (last >= tau ? '#f87171' : last >= tau * 0.85 ? '#facc15' : '#34d399') : color
  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      {tauY != null && tauY > 0 && tauY < height &&
        <line x1="0" y1={tauY} x2={width} y2={tauY} stroke="#f87171" strokeWidth="0.6" strokeDasharray="2 2" opacity="0.5" />}
      <polyline points={pts} fill="none" stroke={lastColor} strokeWidth="1.4" />
      <circle cx={(width - 2) + 1} cy={height - 2 - ((last - min) / span) * (height - 4)} r="1.8" fill={lastColor} />
    </svg>
  )
}

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

// 지표 온톨로지: OEE = 가용성×성능×품질로 분해. SKIPPED/DROP=가용성, NG=품질.
// 단일 "수율"이 병목(가용성 손실)을 가리지 않게, OEE + 품질/가용성을 분리 표기.
function OeeCard({ kpi }) {
  const q = Math.round((kpi.quality ?? kpi.yield_rate ?? 0) * 100)   // 품질: OK/(OK+NG)
  const a = Math.round((kpi.availability ?? 1) * 100)                // 가용성: 검사/트리거
  const oee = Math.round((kpi.oee ?? (kpi.quality ?? 0)) * 100)
  const deferred = kpi.n_skipped ?? 0     // 보류(미검사=백프레셔) — 조용히 드롭 아님
  const color = oee >= 85 ? '#34d399' : oee >= 60 ? '#facc15' : '#f87171'
  // 진짜 원인 표면화: 가용성이 품질보다 낮으면 드롭/병목이 주범(품질 문제 아님)
  const ctx = (a < q && a < 90)
    ? `가용성 ${a}% ↓ — 병목/보류 (품질 ${q}%)`
    : q < 80
      ? `품질 ${q}% ↓ — 불량 多 (가용성 ${a}%)`
      : `품질 ${q}% · 가용성 ${a}%`
  const ctxColor = (a < q && a < 90) ? '#facc15' : q < 80 ? '#f87171' : '#4b9e6f'
  return (
    <Paper elevation={0} sx={{ flex: '0 0 auto', minWidth: 150, px: 2, py: 1,
      bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 2 }}>
      <Typography sx={{ fontSize: 38, fontWeight: 900, color, lineHeight: 1,
        fontFamily: "'Courier New', monospace" }}>
        {oee}%
      </Typography>
      <Typography sx={{ fontSize: 9, color: 'text.secondary', letterSpacing: 1, mt: 0.2 }}>
        OEE (가용성×성능×품질)
      </Typography>
      <Typography sx={{ fontSize: 9, color: ctxColor, mt: 0.2 }}>
        {ctx}{deferred ? ` · 보류 ${deferred}` : ''}
      </Typography>
    </Paper>
  )
}

// 추세 카드 — 수율·이상점수 스파크라인(시간축). 트윈 가치: 순간이 아닌 추세.
function TrendCard() {
  const trend = useSignalStore(s => s.trend) || { score: [], yield: [] }
  const scan = useSignalStore(s => s.scan)
  const tau = scan?.tau ?? 0.5
  const yPct = (trend.yield || []).map(v => v * 100)
  return (
    <Box sx={{ flex: '0 0 auto', minWidth: 122, px: 1.2, py: 0.6, bgcolor: 'rgba(255,255,255,0.04)',
      borderRadius: 2, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 0.3 }}>
      <Box>
        <Typography sx={{ fontSize: 8, color: 'text.secondary', letterSpacing: 0.5 }}>수율 추세</Typography>
        <Sparkline data={yPct} color="#34d399" width={108} height={20} />
      </Box>
      <Box>
        <Typography sx={{ fontSize: 8, color: 'text.secondary', letterSpacing: 0.5 }}>이상점수(τ선)</Typography>
        <Sparkline data={trend.score || []} tau={tau} width={108} height={20} />
      </Box>
    </Box>
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

// 설비 상태 카드(ⓑ) — 백엔드 FactoryLine equipment_status
const EQUIP_KO = {
  RUNNING: ['가동 중', '#34d399'], IDLE: ['대기', '#9aa0aa'],
  QA_ALERT: ['품질 경보', '#facc15'], MODEL_TRAINING: ['모델 학습', '#a78bfa'],
  THERMAL_FAULT: ['발열 감속', '#f87171'],
}
function EquipCard({ line }) {
  const [ko, color] = EQUIP_KO[line?.equipment_status] || ['—', '#4b5563']
  const sub = line
    ? `${line.conveyor_speed_mps ?? '--'}m/s · ${line.throughput_per_min ?? '--'}/min`
    : '라인 신호 대기'
  return (
    <Paper elevation={0} sx={{ flex: 1, minWidth: 110, px: 1.5, py: 1.2,
      bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 2, textAlign: 'center' }}>
      <Typography sx={{ fontSize: 9, color: 'text.secondary', letterSpacing: 0.5, mb: 0.4 }}>
        설비 상태
      </Typography>
      <Typography sx={{ fontSize: 18, fontWeight: 800, color, lineHeight: 1.1,
        fontFamily: "'Courier New', monospace" }}>
        {ko}
      </Typography>
      <Typography sx={{ fontSize: 8.5, color: 'text.secondary', mt: 0.3 }}>
        {sub}
      </Typography>
    </Paper>
  )
}

// GPU 카드(ⓓ) — 실측 온도/VRAM/부하. thermal 색 규약 적용.
const THERMAL_COLOR = { cool: '#1FB8CD', warm: '#facc15', hot: '#fb923c', critical: '#f87171' }
function GpuCard({ telemetry }) {
  if (!telemetry) return <Card label="GPU" value="—" />
  if (!telemetry.has_gpu) return <Card label="GPU" value="CPU 모드" color="#9aa0aa" />
  const color = THERMAL_COLOR[telemetry.thermal] || '#9aa0aa'
  return (
    <Paper elevation={0} sx={{ flex: 1, minWidth: 100, px: 1.5, py: 0.8,
      bgcolor: 'rgba(255,255,255,0.04)', borderRadius: 2, textAlign: 'center' }}>
      <Typography sx={{ fontSize: 18, fontWeight: 800, color, lineHeight: 1.0,
        fontFamily: "'Courier New', monospace" }}>
        {telemetry.temp_c}°C
      </Typography>
      <Typography sx={{ fontSize: 9, color: 'text.secondary', letterSpacing: 1, mt: 0.3 }}>
        GPU · VRAM {telemetry.vram_pct}%{telemetry.training ? ' · 학습' : ''}
      </Typography>
    </Paper>
  )
}

export default function KpiBarPanel() {
  const k = useSignalStore(s => s.kpi) || {}
  const lines = useSignalStore(s => s.lines)
  const scan = useSignalStore(s => s.scan)
  const line = useSignalStore(s => s.line)
  const telemetry = useSignalStore(s => s.telemetry)
  const uiMode = useUiMode()

  const fats = Object.values(lines || {}).map(l => l.fat_verdict).filter(Boolean)
  const fat = fats.includes('FAIL') ? 'FAIL' : fats.includes('PASS') ? 'PASS' : '—'
  const ack = k.ack_max_ms ?? 0

  // VERDICT: scan.verdict 우선, 없으면 fat_verdict
  const verdict = scan?.verdict || fat
  const verdictColor = verdict === 'OK' || verdict === 'PASS' ? '#34d399'
    : verdict === 'NG' || verdict === 'FAIL' ? '#f87171' : '#9aa0aa'

  const ngCount = k.n_ng ?? 0

  // ── Operator: G2 위계 — 수율 > 양품/불량 > 추세 > 최종판정 > 가동상태 ──
  if (uiMode === 'operator') {
    return (
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'stretch', height: '100%' }}>
        <OeeCard kpi={k} />
        <OkNgBar nOk={k.n_ok ?? 0} nNg={ngCount} />
        <TrendCard />
        <Card label="최종 판정" value={verdict} color={verdictColor} big />
        <StateCard state={k.state} />
        <EquipCard line={line} />
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
      <Card label="라인 THRU" value={line?.throughput_per_min != null ? `${line.throughput_per_min}/m` : '—'}
        color="#8fd6e0" />
      <GpuCard telemetry={telemetry} />
    </Box>
  )
}
