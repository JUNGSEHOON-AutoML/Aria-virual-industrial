// signalStore (zustand) — 단일 WS·단일 ingest = "모든 신호의 유일한 지점".
// reducer 기반 구조화 상태 + (구 twinStore 호환) raw 타입 팬아웃을 동시에 제공한다.
import { create } from 'zustand'
import { initialState, applyMessage } from './signalReducer'
import { DATA_ROOT } from './sceneModel'
import { pushType, subscribeType, getLatestType } from './signalFanout'
import {
  getWebSocketUrl,
  inspectorStart, inspectorStop, inspectorSetLatency,
  classTrain, classValidate, analyzeImage, mvtecScan, intakeDataset, sendAction,
} from '../api/apiClient'

let ws = null

export const useSignalStore = create((set, get) => ({
  ...initialState,

  // ── WS 수집 (단일 연결) ──
  connect: () => {
    if (ws) return
    try {
      set({ wsStatus: 'connecting' })
      ws = new WebSocket(getWebSocketUrl())
      ws.onopen = () => set({ wsStatus: 'open' })
      ws.onclose = () => { set({ wsStatus: 'closed' }); ws = null; setTimeout(() => get().connect(), 3000) }
      ws.onerror = () => { try { ws && ws.close() } catch {} }
      ws.onmessage = (e) => { let d; try { d = JSON.parse(e.data) } catch { return } get().ingest(d) }
    } catch { set({ wsStatus: 'closed' }) }
  },
  // 단일 ingest가 (1) 구조화 상태와 (2) raw 팬아웃을 모두 구동
  ingest: (msg) => {
    const patch = applyMessage(get(), msg); if (patch) set(patch)
    pushType(msg)
  },
  send: (obj) => { try { if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj)) } catch {} },

  // ── 로컬 상태 ──
  select: (group, id) => set({ selection: { group, id } }),
  setMode: (mode) => set({ mode }),
  clearAlarms: () => set({ alarms: [] }),
  loadClasses: async () => {
    try { const r = await mvtecScan(DATA_ROOT); if (r?.ok) set({ classes: r.classes || [] }) } catch {}
  },

  // ── API 액션 (apiClient 래핑 — UI는 이것만 호출) ──
  startNode: (opts) => inspectorStart(opts),
  stopNode: () => inspectorStop(),
  setLatency: (o) => inspectorSetLatency(o),
  trainClass: (c, p) => classTrain(c, p),
  validateClass: (c, p) => classValidate(c, p),
  analyze: (f) => analyzeImage(f, true),
  scanMvtec: (root) => mvtecScan(root),
  intake: (f) => intakeDataset(f),
  action: (a) => sendAction(a),
}))

// ── 구 twinStore 호환 API(단일 WS 위에서) ──
export { subscribeType, getLatestType }
export function ensureConnected() { useSignalStore.getState().connect() }
export function send(obj) { useSignalStore.getState().send(obj) }
export function getStatus() { return useSignalStore.getState().wsStatus }
let _lastStatus = null
export function subscribeStatus(cb) {
  return useSignalStore.subscribe((s) => {
    if (s.wsStatus !== _lastStatus) { _lastStatus = s.wsStatus; try { cb(s.wsStatus) } catch {} }
  })
}
