// signalStore (zustand) — 단일 WS·단일 ingest = "모든 신호의 유일한 지점".
// reducer 기반 구조화 상태 + (구 twinStore 호환) raw 타입 팬아웃을 동시에 제공한다.
import { create } from 'zustand'
import { initialState, applyMessage, upsertPrediction, sweepPredictions, upsertReport, rebuildSceneAt } from './signalReducer'
import { record, snapshot, issueMarkers } from './twinRecorder'
import { DATA_ROOT } from './sceneModel'
import { pushType, subscribeType, getLatestType } from './signalFanout'
import {
  getWebSocketUrl,
  inspectorStart, inspectorStop, inspectorSetLatency, inspectorStartLanes, inspectorStopLanes,
  classTrain, classValidate, analyzeImage, mvtecScan, intakeDataset, sendAction, classesStatus,
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
      ws.onopen = () => { set({ wsStatus: 'open' }); get().loadTrained() }
      ws.onclose = () => { set({ wsStatus: 'closed' }); ws = null; setTimeout(() => get().connect(), 3000) }
      ws.onerror = () => { try { ws && ws.close() } catch {} }
      ws.onmessage = (e) => { let d; try { d = JSON.parse(e.data) } catch { return } get().ingest(d) }
    } catch { set({ wsStatus: 'closed' }) }
  },
  // 단일 ingest가 (1) 구조화 상태와 (2) raw 팬아웃을 모두 구동 + (3) 리플레이 기록
  ingest: (msg) => {
    record(msg)                                   // ① 항상 기록(라이브 백그라운드 버퍼)
    if (get().replay.active) return               // 리플레이 중엔 라이브가 화면 덮지 않음
    const patch = applyMessage(get(), msg); if (patch) set(patch)
    pushType(msg)
  },

  // ── ① 3D 리플레이 블랙박스 ──
  startReplay: () => {
    const frames = snapshot()
    if (frames.length < 2) return
    const t0 = frames[0].ts, t1 = frames[frames.length - 1].ts
    set({ replay: { active: true, frames, t0, t1, t: t1, playing: false, speed: 1, markers: issueMarkers(frames) } })
    set(rebuildSceneAt(frames, t1))
  },
  stopReplay: () => set({ replay: { active: false, frames: [], t: 0, t0: 0, t1: 0, playing: false, speed: 1, markers: [] } }),
  replaySeek: (t) => {
    const r = get().replay; if (!r.active) return
    const tc = Math.max(r.t0, Math.min(r.t1, t))
    set({ replay: { ...r, t: tc } }); set(rebuildSceneAt(r.frames, tc))
  },
  replayPlay: () => set((s) => ({ replay: { ...s.replay, playing: true } })),
  replayPause: () => set((s) => ({ replay: { ...s.replay, playing: false } })),
  replaySpeed: (sp) => set((s) => ({ replay: { ...s.replay, speed: sp } })),
  send: (obj) => { try { if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj)) } catch {} },

  // ── 로컬 상태 ──
  select: (group, id) => set({ selection: { group, id } }),
  setMode: (mode) => set({ mode }),
  clearAlarms: () => set({ alarms: [] }),
  loadClasses: async () => {
    try { const r = await mvtecScan(DATA_ROOT); if (r?.ok) set({ classes: r.classes || [] }) } catch {}
  },
  // F2: 학습 완료(뱅크 보유) 클래스 초기 로드 → trained 상태
  loadTrained: async () => {
    try {
      const r = await classesStatus()
      if (r?.ok) {
        const t = {}; (r.classes || []).forEach(c => { t[c.classId] = { ready: true, ts: c.mtime } })
        set({ trained: t })
      }
    } catch {}
  },

  // ── Agentic 유지보수 트윈(Spec 2) — Simulate-then-Approve ──
  setAgent: (patch) => set((s) => ({ agent: { ...s.agent, ...patch } })),
  agentSay: (text) => set((s) => ({ messages: [{ ts: Date.now(), kind: 'agent', text }, ...s.messages].slice(0, 200) })),
  upsertPrediction: (hyp) => set((s) => ({ predictions: upsertPrediction(s.predictions, hyp) })),
  setPredictionStatus: (id, status) => set((s) => ({
    predictions: s.predictions.map((p) => (p.id === id ? { ...p, status } : p)) })),
  sweepPredictions: (nowMs) => set((s) => ({ predictions: sweepPredictions(s.predictions, nowMs) })),
  addApproval: (req) => set((s) => ({ approvals: [req, ...s.approvals].slice(0, 50) })),
  resolveApproval: (id, status) => set((s) => ({
    approvals: s.approvals.map((a) => (a.id === id ? { ...a, status } : a)) })),
  logEpisode: (ep) => set((s) => ({ episodes: [ep, ...s.episodes].slice(0, 200) })),
  addReport: (entry) => set((s) => ({ report: upsertReport(s.report, entry) })),
  // 자율 해결완료 보고(승인 불필요 — 트윈 내 가상 수리). 실 시스템 변경은 별도 승인 게이트.
  pushResolvedReport: (entry) => set((s) => ({
    report: [{ ...entry, id: `res_${entry.key}_${entry.ts}`, status: 'resolved', occurrences: 1 }, ...s.report].slice(0, 60),
    messages: [{ ts: entry.ts, kind: 'resolved', text: `🤖 ${entry.assetName} 자율 해결완료` }, ...s.messages].slice(0, 200),
  })),
  setReportStatus: (id, status) => set((s) => ({
    report: s.report.map((r) => (r.id === id ? { ...r, status } : r)) })),

  // ── API 액션 (apiClient 래핑 — UI는 이것만 호출) ──
  startNode: (opts) => { set({ liveCategory: opts?.category, activeMode: opts?.mode, lanes: {} }); return inspectorStart(opts) },
  stopNode: () => inspectorStop(),
  startLanes: (opts) => { set({ activeMode: opts?.mode }); return inspectorStartLanes(opts) },
  stopLanes: () => inspectorStopLanes(),
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
