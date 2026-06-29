// signalFanout — 순수 타입 팬아웃(browser 의존 없음 → Node 헤드리스 검증 가능).
// signalStore.ingest가 이걸 구동하여 "raw 타입 구독"(구 twinStore API)을 단일 WS 위에서 제공한다.
const typeSubs = new Map()   // type -> Set(cb)
const typeLatest = new Map() // type -> last raw msg

export function pushType(msg) {
  const t = msg && msg.type
  if (!t) return
  typeLatest.set(t, msg)
  const s = typeSubs.get(t); if (s) s.forEach(cb => { try { cb(msg) } catch {} })
  const a = typeSubs.get('*'); if (a) a.forEach(cb => { try { cb(msg) } catch {} })
}
export function subscribeType(type, cb) {
  if (!typeSubs.has(type)) typeSubs.set(type, new Set())
  typeSubs.get(type).add(cb)
  return () => { const s = typeSubs.get(type); if (s) s.delete(cb) }
}
export function getLatestType(type) { return typeLatest.get(type) }
export function _resetFanout() { typeSubs.clear(); typeLatest.clear() }
