// 게임형 공장 공정 시뮬 엔진 (순수 JS, 물리 없음).
// 목적: 데이터 없는 환경에서 24h 공정을 돌려 효율(처리량/가동률/병목)을 보고 최적화.
// 부품 흐름: inbound 큐 → 로봇 검사셀(점유) → 검사(inspectMs) → 분류(OK/NG) → 출고.
// 시드 RNG로 결정적 → 헤드리스 검증 가능.

function mulberry32(seed) {
  let a = seed >>> 0
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export const DEFAULT_CFG = {
  nCells: 4,          // 로봇 검사셀 수
  spawnEveryMs: 1200, // 부품 인입 간격(sim ms)
  travelMs: 1500,     // 이동(인입→셀, 셀→분류) 시간
  inspectMs: 2600,    // 셀당 검사 시간
  defectRate: 0.12,   // 공정 불량 가정치(데이터 없을 때 튜닝 대상)
  speed: 120,         // sim ms per real ms (×) — 시간 가속
  seed: 12345,
}

export function createFactorySim(cfg = {}) {
  const c = { ...DEFAULT_CFG, ...cfg }
  const rng = mulberry32(c.seed)
  let pid = 0
  const s = {
    cfg: c,
    timeMs: 0,
    nextSpawn: 0,
    inbound: [],   // {id} 대기 부품
    parts: [],     // 모든 활성 부품 {id, stage, cell, progress, verdict}
    cells: Array.from({ length: c.nCells }, (_, i) => ({ id: i, part: null, t: 0, busyMs: 0 })),
    produced: 0, ok: 0, ng: 0,
    queuePeak: 0,
  }

  function setConfig(patch) {
    Object.assign(s.cfg, patch)
    // 셀 수 변경 반영
    if (patch.nCells != null && patch.nCells !== s.cells.length) {
      const n = Math.max(1, patch.nCells | 0)
      if (n > s.cells.length) {
        for (let i = s.cells.length; i < n; i++) s.cells.push({ id: i, part: null, t: 0, busyMs: 0 })
      } else {
        s.cells = s.cells.slice(0, n)
      }
    }
  }

  function spawn() {
    const p = { id: ++pid, stage: 'inbound', cell: -1, progress: 0, verdict: null }
    s.parts.push(p)
    s.inbound.push(p)
  }

  function tick(realDtMs) {
    const dt = Math.max(0, realDtMs) * s.cfg.speed   // sim ms
    s.timeMs += dt

    // 인입
    s.nextSpawn -= dt
    while (s.nextSpawn <= 0) { spawn(); s.nextSpawn += s.cfg.spawnEveryMs }

    // 대기 → 유휴 셀 배정
    for (const cell of s.cells) {
      if (!cell.part && cell.reserved == null && s.inbound.length) {
        const p = s.inbound.shift()
        p.stage = 'toCell'; p.cell = cell.id; p.progress = 0
        cell.reserved = p
      }
    }
    s.queuePeak = Math.max(s.queuePeak, s.inbound.length)

    // 부품 단계 진행
    for (const p of s.parts) {
      if (p.stage === 'toCell') {
        p.progress += dt / s.cfg.travelMs
        if (p.progress >= 1) {
          p.progress = 1; p.stage = 'inspect'
          const cell = s.cells[p.cell]
          if (cell) { cell.part = p; cell.reserved = null; cell.t = 0 }
        }
      } else if (p.stage === 'toSort') {
        p.progress += dt / s.cfg.travelMs
        if (p.progress >= 1) { p.progress = 1; p.stage = 'done'; p.doneAt = s.timeMs }
      }
    }

    // 셀 검사 진행
    for (const cell of s.cells) {
      if (cell.part) {
        cell.t += dt; cell.busyMs += dt
        if (cell.t >= s.cfg.inspectMs) {
          const p = cell.part
          p.verdict = rng() < s.cfg.defectRate ? 'NG' : 'OK'
          p.stage = 'toSort'; p.progress = 0
          s.produced++; if (p.verdict === 'NG') s.ng++; else s.ok++
          cell.part = null; cell.t = 0
        }
      }
    }

    // done 부품 정리(잠깐 보였다 사라짐)
    s.parts = s.parts.filter(p => !(p.stage === 'done' && s.timeMs - (p.doneAt || 0) > 800))
  }

  function metrics() {
    const hours = s.timeMs / 3600000 || 1e-9
    const throughput = s.produced / hours                    // parts/h
    const util = s.cells.length
      ? s.cells.reduce((a, cl) => a + cl.busyMs, 0) / (s.timeMs * s.cells.length || 1)
      : 0                                                     // 셀 평균 가동률(OEE 근사)
    const defect = s.produced ? s.ng / s.produced : 0
    const queue = s.inbound.length
    // 병목: 큐가 계속 차면 셀(검사) 병목, 셀이 자주 비면 인입 병목
    const bottleneck = util > 0.9 && queue > s.cells.length ? 'inspect' : (util < 0.6 ? 'feed' : 'balanced')
    return {
      timeMs: s.timeMs,
      throughput: Math.round(throughput),
      oee: +(util * 100).toFixed(1),
      defect: +(defect * 100).toFixed(1),
      queue, queuePeak: s.queuePeak,
      produced: s.produced, ok: s.ok, ng: s.ng,
      cells: s.cells.length,
      bottleneck,
    }
  }

  return { state: s, tick, metrics, setConfig }
}

// sim ms → "HH:MM" (24h 시계)
export function formatSimClock(timeMs) {
  const totalMin = Math.floor(timeMs / 60000) % (24 * 60)
  const h = Math.floor(totalMin / 60), m = totalMin % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}
