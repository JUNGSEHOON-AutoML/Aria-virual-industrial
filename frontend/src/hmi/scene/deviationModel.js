// deviationModel — ② 가상-현실 편차 → 병목 진단(순수, 헤드리스 검증).
// 라인/스테이션 기대 베이스라인(공칭)과 실 메트릭(async_pipeline queue/tact/drop)을 비교.
// 실이 기대×임계 초과 → BOTTLENECK. 초기엔 단순 기대-비율 모델(풀 물리 sim 불필요).

// 비전 검사 스테이션 공칭치(line_hz=6, patchcore tact ~170ms 기준).
export const STATION_BASELINE = {
  vision_station: { tact_ms: 180, queue: 1, queue_cap: 4 },
}

const CFG = { qMult: 2.5, tMult: 1.6 }   // 큐 2.5배·tact 1.6배 초과 시 병목

// kpi(inspector_state) + baseline → { bottleneck, severity(0..1), ratio, reason }
export function evaluateDeviation(kpi = {}, base = STATION_BASELINE.vision_station, cfg = CFG) {
  const queue = kpi.queue_depth ?? 0
  const tact = kpi.tact_time_ms ?? 0
  const drop = kpi.drop_count ?? 0
  const running = String(kpi.state || '').toLowerCase().startsWith('run')

  const qRatio = base.queue > 0 ? queue / base.queue : 0
  const tRatio = base.tact_ms > 0 ? tact / base.tact_ms : 0

  const qHit = queue >= Math.ceil(base.queue * cfg.qMult)   // 큐 적체
  const tHit = tact > base.tact_ms * cfg.tMult               // tact 지연
  const dHit = drop > 0                                       // 드롭(백프레셔 한계)
  const bottleneck = running && (qHit || tHit || dHit)

  const reasons = []
  if (qHit) reasons.push(`큐 적체 ${queue}/${base.queue_cap}`)
  if (tHit) reasons.push(`tact ${tact.toFixed(0)}ms(기대 ${base.tact_ms})`)
  if (dHit) reasons.push(`드롭 ${drop}`)

  // 심각도: 큐 포화 + tact 비율
  const severity = Math.max(0, Math.min(1,
    0.5 * (queue / (base.queue_cap || 4)) + 0.5 * Math.max(0, tRatio - 1)))

  return { bottleneck, severity: Number(severity.toFixed(2)), qRatio: Number(qRatio.toFixed(2)),
    tRatio: Number(tRatio.toFixed(2)), reason: reasons.join(' · '), queue, tact, drop }
}
