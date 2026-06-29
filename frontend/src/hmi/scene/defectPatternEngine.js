// defectPatternEngine — 실 inspector_result 시간·위치 집계 → 예지보전 가설(순수, 헤드리스 검증).
//
// 좌표 계약: uv(defect_xy)는 "정렬된 부품 표면 UV"여야 한다. PatchCore는 부품 크롭에 추론하므로
//   heatmap (u,v)는 이미 부품 프레임이다. ⚠ 실카메라+이동/회전 부품이면 T1-A 정렬/역투영을 거친
//   표면 UV를 넘길 것 — 원본 이미지 픽셀 cell로 집계하면 같은 물리 위치를 안 가리켜 오탐난다.
//
// 규칙: 셀당 [주] 윈도우 K/M, [보조] 연속 streak. 쿨다운은 cell 단위(전역 아님).
// 신뢰도: 빈도에서 유도(Wilson 하한, 표본 적으면 낮음). ★통계(위치 집중)와 인과(가설)는 분리.
// 난수 금지 · verdict 로직 불변(여기선 verdict 소비만).

const DEFAULTS = { window: 5, kOfWindow: 4, streakN: 3, cooldownMs: 15000, maxConf: 0.6, z: 1.96 }

// 클래스별 격자 해상도 — 결함 공간 스케일 차이 반영(큰 표면 세밀 / 작은 부품 거침)
const CLASS_GRID = {
  carpet: 6, tile: 6, leather: 6, wood: 6, grid: 6, foam: 5,
  screw: 2, metal_nut: 2, cable_gland: 2,
}
export function gridForClass(name) {
  return CLASS_GRID[String(name || '').toLowerCase()] ?? 4
}

// uv[0..1]=[u,v] → [row, col] (v=세로, u=가로)
function quantize(uv, g) {
  const c = (v) => Math.min(g - 1, Math.max(0, Math.floor(v * g)))
  return [c(uv[1]), c(uv[0])]
}

// 위치 집중 통계 신뢰도(인과 아님). Wilson 하한: 같은 비율이라도 표본 적으면 낮게.
export function statConfidence(ng, total, { maxConf = 0.6, z = 1.96 } = {}) {
  if (total <= 0) return 0
  const ratio = ng / total
  const denom = 1 + (z * z) / total
  const center = ratio + (z * z) / (2 * total)
  const margin = z * Math.sqrt(ratio * (1 - ratio) / total + (z * z) / (4 * total * total))
  const lower = (center - margin) / denom
  return Math.max(0, Math.min(maxConf, Number(lower.toFixed(3))))
}

// cell 위치 → 인과 가설(휴리스틱, 미검증). 숫자 신뢰도 부여 금지.
function causalHypothesis(row, g) {
  // 상단행=정렬/이송, 하단행=치구/그리퍼 — 어디까지나 가설
  const band = row / Math.max(1, g - 1)
  if (band < 0.34) return { hypothesis: '이송 정렬/카메라 정합 편차 의심', assetHint: 'vision_camera' }
  if (band > 0.66) return { hypothesis: '치구/그리퍼·로봇 관절 마모 의심', assetHint: 'robot_arm' }
  return { hypothesis: '컨베이어 이송/픽업 편차 의심', assetHint: 'conveyor_motor' }
}

export function createDefectPatternEngine(cfg = {}) {
  const C = { ...DEFAULTS, ...cfg }
  const cells = new Map()      // cellId -> { ng, total, streak, window:[bool], row, col, g, cls }
  const cooldown = new Map()   // cellId -> until(ms)  (★cell 단위)

  // 실 inspector_result 1건. opts.className(=liveCategory), opts.nowMs.
  function observe(scan, opts = {}) {
    if (!scan || !Array.isArray(scan.defect_xy)) return null
    const v = scan.verdict
    if (v !== 'OK' && v !== 'NG') return null         // SKIPPED/ERROR 제외
    const cls = opts.className || scan.class || 'part'
    const g = gridForClass(cls)
    const [row, col] = quantize(scan.defect_xy, g)
    const cellId = `${cls}:${row},${col}`
    const now = opts.nowMs ?? 0
    const isNG = v === 'NG'

    let rec = cells.get(cellId)
    if (!rec) { rec = { ng: 0, total: 0, streak: 0, window: [], row, col, g, cls }; cells.set(cellId, rec) }

    // 해당 cell에만 갱신(다른 cell 이벤트는 이 cell streak/window 불변)
    rec.total += 1
    if (isNG) { rec.ng += 1; rec.streak += 1 } else { rec.streak = 0 }
    rec.window = [...rec.window, isNG].slice(-C.window)

    const ngInWin = rec.window.filter(Boolean).length
    const windowTrigger = rec.window.length >= C.kOfWindow && ngInWin >= C.kOfWindow   // 주: K/M
    const streakTrigger = rec.streak >= C.streakN                                       // 보조
    if (!windowTrigger && !streakTrigger) return null

    // 쿨다운(cell 단위) — 다른 cell 가설을 막지 않음
    const until = cooldown.get(cellId) || 0
    if (now < until) return null
    cooldown.set(cellId, now + C.cooldownMs)

    const stat = statConfidence(rec.ng, rec.total, C)   // 위치 집중(통계, 누적 표본)
    const cause = causalHypothesis(row, g)
    return {
      cell: cellId, class: cls, row, col, grid: g,
      count: ngInWin, window: `${ngInWin}/${rec.window.length}`,
      streak: rec.streak, ngTotal: rec.ng, total: rec.total,
      statConfidence: stat,                              // 숫자 — "위치 집중 신뢰도"
      causal: { ...cause, verified: false },             // 인과 — 가설·미검증(숫자 신뢰도 없음)
      recommendedAction: '해당 셀 점검 · 재교정(승인 후)',
      trigger: windowTrigger ? 'window' : 'streak',
      ts: now,
    }
  }

  return {
    observe,
    get cells() { return cells },
    reset() { cells.clear(); cooldown.clear() },
    setConfig(p) { Object.assign(C, p) },
  }
}
