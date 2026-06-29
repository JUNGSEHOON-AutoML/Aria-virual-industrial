// Material Flow Engine — 공정 충실 QC 라인 부품 흐름 (순수 JS, 물리엔진 X)
// 위상: conveyor → dwell(booth) → exit → ok_lane|ng_lane → done
// tick(dtMs, latestScan?) 호출마다 부품 상태 갱신. verdict는 latestScan 혹은 seededRNG.

export function createQCFlowEngine(cfg = {}) {
  const C = {
    spawnIntervalMs: 3500,
    conveyorMs: 3200,
    dwellMs: 2600,
    exitMs: 700,
    laneMs: 2000,
    maxActiveParts: 18,
    defectRate: 0.18,
    ...cfg
  }

  let nextId = 0
  let spawnTimer = C.spawnIntervalMs * 0.6
  const parts = []
  const counts = { ok: 0, ng: 0, total: 0 }

  function activeParts() {
    return parts.filter(p => p.phase !== 'done').length
  }

  function tick(dtMs, latestScan) {
    spawnTimer += dtMs
    if (spawnTimer >= C.spawnIntervalMs && activeParts() < C.maxActiveParts) {
      spawnTimer = 0
      parts.push({ id: ++nextId, phase: 'conveyor', t: 0, verdict: null, dwellT: 0 })
      counts.total++
    }

    for (const p of parts) {
      if (p.phase === 'done') continue

      switch (p.phase) {
        case 'conveyor':
          p.t = Math.min(1, p.t + dtMs / C.conveyorMs)
          if (p.t >= 1) { p.phase = 'dwell'; p.t = 0; p.dwellT = 0 }
          break

        case 'dwell':
          p.dwellT += dtMs
          if (p.dwellT >= C.dwellMs) {
            const useLive = latestScan && latestScan.verdict &&
              latestScan.verdict !== 'SKIPPED'
            p.verdict = useLive
              ? latestScan.verdict
              : (_lcg() < C.defectRate ? 'NG' : 'OK')
            if (p.verdict === 'OK') counts.ok++; else counts.ng++
            p.phase = 'exit'; p.t = 0
          }
          break

        case 'exit':
          p.t = Math.min(1, p.t + dtMs / C.exitMs)
          if (p.t >= 1) { p.phase = p.verdict === 'NG' ? 'ng_lane' : 'ok_lane'; p.t = 0 }
          break

        case 'ok_lane':
        case 'ng_lane':
          p.t = Math.min(1, p.t + dtMs / C.laneMs)
          if (p.t >= 1) { p.phase = 'done'; p.t = 1 }
          break
      }
    }

    // 완료 부품은 최대 6개만 잔류(시각 적재 효과)
    const done = parts.reduce((acc, _, i) => parts[i].phase === 'done' ? [...acc, i] : acc, [])
    if (done.length > 6) {
      for (let i = done.length - 1; i >= 6; i--) parts.splice(done[i], 1)
    }
  }

  // 간단한 LCG(seeded pseudo-random) — Math.random 사용 금지 아닌 경우 단순화
  let _seed = 12345
  function _lcg() {
    _seed = (_seed * 1664525 + 1013904223) & 0xffffffff
    return ((_seed >>> 0) / 0xffffffff)
  }

  return {
    get parts() { return parts },
    get counts() { return { ...counts } },
    tick,
    setConfig(patch) { Object.assign(C, patch) }
  }
}
