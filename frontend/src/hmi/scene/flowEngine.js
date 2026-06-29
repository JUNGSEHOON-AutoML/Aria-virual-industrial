// Material Flow Engine — WS 구동(가짜 분류 제거). 순수 JS, 물리엔진 X.
// 부품은 실 inspector_result(verdict OK/NG)가 들어올 때만 spawnFromResult로 생성된다.
// tick()은 기존 부품의 위상 전진만 담당 — Math.random/LCG 분류 없음(Prompt 1: 실데이터 강제).
// 위상: conveyor → dwell(booth) → exit → ok_lane|ng_lane → done
export function createQCFlowEngine(cfg = {}) {
  const C = {
    conveyorMs: 3200, dwellMs: 1400, exitMs: 700, laneMs: 2000,
    maxActiveParts: 24, ...cfg,
  }

  let nextId = 0
  const parts = []
  const counts = { ok: 0, ng: 0, total: 0 }
  const seen = new Set()   // part_id 중복 스폰 방지

  // 실 검사 결과 1건 → 부품 1개(실 verdict 보유). 랜덤 없음.
  function spawnFromResult(scan) {
    if (!scan || !scan.part_id) return
    const v = scan.verdict
    if (v !== 'OK' && v !== 'NG') return          // SKIPPED/ERROR 등은 라인에 안 띄움
    if (seen.has(scan.part_id)) return
    seen.add(scan.part_id)
    if (seen.size > 256) seen.clear()             // 메모리 가드
    if (activeParts() >= C.maxActiveParts) return
    parts.push({ id: ++nextId, partId: scan.part_id, phase: 'conveyor', t: 0, dwellT: 0, verdict: v })
    counts.total++
    if (v === 'OK') counts.ok++; else counts.ng++
  }

  function activeParts() { return parts.filter(p => p.phase !== 'done').length }

  // dtMs만큼 위상 전진(스폰/분류 없음)
  function tick(dtMs) {
    for (const p of parts) {
      if (p.phase === 'done') continue
      switch (p.phase) {
        case 'conveyor':
          p.t = Math.min(1, p.t + dtMs / C.conveyorMs)
          if (p.t >= 1) { p.phase = 'dwell'; p.t = 0; p.dwellT = 0 }
          break
        case 'dwell':
          p.dwellT += dtMs
          if (p.dwellT >= C.dwellMs) { p.phase = 'exit'; p.t = 0 }   // verdict는 이미 실데이터
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
    // 완료 부품 최대 6개 잔류
    const done = parts.reduce((acc, _, i) => parts[i].phase === 'done' ? [...acc, i] : acc, [])
    if (done.length > 6) for (let i = done.length - 1; i >= 6; i--) parts.splice(done[i], 1)
  }

  return {
    get parts() { return parts },
    get counts() { return { ...counts } },
    tick, spawnFromResult,
    setConfig(patch) { Object.assign(C, patch) },
  }
}
