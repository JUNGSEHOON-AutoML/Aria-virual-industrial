// RightPanel — operator: [검사 결과 | 설비 건전성] 탭 / expert: 트리 선택 컨텍스트.
import { useEffect, useState } from 'react'
import { Box, Typography, Button, Stack, ToggleButtonGroup, ToggleButton } from '@mui/material'
import { useSignalStore } from '../signalStore'
import { classSamples } from '../../api/apiClient'
import { DATA_ROOT } from '../sceneModel'
import { useUiMode } from '../uiMode'
import { deriveAssets, statusColor, statusKo, faultyAssets } from '../scene/assetModel'
import { buildVlmReport } from '../scene/vlmReport'
import DefectViewer from './DefectViewer'

// 시뮬 지표 갱신용 — 1초마다 리렌더
function useTick(ms = 1000) {
  const [, f] = useState(0)
  useEffect(() => {
    const id = setInterval(() => f(n => (n + 1) % 1e6), ms)
    return () => clearInterval(id)
  }, [ms])
}

// ── Operator: 설비 건전성(Asset Health) 대시보드 ───────────────────────
function AssetHealthPanel() {
  useTick(1000)
  const k = useSignalStore(s => s.kpi) || {}
  const scan = useSignalStore(s => s.scan)
  const assets = deriveAssets(k, scan, typeof performance !== 'undefined' ? performance.now() : 0)
  const faulty = faultyAssets(assets)

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 0.8 }}>
      <Typography sx={{ fontSize: 9, color: '#6b7280', letterSpacing: 1 }}>설비 건전성</Typography>

      {/* 요약 배너 */}
      <Box sx={{ px: 1, py: 0.6, borderRadius: 1,
        bgcolor: faulty.length ? 'rgba(248,113,113,0.10)' : 'rgba(52,211,153,0.08)',
        border: `1px solid ${faulty.length ? 'rgba(248,113,113,0.3)' : 'rgba(52,211,153,0.25)'}` }}>
        <Typography sx={{ fontSize: 11, color: faulty.length ? '#f87171' : '#34d399' }}>
          {faulty.length
            ? `⚠ 주의 설비 ${faulty.length}대 — ${faulty.map(a => a.name).join(', ')}`
            : '● 전 설비 정상 가동'}
        </Typography>
      </Box>

      {/* 설비 카드 리스트 */}
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.6, overflowY: 'auto' }}>
        {assets.map(a => {
          const c = statusColor(a.status)
          return (
            <Box key={a.id} sx={{ px: 1, py: 0.8, borderRadius: 1.5,
              bgcolor: 'rgba(255,255,255,0.03)', border: `1px solid ${c}33` }}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.7 }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: c,
                    boxShadow: `0 0 6px ${c}` }} />
                  <Typography sx={{ fontSize: 12, color: '#e2e8f0' }}>{a.name}</Typography>
                </Box>
                <Typography sx={{ fontSize: 11, color: c, fontWeight: 700 }}>
                  {statusKo(a.status)}
                </Typography>
              </Box>
              <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 0.4 }}>
                {a.metrics.map((m, i) => (
                  <Box key={i} sx={{ textAlign: 'center', bgcolor: 'rgba(255,255,255,0.02)',
                    borderRadius: 0.8, py: 0.4 }}>
                    <Typography sx={{ fontSize: 11, color: '#cbd5e1',
                      fontFamily: "'Courier New', monospace" }}>
                      {m.v}{m.unit ? <span style={{ fontSize: 8, color: '#6b7280' }}> {m.unit}</span> : null}
                    </Typography>
                    <Typography sx={{ fontSize: 8, color: m.sim ? '#7c6b4b' : '#6b7280' }}>
                      {m.k}{m.sim ? ' ◦' : ''}
                    </Typography>
                  </Box>
                ))}
              </Box>
            </Box>
          )
        })}
      </Box>

      <Typography sx={{ fontSize: 8, color: '#4b5563', mt: 'auto' }}>
        ◦ = 데모 시뮬 센서값(실측 피드 없음) · 그 외 실측 신호
      </Typography>
    </Box>
  )
}

const head = { fontSize: 9, color: '#6b7280', letterSpacing: 1, mb: 1 }
function Row({ k, v, c }) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', py: 0.3, fontSize: 12 }}>
      <span style={{ color: '#6b7280' }}>{k}</span>
      <span style={{ color: c || '#e2e8f0' }}>{v}</span>
    </Box>
  )
}

// ── 언어 게이지: 수치 대신 "정상 · 기준까지 X% 여유" + 주의존(황). 색 의미 고정(녹/황/적). ──
function ScoreGauge({ score, tau, showNumber = false }) {
  if (score == null || score < 0) return null
  const t = tau ?? 0.5
  const max = Math.max(1.0, 2 * t)
  const tauPct = (t / max) * 100
  const warnPct = (t * 0.85 / max) * 100              // 주의존 시작(기준의 85%)
  const scorePct = Math.min(100, Math.max(0, (score / max) * 100))
  // 상태: 정상(녹) / 주의(황, 기준 근접) / NG(적)
  const ratio = score / t                              // 1=기준
  const state = ratio >= 1 ? 'NG' : ratio >= 0.85 ? '주의' : '정상'
  const mc = state === 'NG' ? '#f87171' : state === '주의' ? '#facc15' : '#34d399'
  const marginPct = Math.round((1 - ratio) * 100)     // 기준까지 여유(%)
  const label = state === 'NG' ? `불량 · 기준 ${Math.round((ratio - 1) * 100)}% 초과`
    : state === '주의' ? `주의 · 기준에 근접 (여유 ${marginPct}%)`
    : `정상 · 기준까지 여유 ${marginPct}%`

  return (
    <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
      <Typography sx={{ fontSize: 12, color: mc, fontWeight: 700, mb: 0.6 }}>{label}</Typography>
      <Box sx={{ height: 12, position: 'relative', borderRadius: 1, overflow: 'hidden' }}>
        <Box sx={{ position: 'absolute', inset: 0, bgcolor: 'rgba(52,211,153,0.18)' }} />
        <Box sx={{ position: 'absolute', top: 0, bottom: 0, left: `${warnPct}%`, width: `${tauPct - warnPct}%`,
          bgcolor: 'rgba(250,204,21,0.25)' }} />
        <Box sx={{ position: 'absolute', top: 0, bottom: 0, left: `${tauPct}%`, right: 0,
          bgcolor: 'rgba(248,113,113,0.18)' }} />
        <Box sx={{ position: 'absolute', top: -1, bottom: -1, left: `${tauPct}%`, width: 2, bgcolor: '#9aa0aa' }} />
        <Box sx={{ position: 'absolute', top: 0, bottom: 0, left: `${scorePct}%`, width: 4,
          bgcolor: mc, transform: 'translateX(-2px)', borderRadius: 1, boxShadow: `0 0 6px ${mc}` }} />
      </Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.3 }}>
        <Typography sx={{ fontSize: 8, color: '#34d399' }}>정상</Typography>
        <Typography sx={{ fontSize: 8, color: '#facc15' }}>주의</Typography>
        <Typography sx={{ fontSize: 8, color: '#f87171' }}>기준</Typography>
      </Box>
      {showNumber && (
        <Typography sx={{ fontSize: 9, color: '#4b5563', mt: 0.3 }}>
          score {score.toFixed(3)} / τ {t.toFixed(3)} · 낮을수록 정상
        </Typography>
      )}
    </Box>
  )
}

// ── 공정 파이프라인 배너 — "지금 어떤 모델/공정으로 검사 중인지" 투명 표시 ──
const PIPELINE = {
  mock: '시뮬 드라이버 (실 추론 아님 — UI 점검용)',
  patchcore: 'PatchCore 이상탐지 (DINO feature · 코사인 거리)',
  combined: 'PatchCore 이상게이트 → 이상 시에만 YOLO 결함분류 (효율 라우팅)',
}
function ProcessBanner() {
  const mode = useSignalStore(s => s.activeMode)
  if (!mode) return null
  return (
    <Box sx={{ mb: 1, px: 1, py: 0.7, borderRadius: 1, bgcolor: 'rgba(31,184,205,0.07)',
      border: '1px solid rgba(31,184,205,0.25)' }}>
      <Typography sx={{ fontSize: 9, color: '#6b7280', letterSpacing: 0.5 }}>공정 · 모델</Typography>
      <Typography sx={{ fontSize: 10.5, color: '#1FB8CD' }}>{mode}</Typography>
      <Typography sx={{ fontSize: 9.5, color: '#9aa3b2', mt: 0.2 }}>{PIPELINE[mode] || '—'}</Typography>
    </Box>
  )
}

// ── Operator 기본: 라인 건강 요약 + "다음 행동" (2초 안에 ①건강 ②손댈것 ③어디·뭐) ──
function LineSummary() {
  const k = useSignalStore(s => s.kpi) || {}
  const scan = useSignalStore(s => s.scan)
  const lastNG = useSignalStore(s => s.lastNG)
  const predictions = useSignalStore(s => s.predictions) || []
  const assets = deriveAssets(k, scan, 0)
  const faulty = faultyAssets(assets)
  const activePred = predictions.filter(p => p.status === 'pending' || p.status === 'approved')
  const yieldPct = Math.round((k.yield_rate ?? 0) * 100)
  const running = String(k.state || '').toLowerCase().startsWith('run')

  // 라인 상태(녹/황/적) + 다음 행동
  let state, sColor, action
  if (faulty.some(a => a.status === 'Error') || (running && yieldPct < 50)) {
    state = '불량 다발'; sColor = '#f87171'
    action = faulty.length ? `${faulty[0].name} 점검 — 보고서/예지 확인` : '불량률 급증 — 라인 점검'
  } else if (faulty.length || activePred.length || (running && yieldPct < 90)) {
    state = '주의'; sColor = '#facc15'
    action = activePred.length ? `예지 ${activePred.length}건 검토 (우측 제안)` :
      faulty.length ? `${faulty[0].name} 주의 관찰` : '수율 목표 미달 — 추세 확인'
  } else {
    state = running ? '정상 가동' : '대기'; sColor = running ? '#34d399' : '#9aa0aa'
    action = '조치 불필요 — 정상'
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.8 }}>
      <ProcessBanner />
      {/* ① 라인 건강 */}
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
        <span style={{ width: 11, height: 11, borderRadius: '50%', background: sColor, boxShadow: `0 0 8px ${sColor}` }} />
        <Typography sx={{ fontSize: 22, fontWeight: 800, color: sColor }}>{state}</Typography>
        <Typography sx={{ fontSize: 12, color: '#9aa3b2', ml: 'auto' }}>수율 {yieldPct}%</Typography>
      </Box>
      {/* ② 다음 행동 */}
      <Box sx={{ px: 1, py: 0.8, borderRadius: 1, bgcolor: `${sColor}14`, border: `1px solid ${sColor}44` }}>
        <Typography sx={{ fontSize: 9, color: '#6b7280', letterSpacing: 1 }}>다음 행동</Typography>
        <Typography sx={{ fontSize: 12, color: '#e2e8f0' }}>{action}</Typography>
      </Box>
      {/* ③ 최근 불량(안정) */}
      <Box sx={{ mt: 0.3 }}>
        <Typography sx={{ fontSize: 9, color: '#6b7280', letterSpacing: 1 }}>최근 불량</Typography>
        {lastNG ? (
          <Typography sx={{ fontSize: 11, color: '#cbd5e1' }}>
            <span style={{ color: '#f87171' }}>{lastNG.part_id}</span>
            {lastNG.defect_class ? ` · ${lastNG.defect_class}` : ''}
            {lastNG.score != null ? ` · score ${lastNG.score.toFixed(3)}` : ''}
          </Typography>
        ) : <Typography sx={{ fontSize: 11, color: '#34d399' }}>없음 — 전수 정상</Typography>}
      </Box>
      <Typography sx={{ fontSize: 9, color: '#4b5563', mt: 0.4 }}>
        3D에서 부품을 클릭하면 그 부품 상세 검사가 여기에 고정됩니다.
      </Typography>
    </Box>
  )
}

// ── Operator: 주목(클릭) 부품 상세 — focus 우선, 전 화면 일관 ─────────────
function ScanResult({ scan, onClear }) {
  const det = useSignalStore(s => s.detectors) || {}
  if (!scan) return <LineSummary />

  const verdict = scan.verdict
  const isNG = verdict === 'NG'
  const isOK = verdict === 'OK'
  const vColor = isOK ? '#34d399' : isNG ? '#f87171' : '#9aa0aa'
  const verdictKo = isOK ? '정상' : isNG ? '불량(NG)' : '—'

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 0.4 }}>
      {onClear && (
        <Box onClick={onClear} sx={{ cursor: 'pointer', mb: 0.3 }}>
          <Typography sx={{ fontSize: 10, color: '#1FB8CD' }}>← 전체 보기(라인 요약)</Typography>
        </Box>
      )}
      {/* ① 판정 하나 — 가장 크게 */}
      <Typography sx={{ fontSize: 34, fontWeight: 900, color: vColor, lineHeight: 1.1 }}>
        {verdictKo}
      </Typography>
      <Typography sx={{ fontSize: 10, color: '#6b7280' }}>
        📌 {scan.part_id || '—'}{scan.class ? ` (${scan.class})` : ''}
      </Typography>

      {/* ② 언어 게이지 */}
      <ScoreGauge score={scan.score} tau={scan.tau} />

      {/* ③ 근거 펼침 — 부품 record 기준(전역 det 아님) */}
      <ReasonAccordion scan={scan} isNG={isNG} />
    </Box>
  )
}

// 근거 펼치기 — 부품 record 기준. OK일 땐 YOLO 결함라벨 노출 안 함(모순 방지).
function ReasonAccordion({ scan, isNG }) {
  const det = { patchcore: scan.score != null && scan.score >= 0 ? { score: scan.score, verdict: scan.verdict } : null,
    yolo: scan.defect_class ? { defect_class: scan.defect_class } : null }
  const [open, setOpen] = useState(false)
  return (
    <Box sx={{ mt: 0.6, pt: 0.6, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
      <Box onClick={() => setOpen(o => !o)} sx={{ cursor: 'pointer', display: 'flex',
        alignItems: 'center', gap: 0.5 }}>
        <Typography sx={{ fontSize: 10, color: '#9aa3b2' }}>{open ? '▾' : '▸'} 판정 근거 {open ? '접기' : '펼치기'}</Typography>
      </Box>
      {open && (
        <Box sx={{ mt: 0.5 }}>
          {det.patchcore && (
            <Row k="PatchCore(이상)" v={`${det.patchcore.score?.toFixed?.(3)} · ${det.patchcore.verdict}`}
              c={det.patchcore.verdict === 'NG' ? '#f87171' : '#34d399'} />
          )}
          {/* YOLO 결함분류는 NG(이상 게이트 통과) 때만 — OK 옆 결함라벨 모순 제거 */}
          {isNG && det.yolo?.defect_class && (
            <Row k="YOLO(결함)" v={det.yolo.defect_class} c="#fca5a5" />
          )}
          {!isNG && det.yolo?.defect_class && (
            <Typography sx={{ fontSize: 9, color: '#5b6677', py: 0.3 }}>
              YOLO 후보 {det.yolo.defect_class} → PatchCore 정상 판정으로 기각
            </Typography>
          )}
          <VlmSection scan={scan} />
        </Box>
      )}
    </Box>
  )
}

// ── VLM 분석 섹션 (관측/추정원인/권장조치) ─────────────────────────────
function VlmSection({ scan, mock = false }) {
  const r = buildVlmReport(scan, mock)
  return (
    <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.7, mb: 0.5 }}>
        <Typography sx={head}>VLM 분석</Typography>
        {r.placeholder && <Typography sx={{ fontSize: 8, color: '#a78b4b' }}>placeholder</Typography>}
      </Box>
      <Typography sx={{ fontSize: 11, color: '#cbd5e1', lineHeight: 1.5 }}>
        <span style={{ color: '#6b7280' }}>관측 · </span>{r.observation}
      </Typography>
      {r.cause ? (
        <Typography sx={{ fontSize: 11, lineHeight: 1.5, mt: 0.4 }}>
          <span style={{ color: '#6b7280' }}>추정 원인 · </span>
          <span style={{ color: '#facc15' }}>{r.cause.text}</span>
          <span style={{ color: '#9aa0aa' }}> (신뢰도 {r.cause.confidence.toFixed(2)} · {r.cause.note})</span>
        </Typography>
      ) : (
        <Typography sx={{ fontSize: 11, color: '#34d399', mt: 0.4 }}>추정 원인 · 해당 없음(정상)</Typography>
      )}
      <Typography sx={{ fontSize: 11, color: '#cbd5e1', lineHeight: 1.5, mt: 0.4 }}>
        <span style={{ color: '#6b7280' }}>권장 조치 · </span>{r.action}
      </Typography>
    </Box>
  )
}

// ── Expert: 라인 선택 컨텍스트 ───────────────────────────────────────────
function LineCtx({ id }) {
  const lines = useSignalStore(s => s.lines)
  const trainClass = useSignalStore(s => s.trainClass)
  const validateClass = useSignalStore(s => s.validateClass)
  const [items, setItems] = useState([])
  const r = lines?.[id]
  const path = `${DATA_ROOT}/${id}`
  useEffect(() => {
    setItems([])
    classSamples(id, path).then(s => { if (s?.ok) setItems(s.items || []) }).catch(() => {})
  }, [id])
  return (
    <>
      <Typography sx={head}>LINE · {String(id).toUpperCase()}</Typography>
      <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
        <Button size="small" variant="outlined" sx={{ fontSize: 10 }}
          onClick={() => trainClass(id, path)}>학습</Button>
        <Button size="small" variant="outlined" sx={{ fontSize: 10 }}
          onClick={() => validateClass(id, path)}>판정</Button>
      </Stack>
      {r && <Box sx={{ mb: 1 }}>
        <Row k="verdict" v={r.fat_verdict || '—'}
          c={r.fat_verdict === 'PASS' ? '#34d399' : '#f87171'} />
        <Row k="escape" v={r.escape_rate != null ? `${(r.escape_rate * 100).toFixed(0)}%` : '—'} />
      </Box>}
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 0.5 }}>
        {items.slice(0, 9).map((it, i) => (
          <img key={i} src={it.url} alt="" style={{ width: '100%', height: 48, objectFit: 'cover',
            borderRadius: 4, border: `1px solid ${it.label === 'NG' ? '#f87171' : '#34d399'}` }} />
        ))}
      </Box>
    </>
  )
}

function NodeCtx({ id }) {
  const k = useSignalStore(s => s.kpi) || {}
  const det = useSignalStore(s => s.detectors) || {}
  return (
    <>
      <Typography sx={head}>VISION NODE · {String(id).toUpperCase()}</Typography>
      <Row k="ack max" v={`${(k.ack_max_ms ?? 0).toFixed(1)}ms`}
        c={(k.ack_max_ms ?? 0) < 20 ? '#34d399' : '#f87171'} />
      <Row k="infer p95" v={`${(k.infer_latency_p95_ms ?? 0).toFixed(0)}ms`} c="#facc15" />
      <Row k="queue / drop" v={`${k.queue_depth ?? 0} / ${k.drop_count ?? 0}`} />
      <Row k="OK / NG" v={`${k.n_ok ?? 0} / ${k.n_ng ?? 0}`} />
      <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
        <Row k="PatchCore"
          v={det.patchcore ? `${det.patchcore.score?.toFixed?.(3)} · ${det.patchcore.verdict}` : '—'} />
        <Row k="YOLO" v={det.yolo?.defect_class || '—'} c="#fca5a5" />
      </Box>
    </>
  )
}

// ── T1-B/T1-C: 예지보전 가설 카드 (통계 신뢰도 ↔ 인과 가설 분리, 표본/RUL 표기, 점검 지시) ──
const ASSET_KO = { robot_arm: '로봇 팔', vision_camera: '비전 카메라', conveyor_motor: '컨베이어 모터' }
const SIGNAL_KO = { rms_slope: '진동↑', temp_slope: '발열↑', p95_creep: '지연↑', drop_trend: '드롭↑' }
const baseAsset = (a) => (a || '').replace(/_\d+$/, '')
const laneOf = (a) => { const m = /_(\d+)$/.exec(a || ''); return m ? ` #${m[1]}` : '' }
function predName(p) {
  if (p.asset) return (ASSET_KO[baseAsset(p.asset)] || p.asset) + laneOf(p.asset)
  return ASSET_KO[p.causal?.assetHint] || p.cell
}
// 건전성 게이지(H: 녹→황→적) — 순수 표현
function HealthGauge({ h }) {
  const pct = Math.round((h ?? 0) * 100)
  const color = h >= 0.7 ? '#34d399' : h >= 0.45 ? '#facc15' : '#f87171'
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.6, mt: 0.4 }}>
      <Typography sx={{ fontSize: 9, color: '#9aa0aa', minWidth: 30 }}>건전성</Typography>
      <Box sx={{ flex: 1, height: 6, borderRadius: 1, bgcolor: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
        <Box sx={{ width: `${pct}%`, height: '100%', bgcolor: color, transition: 'width .5s' }} />
      </Box>
      <Typography sx={{ fontSize: 9, color, fontFamily: "'Courier New', monospace", minWidth: 28 }}>{pct}%</Typography>
    </Box>
  )
}
function PredictiveCards() {
  const predictions = useSignalStore(s => s.predictions) || []
  const addApproval = useSignalStore(s => s.addApproval)
  const setPredictionStatus = useSignalStore(s => s.setPredictionStatus)
  // 활성(해소/기각 제외)만 + 우선순위(위치 집중 높은 순) 정렬
  const active = predictions
    .filter(p => p.status === 'pending' || p.status === 'approved')
    .sort((a, b) => (b.statConfidence ?? 0) - (a.statConfidence ?? 0))
  if (!active.length) return null

  const order = (id) => () => {
    setPredictionStatus(id, 'approved')
    const p = predictions.find(x => x.id === id)
    const asset = p?.causal?.assetHint
    // ★승인=인과 확정 아님. 점검/조치 실행을 승인 게이트로(request_real_action)
    addApproval({
      id: `ap_pred_${id}_${p.occurrences}`, assetId: asset, assetName: ASSET_KO[asset] || asset,
      action: 'inspector_restart', actionLabel: '점검·재교정', kind: 'inspection',
      status: 'pending', ts: Date.now(),
    })
  }

  return (
    <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
      {/* 색 의미 고정: 황=주의·예지 */}
      <Typography sx={{ ...head, color: '#facc15' }}>⚠ 예지·점검 제안 ({active.length})</Typography>
      {active.map((p, idx) => (
        <Box key={p.id} sx={{ mt: 0.8, p: 1, borderRadius: 1.5,
          bgcolor: 'rgba(250,204,21,0.06)', border: '1px solid rgba(250,204,21,0.3)' }}>
          {/* 우선순위 + 신뢰도 + (교차확증 배지) */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <Typography sx={{ fontSize: 11, color: '#e2e8f0' }}>
              <span style={{ color: '#facc15', fontWeight: 700 }}>#{idx + 1}</span> {predName(p)}
              {p.corroborated && <span style={{ color: '#34d399', fontSize: 9, marginLeft: 6 }}>✓교차확증</span>}
            </Typography>
            <Typography sx={{ fontSize: 9, color: '#9aa0aa' }}>
              신뢰 {(p.statConfidence ?? 0).toFixed(2)}{p.total != null ? ` · ${p.total}중 ${p.ngTotal}회` : ''}
            </Typography>
          </Box>
          {/* T1-C PdM: 건전성 게이지 + RUL(밴드) + 선행신호 */}
          {p.rul && (
            <>
              {p.health != null && <HealthGauge h={p.health} />}
              {p.rul.est_hours != null ? (
                <Typography sx={{ fontSize: 10.5, mt: 0.4, color: '#facc15', fontFamily: "'Courier New', monospace" }}>
                  RUL ~{p.rul.est_hours}h <span style={{ color: '#9aa0aa' }}>({p.rul.lo}–{p.rul.hi}h · {p.rul.model})</span>
                </Typography>
              ) : (
                <Typography sx={{ fontSize: 10, mt: 0.4, color: '#9aa0aa' }}>RUL 미외삽 (임박 열화 없음)</Typography>
              )}
              {p.leadingSignals?.length > 0 && (
                <Typography sx={{ fontSize: 9.5, mt: 0.2, color: '#cbd5e1' }}>
                  선행: {p.leadingSignals.map(s => SIGNAL_KO[s] || s).join(' · ')}
                  {p.ngEvidence && <span style={{ color: '#34d399' }}> · NG {p.ngEvidence.window}</span>}
                </Typography>
              )}
              <Typography sx={{ fontSize: 9, mt: 0.2, color: '#6b7280' }}>{p.note || '확인요망(단정 아님)'}</Typography>
            </>
          )}
          {/* T1-B 인과 가설(미검증) + 실 결함종류 */}
          {!p.rul && (
            <Typography sx={{ fontSize: 10.5, mt: 0.3, color: '#cbd5e1' }}>
              {p.causal?.hypothesis}{p.defectClass ? ` · 반복 ${p.defectClass}×${p.defectClassN}` : ''}
              <span style={{ color: '#6b7280', fontSize: 9 }}> (가설·미검증)</span>
            </Typography>
          )}
          {/* 권장 조치 */}
          <Typography sx={{ fontSize: 10, mt: 0.2, color: '#9aa3b2' }}>
            권장 · {p.recommendedAction || '해당 셀 점검·재교정'}
          </Typography>
          {/* 조치 + 피드백(확인/기각) */}
          {p.status === 'approved' ? (
            <Typography sx={{ fontSize: 9, color: '#34d399', mt: 0.6 }}>✓ 점검 지시됨 — 승인 게이트에서 실행</Typography>
          ) : (
            <Stack direction="row" spacing={0.8} sx={{ mt: 0.8 }}>
              <Button size="small" variant="outlined" color="warning" onClick={order(p.id)}
                sx={{ flex: 1, minHeight: 32, fontSize: 10 }}>점검 지시</Button>
              <Button size="small" variant="text" color="inherit"
                onClick={() => setPredictionStatus(p.id, 'dismissed')}
                sx={{ minHeight: 32, fontSize: 10 }}>기각</Button>
            </Stack>
          )}
        </Box>
      ))}
    </Box>
  )
}

// ── 에이전트 점검 보고서 — 자동 승인 모달 대신 누적. 운영자가 필요할 때만 조치. ──
function ReportPanel() {
  const report = useSignalStore(s => s.report) || []
  const addApproval = useSignalStore(s => s.addApproval)
  const setReportStatus = useSignalStore(s => s.setReportStatus)
  const trained = useSignalStore(s => s.trained) || {}
  const [viewer, setViewer] = useState(false)
  const open = report.filter(r => r.status === 'open')
  const done = report.filter(r => r.status !== 'open').slice(0, 6)
  const anyTrained = Object.keys(trained).length > 0

  const act = (r) => {
    // 운영자가 보고서에서 조치를 시작할 때만 승인 게이트 생성(원인 확정 아님)
    addApproval({
      id: `ap_rep_${r.id}`, assetId: r.asset, assetName: r.assetName,
      action: r.action || 'inspector_restart', actionLabel: r.recommendedAction || '점검·재교정',
      kind: 'inspection', status: 'pending', ts: Date.now(),
    })
    setReportStatus(r.id, 'acted')
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.8 }}>
      {/* 결함 3D 뷰어 — 학습 완료 클래스의 결함을 360° 회전 검수 */}
      <Button size="small" variant="outlined" disabled={!anyTrained}
        onClick={() => setViewer(true)}
        sx={{ fontSize: 10, minHeight: 32, mb: 0.5,
          color: anyTrained ? '#1FB8CD' : '#4b5563',
          borderColor: anyTrained ? '#1FB8CD55' : 'rgba(255,255,255,0.1)' }}>
        🔄 결함 3D 뷰어 (360° 검수)
      </Button>
      <DefectViewer open={viewer} onClose={() => setViewer(false)} category="bottle" />

      <Typography sx={head}>에이전트 점검 보고서</Typography>
      {!open.length && (
        <Typography sx={{ fontSize: 11, color: '#6b7280' }}>
          ◎ 미처리 항목 없음 — 에이전트가 라인을 점검 중입니다.
        </Typography>
      )}
      {open.map(r => (
        <Box key={r.id} sx={{ p: 1, borderRadius: 1.5,
          bgcolor: 'rgba(240,163,90,0.06)', border: '1px solid rgba(240,163,90,0.28)' }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <Typography sx={{ fontSize: 12, color: '#f0a35a' }}>⚠ {r.title}</Typography>
            <Typography sx={{ fontSize: 9, color: '#6b7280' }}>
              {r.occurrences > 1 ? `누적 ${r.occurrences}회` : ''} {new Date(r.ts).toLocaleTimeString()}
            </Typography>
          </Box>
          <Typography sx={{ fontSize: 10, color: '#cbd5e1', mt: 0.3 }}>{r.observation}</Typography>
          <Typography sx={{ fontSize: 10, color: '#9aa0aa', mt: 0.2 }}>
            권장 조치 · {r.recommendedAction}
          </Typography>
          <Stack direction="row" spacing={1} sx={{ mt: 0.8 }}>
            <Button size="small" variant="outlined" color="warning" onClick={() => act(r)}
              sx={{ flex: 1, minHeight: 32, fontSize: 10 }}>조치 실행 (승인)</Button>
            <Button size="small" variant="text" color="inherit"
              onClick={() => setReportStatus(r.id, 'dismissed')}
              sx={{ minHeight: 32, fontSize: 10 }}>확인</Button>
          </Stack>
        </Box>
      ))}
      {done.length > 0 && (
        <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
          <Typography sx={{ fontSize: 9, color: '#4b5563', mb: 0.4 }}>처리됨</Typography>
          {done.map(r => (
            <Typography key={r.id} sx={{ fontSize: 9, color: '#5b6677' }}>
              {r.status === 'acted' ? '✓ 조치' : '— 확인'} · {r.title}
            </Typography>
          ))}
        </Box>
      )}
    </Box>
  )
}

export default function RightPanel() {
  const sel = useSignalStore(s => s.selection)
  const uiMode = useUiMode()
  const [tab, setTab] = useState('inspect')
  const reportOpen = useSignalStore(s => (s.report || []).filter(r => r.status === 'open').length)
  const focus = useSignalStore(s => s.focus)            // 클릭한 주목 부품(전 화면 일관)
  const setFocus = useSignalStore(s => s.setFocus)

  if (uiMode === 'operator') {
    return (
      <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', p: 1.2,
        bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 2,
        fontFamily: "'Courier New', monospace" }}>
        {/* 탭: 검사 / 설비 / 보고서 */}
        <ToggleButtonGroup size="small" exclusive value={tab}
          onChange={(_, v) => v && setTab(v)} fullWidth sx={{ mb: 1 }}>
          <ToggleButton value="inspect" sx={{ fontSize: 10, py: 0.4 }}>검사</ToggleButton>
          <ToggleButton value="assets" sx={{ fontSize: 10, py: 0.4 }}>설비</ToggleButton>
          <ToggleButton value="report" sx={{ fontSize: 10, py: 0.4 }}>
            보고서{reportOpen ? ` (${reportOpen})` : ''}
          </ToggleButton>
        </ToggleButtonGroup>

        <Box sx={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
          {tab === 'inspect' && <>
            {focus ? <ScanResult scan={focus} onClear={() => setFocus(null)} /> : <LineSummary />}
            <PredictiveCards />
          </>}
          {tab === 'assets' && <AssetHealthPanel />}
          {tab === 'report' && <ReportPanel />}
        </Box>
      </Box>
    )
  }

  // Expert: 트리 선택 컨텍스트
  let body
  if (!sel) body = <Typography sx={{ fontSize: 12, color: '#6b7280' }}>좌측 계층에서 선택하세요.</Typography>
  else if (sel.group === 'line') body = <LineCtx id={sel.id} />
  else if (sel.group === 'node') body = <NodeCtx id={sel.id} />
  else if (sel.group === 'twin') body = (
    <>
      <Typography sx={head}>TWIN · {sel.id}</Typography>
      <Typography sx={{ fontSize: 12, color: '#9aa0aa' }}>
        동시 송출. 외부 실연동은 pip install asyncua paho-mqtt 후.
      </Typography>
    </>
  )
  else body = <Typography sx={{ ...head }}>{String(sel.group).toUpperCase()} · {sel.id}</Typography>

  return (
    <Box sx={{ height: '100%', overflowY: 'auto', p: 1.2,
      bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 2,
      fontFamily: "'Courier New', monospace" }}>
      {body}
    </Box>
  )
}
