// RightPanel — operator: [검사 결과 | 설비 건전성] 탭 / expert: 트리 선택 컨텍스트.
import { useEffect, useState } from 'react'
import { Box, Typography, Button, Stack, ToggleButtonGroup, ToggleButton } from '@mui/material'
import { useSignalStore } from '../signalStore'
import { classSamples } from '../../api/apiClient'
import { DATA_ROOT } from '../sceneModel'
import { useUiMode } from '../uiMode'
import { deriveAssets, statusColor, statusKo, faultyAssets } from '../scene/assetModel'
import { buildVlmReport } from '../scene/vlmReport'

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

// ── G1: Anomaly Score 비교 게이지 (한국어 라벨) ────────────────────────
function ScoreGauge({ score, tau }) {
  if (score == null) return null
  const t = tau ?? 0.5
  const max = Math.max(1.0, 2 * t)
  const tauPct = Math.min(100, (t / max) * 100)
  const scorePct = Math.min(100, Math.max(0, (score / max) * 100))
  const isOK = score < t
  const mc = isOK ? '#34d399' : '#f87171'

  return (
    <Box sx={{ mt: 1.5, pt: 1.5, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
      <Typography sx={{ fontSize: 9, color: '#6b7280', letterSpacing: 0.5, mb: 0.8 }}>
        점수 비교
      </Typography>

      {/* 점수 표시 */}
      <Typography sx={{ fontSize: 16, fontWeight: 700, color: mc, mb: 0.5,
        fontFamily: "'Courier New', monospace" }}>
        {score.toFixed(3)}
      </Typography>

      {/* 게이지 트랙 */}
      <Box sx={{ height: 14, position: 'relative', borderRadius: 1, mb: 0.4 }}>
        {/* OK 구간 [0, τ) */}
        <Box sx={{ position: 'absolute', top: 0, left: 0, bottom: 0,
          width: `${tauPct}%`, borderRadius: '4px 0 0 4px',
          bgcolor: 'rgba(52,211,153,0.22)', border: '1px solid rgba(52,211,153,0.38)' }} />
        {/* NG 구간 [τ, max] */}
        <Box sx={{ position: 'absolute', top: 0, bottom: 0, right: 0,
          left: `${tauPct}%`, borderRadius: '0 4px 4px 0',
          bgcolor: 'rgba(248,113,113,0.14)', border: '1px solid rgba(248,113,113,0.30)' }} />
        {/* τ 눈금 */}
        <Box sx={{ position: 'absolute', top: -2, bottom: -2, left: `${tauPct}%`,
          width: 2, bgcolor: '#9aa0aa', transform: 'translateX(-1px)' }} />
        {/* 현재 점수 마커 */}
        <Box sx={{ position: 'absolute', top: 1, bottom: 1, left: `${scorePct}%`,
          width: 4, bgcolor: mc, transform: 'translateX(-2px)', borderRadius: 1,
          boxShadow: `0 0 6px ${mc}88` }} />
      </Box>

      {/* 축 레이블 */}
      <Box sx={{ position: 'relative', height: 14, mb: 0.8 }}>
        <Typography sx={{ position: 'absolute', left: 0, bottom: 0, fontSize: 9, color: '#34d399' }}>
          OK
        </Typography>
        <Typography sx={{ position: 'absolute', left: `${tauPct}%`, bottom: 0, fontSize: 9,
          color: '#9aa0aa', transform: 'translateX(-50%)', whiteSpace: 'nowrap' }}>
          {t.toFixed(3)}
        </Typography>
        <Typography sx={{ position: 'absolute', right: 0, bottom: 0, fontSize: 9, color: '#f87171' }}>
          NG
        </Typography>
      </Box>

      {/* 상세 수치 — 낮을수록 정상 이유 명시 */}
      <Box sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 1, px: 1, py: 0.6 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.3 }}>
          <Typography sx={{ fontSize: 10, color: '#6b7280' }}>현재 점수</Typography>
          <Typography sx={{ fontSize: 10, color: mc, fontFamily: "'Courier New', monospace" }}>
            {score.toFixed(3)}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.3 }}>
          <Typography sx={{ fontSize: 10, color: '#6b7280' }}>임계값(T)</Typography>
          <Typography sx={{ fontSize: 10, color: '#9aa0aa', fontFamily: "'Courier New', monospace" }}>
            {t.toFixed(3)}
          </Typography>
        </Box>
        <Typography sx={{ fontSize: 9, color: '#4b5563', mt: 0.2 }}>
          (Anomaly Score — 낮을수록 정상)
        </Typography>
      </Box>
    </Box>
  )
}

// ── Operator: 현재 스캔 결과 집중 표시 ─────────────────────────────────
function ScanResult() {
  const scan = useSignalStore(s => s.scan)
  const det = useSignalStore(s => s.detectors) || {}
  const k = useSignalStore(s => s.kpi) || {}

  const verdict = scan?.verdict
  const isNG = verdict === 'NG'
  const isOK = verdict === 'OK'
  const vColor = isOK ? '#34d399' : isNG ? '#f87171' : '#9aa0aa'

  if (!scan) {
    return (
      <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', gap: 1 }}>
        <span style={{ fontSize: 28, color: '#4b5563' }}>◎</span>
        <Typography sx={{ fontSize: 11, color: '#6b7280', letterSpacing: 1 }}>
          검사 대기 중...
        </Typography>
        {k.state && <Typography sx={{ fontSize: 10, color: '#4b5563' }}>
          INSP {String(k.state).toUpperCase()}
        </Typography>}
      </Box>
    )
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 0.5 }}>
      <Typography sx={head}>검사 결과</Typography>

      {/* 대형 verdict */}
      <Typography sx={{ fontSize: 40, fontWeight: 900, color: vColor, lineHeight: 1,
        letterSpacing: 3, mb: 0.5 }}>
        {verdict}
      </Typography>

      {scan.defect_class && (
        <Row k="DEFECT CLASS" v={scan.defect_class} c="#facc15" />
      )}
      {scan.part_id && <Row k="PART ID" v={scan.part_id} />}

      {/* G1: 점수 비교 게이지 — verdict 로직 불변, 표현만 */}
      <ScoreGauge score={scan?.score} tau={scan?.tau ?? det.patchcore?.tau} />

      {/* PatchCore / YOLO 간이 */}
      {(det.patchcore || det.yolo) && (
        <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
          {det.patchcore && (
            <Row k="PatchCore"
              v={`${det.patchcore.score?.toFixed?.(3)} · ${det.patchcore.verdict}`}
              c={det.patchcore.verdict === 'NG' ? '#f87171' : '#34d399'} />
          )}
          {det.yolo?.defect_class && (
            <Row k="YOLO" v={det.yolo.defect_class} c="#fca5a5" />
          )}
        </Box>
      )}

      {/* VLM 분석 — 가설+신뢰도(확인 요망), 원인 단정 금지 (명세 §4) */}
      <VlmSection scan={scan} />
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

// ── T1-B: 예지보전 가설 카드 (통계 신뢰도 ↔ 인과 가설 분리, 표본 표기, 점검 지시) ──
const ASSET_KO = { robot_arm: '로봇 팔', vision_camera: '비전 카메라', conveyor_motor: '컨베이어 모터' }
function PredictiveCards() {
  const predictions = useSignalStore(s => s.predictions) || []
  const addApproval = useSignalStore(s => s.addApproval)
  const setPredictionStatus = useSignalStore(s => s.setPredictionStatus)
  // 활성(해소/기각 제외)만
  const active = predictions.filter(p => p.status === 'pending' || p.status === 'approved')
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
      <Typography sx={{ ...head, color: '#f0a35a' }}>⚠ 예지보전 — 가설(확인 요망)</Typography>
      {active.map(p => (
        <Box key={p.id} sx={{ mt: 0.8, p: 1, borderRadius: 1.5,
          bgcolor: 'rgba(240,163,90,0.06)', border: '1px solid rgba(240,163,90,0.28)' }}>
          {/* 통계(위치 집중) — 숫자 신뢰도 + 표본 */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <Typography sx={{ fontSize: 11, color: '#e2e8f0' }}>
              위치 집중 <b style={{ color: '#f0a35a' }}>{(p.statConfidence ?? 0).toFixed(2)}</b>
              <span style={{ fontSize: 9, color: '#6b7280' }}> (통계)</span>
            </Typography>
            <Typography sx={{ fontSize: 9, color: '#9aa0aa' }}>
              최근 {p.total}검사 중 {p.ngTotal}회
            </Typography>
          </Box>
          <Typography sx={{ fontSize: 9, color: '#6b7280' }}>
            셀 {p.cell} · {p.status === 'approved' ? '점검 지시됨' : `재발 ${p.occurrences}회`}
          </Typography>
          {/* 실 결함종류(YOLO) — 데이터 사실(가설 아님) */}
          {p.defectClass && (
            <Typography sx={{ fontSize: 11, mt: 0.4 }}>
              <span style={{ color: '#6b7280' }}>반복 결함 · </span>
              <span style={{ color: '#fca5a5' }}>{p.defectClass}</span>
              <span style={{ color: '#9aa0aa' }}> ×{p.defectClassN} (YOLO 검출)</span>
            </Typography>
          )}
          {/* 인과 — 가설·미검증 (숫자 신뢰도 없음, 단정 아님) */}
          <Typography sx={{ fontSize: 11, mt: 0.4 }}>
            <span style={{ color: '#6b7280' }}>추정 원인 · </span>
            <span style={{ color: '#facc15' }}>{p.causal?.hypothesis}</span>
            <span style={{ color: '#9aa0aa' }}> (가설·미검증)</span>
          </Typography>
          {/* 점검 지시 — 원인 확정 아님 */}
          {p.status !== 'approved' ? (
            <Button size="small" variant="outlined" color="warning" fullWidth
              onClick={order(p.id)}
              sx={{ mt: 0.8, minHeight: 34, fontSize: 10 }}>
              점검 지시 (승인 게이트)
            </Button>
          ) : (
            <Typography sx={{ fontSize: 9, color: '#34d399', mt: 0.6 }}>
              ✓ 점검 지시 — 승인 게이트에서 실행 결정
            </Typography>
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
  const open = report.filter(r => r.status === 'open')
  const done = report.filter(r => r.status !== 'open').slice(0, 6)

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
          {tab === 'inspect' && <><ScanResult /><PredictiveCards /></>}
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
