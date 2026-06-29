// signalStore (zustand) — "모든 API 재연결의 단일 지점".
// UI 컴포넌트는 fetch/ws를 직접 호출하지 않고 이 store만 구독/호출한다(스펙 §5, DO/DON'T).
import { create } from 'zustand'
import { initialState, applyMessage } from './signalReducer'
import { DATA_ROOT } from './sceneModel'
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
  ingest: (msg) => { const patch = applyMessage(get(), msg); if (patch) set(patch) },

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
