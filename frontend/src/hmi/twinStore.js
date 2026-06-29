// 통합 신호 스토어 (realvirtual signal store 대응)
// 단일 WebSocket 연결 → 모든 메시지 타입을 타입별 구독자에게 팬아웃 + 최신값 캐시.
// 기존 컴포넌트마다 따로 열던 WS를 하나로 통합한다.
import { getWebSocketUrl } from '../api/apiClient'

const subs = new Map()      // type -> Set(cb)
const latest = new Map()    // type -> last message
const statusSubs = new Set()
let ws = null
let status = 'idle'

function setStatus(s) { status = s; statusSubs.forEach(cb => { try { cb(s) } catch {} }) }

function connect() {
  try {
    setStatus('connecting')
    ws = new WebSocket(getWebSocketUrl())
    ws.onopen = () => setStatus('open')
    ws.onclose = () => { setStatus('closed'); ws = null; setTimeout(connect, 3000) }  // 자동 재연결
    ws.onerror = () => { try { ws && ws.close() } catch {} }
    ws.onmessage = (e) => {
      let d
      try { d = JSON.parse(e.data) } catch { return }
      const t = d && d.type
      if (!t) return
      latest.set(t, d)
      const set = subs.get(t)
      if (set) set.forEach(cb => { try { cb(d) } catch {} })
      const any = subs.get('*')
      if (any) any.forEach(cb => { try { cb(d) } catch {} })
    }
  } catch { setStatus('closed'); setTimeout(connect, 3000) }
}

export function ensureConnected() { if (!ws) connect() }

export function subscribe(type, cb) {
  ensureConnected()
  if (!subs.has(type)) subs.set(type, new Set())
  subs.get(type).add(cb)
  return () => { const s = subs.get(type); if (s) s.delete(cb) }
}

export function getLatest(type) { return latest.get(type) }
export function subscribeStatus(cb) { statusSubs.add(cb); return () => statusSubs.delete(cb) }
export function getStatus() { return status }
export function sendCmd(obj) { try { if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj)) } catch {} }
