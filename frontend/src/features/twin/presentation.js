// Presentation only: never writes interpolated poses or derived metrics to the engine.
export const damping = (dt, lambda = 10) => 1 - Math.exp(-lambda * Math.max(0, dt))
export const finite = value => typeof value === 'number' && Number.isFinite(value)
export function formatValue(value, digits = 0, suffix = '') {
  return finite(value) ? value.toLocaleString('en-US', { maximumFractionDigits: digits }) + suffix : 'N/A'
}
export function projectParts(snapshot) {
  const nodes = new Map(snapshot.model.components.map(c => [c.id, c])), offsets = new Map()
  return (snapshot.parts || []).slice(0, 2000).flatMap(p => {
    const c = nodes.get(p.component)
    if (!c) return []
    const i = offsets.get(c.id) || 0; offsets.set(c.id, i + 1)
    let x = (Math.floor(i / 3) % 4 - 1.5) * .25, y = 1, z = (i % 3 - 1) * .3
    if (c.kind === 'Machine') z += .3
    if (c.kind === 'Conveyor') x += (Math.min(1, Math.max(0, (snapshot.time - p.entered) / Math.max(.01, p.due - p.entered))) - .5) * c.length
    if (p.robot?.attached) {
      const t = p.robot.tcp
      if (c.kind === 'Machine') { x = .45 - t[0]; y = .65 + t[2]; z = 2.05 + t[1] }
      else { x = -.6 + t[0]; y = .99 + t[2]; z = -.35 - t[1] }
    }
    const a = c.rotation || 0
    const position = [c.position[0] + x * Math.cos(a) + z * Math.sin(a), c.position[1] + y, c.position[2] - x * Math.sin(a) + z * Math.cos(a)]
    // Spawn at the latest real source, then damp toward the server-derived target.
    const move = [...(snapshot.moves || [])].reverse().find(m => m.part === p.id && m.source)
    const source = nodes.get(move?.source)
    return [{ id: p.id, position, origin: source ? [source.position[0], source.position[1] + 1, source.position[2]] : position, verdict: p.verdict }]
  })
}
export function reconcilePoses(previous, snapshot) {
  const reset = previous.run !== snapshot.run_token || snapshot.time < previous.time
  const advance = reset || snapshot.time !== previous.time
  return { run: snapshot.run_token, time: snapshot.time, reset, advance,
    targets: advance ? projectParts(snapshot) : previous.targets }
}
export function engineEvents(snapshot) {
  const duplicate = new Map()
  return (snapshot?.events || []).map(e => {
    const key = JSON.stringify(e), n = duplicate.get(key) || 0; duplicate.set(key, n + 1)
    return { id: `${snapshot.run_token}:${key}:${n}`, source: 'DES', time: e.time, component: e.component,
      title: e.type.replaceAll('_', ' '), detail: [e.part, e.state, e.event, e.verdict].filter(Boolean).join(' · '), payload: e }
  }).reverse()
}
// Only structured backend evidence may select an asset; answer prose is not parsed.
export function evidenceComponent(result, ids) {
  const candidates = [result.evidence?.component]
  for (const t of result.trace || []) {
    if (t.tool === 'get_bottleneck_analysis' || t.tool === 'run_scenario') {
      const r = t.result
      const rows = Array.isArray(r) ? r : r?.bottlenecks
      if (Array.isArray(rows)) candidates.push(rows[0]?.component, rows[0]?.id)
    }
  }
  return candidates.find(id => ids.includes(id)) || null
}
