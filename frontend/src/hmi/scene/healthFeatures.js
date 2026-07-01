// healthFeatures.js — 백엔드 health_features.py 미러(T1-C C1). 순수·결정론적.
// 동일 규칙으로 프론트에서도 특징 산출 가능(Node 헤드리스 검증). 블랙박스 금지.
// rows: [{ts(초), temp_c, vib_rms_mm_s, infer_p95_ms, drop_rate}]

export const NMIN = 4
const MS_PER_HR = 3600000

function lstsqSlope(tsMs, ys) {
  const n = tsMs.length
  if (n < 2) return null
  const xs = tsMs.map(t => (t - tsMs[0]) / MS_PER_HR)
  const mx = xs.reduce((a, b) => a + b, 0) / n
  const my = ys.reduce((a, b) => a + b, 0) / n
  const sxx = xs.reduce((a, x) => a + (x - mx) ** 2, 0)
  if (sxx <= 1e-12) return null
  const sxy = xs.reduce((a, x, i) => a + (x - mx) * (ys[i] - my), 0)
  return sxy / sxx
}

function median(xs) {
  if (!xs.length) return 0
  const s = [...xs].sort((a, b) => a - b)
  const m = s.length >> 1
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}

function mad(xs, med) {
  if (!xs.length) return 0
  return 1.4826 * median(xs.map(x => Math.abs(x - med)))
}

function zScore(xs, base) {
  if (base == null || !xs.length) return null
  const med = median(xs)
  const m = mad(xs, med)
  if (m <= 1e-9) return 0
  return (med - base) / m
}

const r4 = v => (v == null ? null : Math.round(v * 1e4) / 1e4)

export function extract(rows, baseline = null, nmin = NMIN) {
  const n = rows.length
  if (n === 0) return { n: 0, rms_level: null, rms_slope: null, temp_slope: null, p95_creep: null, drop_trend: null, z: {}, baseline: {} }

  const tsMs = rows.map(r => Number(r.ts || 0) * 1000)
  const vib = rows.map(r => Number(r.vib_rms_mm_s || 0))
  const temp = rows.map(r => Number(r.temp_c || 0))
  const p95 = rows.map(r => Number(r.infer_p95_ms || 0))
  const drop = rows.map(r => Number(r.drop_rate || 0))

  const enough = n >= nmin
  const base = baseline || { rms_level: median(vib), temp_c: median(temp), infer_p95_ms: median(p95), drop_rate: median(drop) }
  const z = {}
  if (enough) {
    z.rms_level = zScore(vib, base.rms_level)
    z.temp_c = zScore(temp, base.temp_c)
    z.infer_p95_ms = zScore(p95, base.infer_p95_ms)
    z.drop_rate = zScore(drop, base.drop_rate)
  }

  return {
    n,
    rms_level: r4(median(vib)),
    rms_slope: r4(enough ? lstsqSlope(tsMs, vib) : null),
    temp_slope: r4(enough ? lstsqSlope(tsMs, temp) : null),
    p95_creep: r4(enough ? lstsqSlope(tsMs, p95) : null),
    drop_trend: r4(enough ? lstsqSlope(tsMs, drop) : null),
    z: Object.fromEntries(Object.entries(z).map(([k, v]) => [k, r4(v)])),
    baseline: Object.fromEntries(Object.entries(base).map(([k, v]) => [k, r4(v)])),
  }
}
