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
  liveCategory: null,          // 현재 가동 중인 검사 클래스(시편 형상 결정)
  // ── Agentic 유지보수 트윈(Spec 2) ──
  agent: { task: 'IDLE', targetAssetId: null },   // task: IDLE|MOVING|REPAIRING
  approvals: [],               // {id, assetId, action, actionLabel, status:'pending|approved|rejected', ts}
  episodes: [],                // {ts, event, assetId, action, approval, result}
  detections: [],              // yolo_detection — 순찰 로봇 YOLO 동적 탐지(실 WS만)
  predictions: [],             // T1-B 예지 가설 — 상태기계(pending|approved|dismissed|resolved)
  report: [],                  // 에이전트 점검 보고서 — 자동 승인 모달 대신 누적(경보 피로 방지)
  trained: {},                 // F2: classId -> {ready, n_patches, ts} 학습 완료(검사 준비) 상태
  lanes: {},                   // 멀티레인: laneIdx -> {category, kpi, scan} (각 레인 다른 클래스)
  activeMode: null,            // 현재 가동 모델(mock|patchcore|combined) — 공정 투명성
  replay: { active: false, frames: [], t: 0, t0: 0, t1: 0, playing: false, speed: 1, markers: [] },  // ① 3D 리플레이
}

// ① 리플레이: 기록 프레임을 t시점까지 reducer로 되먹여 그 순간의 씬 상태 재구성(순수).
// 반환 = 씬 표출 상태(kpi/scan/detectors/alarms/lines/agents/joints)만. 헤드리스 검증 가능.
export function rebuildSceneAt(frames, t) {
  let st = { ...initialState }
  for (const f of frames) {
    if (f.ts > t) break
    const p = applyMessage(st, f.msg)
    if (p) st = { ...st, ...p }
  }
  return { kpi: st.kpi, scan: st.scan, detectors: st.detectors, alarms: st.alarms, lines: st.lines, agents: st.agents, joints: st.joints }
}

// ── 에이전트 보고서: 자동 모달 대신 발견사항을 누적. 동일 key 병합(occurrences++). ──
export function upsertReport(list, entry) {
  if (!entry || !entry.key) return list
  const i = list.findIndex(r => r.key === entry.key && r.status === 'open')
  if (i < 0) return [{ ...entry, id: `${entry.key}:${entry.ts}`, status: 'open', occurrences: 1 }, ...list].slice(0, 60)
  const prev = list[i]
  const next = list.slice()
  next[i] = { ...prev, ...entry, id: prev.id, status: 'open', occurrences: prev.occurrences + 1 }
  return next
}

// ── T1-B 예지 가설 상태기계 (순수, 헤드리스 검증) ──────────────────────
// 동일 cell 재발 → 새 카드 X, 기존 카드 count/표본 갱신(+occurrences). 상태 'resolved'/'dismissed'면 재개.
export function upsertPrediction(list, hyp) {
  if (!hyp || !hyp.cell) return list
  const base = {
    id: hyp.cell, cell: hyp.cell, class: hyp.class, row: hyp.row, col: hyp.col, grid: hyp.grid,
    causal: hyp.causal, statConfidence: hyp.statConfidence,
    defectClass: hyp.defectClass, defectClassN: hyp.defectClassN,
    ngTotal: hyp.ngTotal, total: hyp.total, window: hyp.window,
    recommendedAction: hyp.recommendedAction, lastNgTs: hyp.ts,
  }
  const i = list.findIndex(p => p.id === hyp.cell)
  if (i < 0) return [{ ...base, status: 'pending', occurrences: 1, ts: hyp.ts }, ...list].slice(0, 30)
  const prev = list[i]
  const status = (prev.status === 'resolved' || prev.status === 'dismissed') ? 'pending' : prev.status
  const next = list.slice()
  next[i] = { ...prev, ...base, occurrences: prev.occurrences + 1, status }
  return next
}

// 자동 해소: pending|approved 가설이 일정 시간 NG 없으면 resolved로 가라앉힘(과거 가설 누적 방지).
export function sweepPredictions(list, nowMs, resolveMs = 20000) {
  let changed = false
  const out = list.map(p => {
    if ((p.status === 'pending' || p.status === 'approved') && nowMs - p.lastNgTs > resolveMs) {
      changed = true; return { ...p, status: 'resolved' }
    }
    return p
  })
  return changed ? out : list
}

// 메시지 1건 → 상태 부분 패치(없으면 null). 순수 함수.
export function applyMessage(state, msg) {
  const t = msg && msg.type
  if (!t) return null
  switch (t) {
    case 'inspector_state':
      if (msg.lane != null)   // 멀티레인: 레인별 kpi + 전역 kpi(메인 패널)도 갱신
        return { kpi: { ...msg }, lanes: { ...state.lanes, [msg.lane]: { ...(state.lanes[msg.lane] || {}), category: msg.category, kpi: msg } } }
      return { kpi: { ...msg } }

    case 'inspector_done': {   // 검사 1바퀴 완료 → 완료 메시지(멀티레인은 다음 클래스로 자동 전환)
      const yld = msg.yield_rate != null ? `${(msg.yield_rate * 100).toFixed(0)}%` : '—'
      const m = {
        messages: [{ ts: Date.now(), kind: 'inspector_done',
          text: `${msg.lane != null ? `레인${msg.lane} ` : ''}검사 완료 — ${msg.category || ''} · OK ${msg.n_ok ?? 0}/NG ${msg.n_ng ?? 0} · 수율 ${yld}` }, ...state.messages].slice(0, 200),
      }
      if (msg.lane == null) m.kpi = { ...state.kpi, state: 'done' }   // 단일 노드만 종료 처리
      return m
    }

    case 'inspector_result': {
      const patch = { scan: msg }
      if (msg.lane != null)   // 멀티레인: 레인별 최신 결과 라우팅
        patch.lanes = { ...state.lanes, [msg.lane]: { ...(state.lanes[msg.lane] || {}), category: msg.category, scan: msg } }
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

    case 'class_trained':       // F2: 클래스 학습 완료(검사 준비됨)
      return msg.classId
        ? { trained: { ...state.trained, [msg.classId]: { ready: !!msg.ready, n_patches: msg.n_patches, ts: msg.ts } },
            messages: [{ ts: Date.now(), kind: 'class_trained', text: `${msg.classId} 학습 완료 — 검사 준비됨 (${msg.n_patches} 패치)` }, ...state.messages].slice(0, 200) }
        : null

    case 'yolo_detection': {
      // 순찰 로봇 YOLO 동적 탐지 — 실 WS 수신만(클라 위조 없음). 최근 12건 유지.
      const det = { ...msg, _rx: Date.now() }
      return { detections: [det, ...state.detections].slice(0, 12) }
    }

    case 'agent_status':
      return { agents: { ...state.agents, [msg.agent]: { state: msg.state, detail: msg.detail } } }

    case 'training':
      return { training: msg }

    case 'joint_state':
      return { joints: msg.joints || null }

    case 'diagnostic_result': {
      // 백엔드 aggregator의 예지 가설 → predictions 상태기계(클라 엔진과 동일 경로)
      const m = { messages: [{ ts: Date.now(), kind: t, text: msg.hypothesis || msg.content || msg.detail || t }, ...state.messages].slice(0, 200) }
      if (msg.kind === 'predictive' && msg.cell) {
        m.predictions = upsertPrediction(state.predictions, {
          cell: msg.cell, class: msg.class, row: msg.row, col: msg.col, grid: msg.grid,
          causal: { hypothesis: msg.hypothesis, assetHint: msg.asset_hint, verified: false },
          statConfidence: msg.confidence, ngTotal: msg.ngTotal, total: msg.total,
          window: msg.window, recommendedAction: msg.recommended_action, ts: msg.ts || Date.now(),
        })
      }
      return m
    }

    case 'thought':
    case 'response':
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
