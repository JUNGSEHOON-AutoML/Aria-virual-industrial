// signalStore의 순수 reducer/selector (apiClient·WS 의존 없음 → Node 헤드리스 검증 가능).
// /ws/chat 메시지를 실제 소스 매핑(스펙 §5 재매핑)으로 store 상태에 반영한다.

export const initialState = {
  mode: 'standalone',          // standalone(mock/synthetic) | live(실 detector)
  wsStatus: 'idle',
  classes: [],                 // mvtecScan 클래스 목록(계층/뷰포트 단일 소스)
  lines: {},                   // classId -> class_result (fat_verdict, escape_rate, ...)
  kpi: {},                     // inspector_state (state/yield/tact/ack/queue/drop/n_ok/n_ng/...)
  scan: null,                  // 최신 inspector_result
  detectors: { patchcore: null, yolo: null },
  alarms: [],                  // {ts, level, tag, text}
  selection: null,             // {group, id}
  agents: {},                  // agent -> {state, detail}
  training: null,              // 최신 training 이벤트
  joints: null,                // joint_state.joints
  messages: [],                // {ts, kind, text}
}

// 메시지 1건 → 상태 부분 패치(없으면 null). 순수 함수.
export function applyMessage(state, msg) {
  const t = msg && msg.type
  if (!t) return null
  switch (t) {
    case 'inspector_state':
      return { kpi: { ...msg } }

    case 'inspector_result': {
      const patch = { scan: msg }
      const det = { ...state.detectors }
      if (msg.score != null && msg.score >= 0) det.patchcore = { score: msg.score, verdict: msg.verdict, tau: msg.tau }
      if (msg.defect_class || msg.bbox) det.yolo = { defect_class: msg.defect_class, bbox: msg.bbox }
      patch.detectors = det
      if (msg.verdict === 'NG')
        patch.alarms = [{ ts: msg.ts, level: 'error', tag: 'ALARM', text: `${msg.part_id} NG ${msg.defect_class || ''}`.trim() }, ...state.alarms].slice(0, 100)
      else if (msg.verdict === 'SKIPPED')
        patch.alarms = [{ ts: msg.ts, level: 'warn', tag: 'SKIP', text: `${msg.part_id} (backpressure)` }, ...state.alarms].slice(0, 100)
      return patch
    }

    case 'class_result':
      return { lines: { ...state.lines, [msg.classId]: msg } }

    case 'agent_status':
      return { agents: { ...state.agents, [msg.agent]: { state: msg.state, detail: msg.detail } } }

    case 'training':
      return { training: msg }

    case 'joint_state':
      return { joints: msg.joints || null }

    case 'thought':
    case 'response':
    case 'diagnostic_result':
      return { messages: [{ ts: Date.now(), kind: t, text: msg.content || msg.detail || t }, ...state.messages].slice(0, 200) }

    default:
      return null
  }
}

// ── selectors (UI 슬롯이 구독) ──
export const selectKpi = (s) => s.kpi || {}
export const selectAlarms = (s) => s.alarms || []
export const selectScan = (s) => s.scan
export const selectDetectors = (s) => s.detectors
export const selectJoints = (s) => s.joints
// 선택 컨텍스트: line 선택 시 해당 라인 결과, node 선택 시 kpi
export function selectContext(s) {
  if (!s.selection) return { kind: 'none' }
  if (s.selection.group === 'line') return { kind: 'line', id: s.selection.id, data: s.lines[s.selection.id] || null }
  if (s.selection.group === 'node') return { kind: 'node', id: s.selection.id, data: s.kpi }
  return { kind: s.selection.group, id: s.selection.id }
}
