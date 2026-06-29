// 헤드리스 증명: 단일 ingest 경로가 (1) reducer 구조화 상태 + (2) raw 타입 팬아웃을 동시에 올바로 구동.
import { initialState, applyMessage, selectContext } from './signalReducer.js'
import { pushType, subscribeType, getLatestType, _resetFanout } from './signalFanout.js'

let pass = 0, fail = 0
const ok = (c, m) => { if (c) { pass++; } else { fail++; console.log('  ✗', m) } }

// 통합 ingest를 모사: reducer 패치 + 팬아웃 동시
let state = { ...initialState }
const ingest = (msg) => { const p = applyMessage(state, msg); if (p) state = { ...state, ...p }; pushType(msg) }

_resetFanout()
// raw 구독자(구 twinStore 사용자) 설치
const got = { inspector_result: [], any: [] }
const un1 = subscribeType('inspector_result', m => got.inspector_result.push(m))
const un2 = subscribeType('*', m => got.any.push(m.type))

// /ws/chat 메시지 시퀀스
ingest({ type: 'inspector_state', state: 'RUN', yield: 0.5, tact: 52, n_ok: 100, n_ng: 100 })
ingest({ type: 'inspector_result', part_id: 'P1', score: 0.42, tau: 0.5, verdict: 'OK' })
ingest({ type: 'inspector_result', part_id: 'P2', score: 0.88, tau: 0.5, verdict: 'NG', defect_class: 'crack', bbox: [1,2,3,4] })
ingest({ type: 'class_result', classId: 'capsule', fat_verdict: 'FAIL', escape_rate: 0.64 })
ingest({ type: 'agent_status', agent: 'vision', state: 'DIAGNOSING', detail: 'x' })
ingest({ type: 'thought', content: '카메라 재교정 권장' })

// ── (1) 구조화 상태 (reducer) ──
ok(state.kpi.state === 'RUN' && state.kpi.yield === 0.5, 'kpi(inspector_state) 반영')
ok(state.scan && state.scan.part_id === 'P2', 'scan=최신 inspector_result')
ok(state.detectors.patchcore && state.detectors.patchcore.score === 0.88, 'detectors.patchcore 반영')
ok(state.detectors.yolo && state.detectors.yolo.defect_class === 'crack' && Array.isArray(state.detectors.yolo.bbox), 'detectors.yolo bbox 반영')
ok(state.alarms.length === 1 && state.alarms[0].text.includes('P2') && state.alarms[0].text.includes('crack'), 'NG → alarm prepend')
ok(state.lines.capsule && state.lines.capsule.fat_verdict === 'FAIL', 'class_result → lines[classId]')
ok(state.agents.vision && state.agents.vision.state === 'DIAGNOSING', 'agent_status → agents[agent]')
ok(state.messages.length === 1 && state.messages[0].kind === 'thought', 'thought → messages')

// selector(선택 컨텍스트)
state = { ...state, selection: { group: 'line', id: 'capsule' } }
const ctx = selectContext(state)
ok(ctx.kind === 'line' && ctx.data && ctx.data.fat_verdict === 'FAIL', 'selectContext(line) 동기')

// ── (2) raw 팬아웃 (구 twinStore 사용자) ──
ok(got.inspector_result.length === 2, 'subscribeType(inspector_result) 2건 수신')
ok(got.inspector_result[1].part_id === 'P2', '구독자가 raw 메시지 그대로 수신')
ok(getLatestType('inspector_result').part_id === 'P2', 'getLatestType=최신 raw')
ok(getLatestType('class_result').classId === 'capsule', 'getLatestType(class_result)')
ok(got.any.length === 6, "'*' 구독자 전체 6건 수신")

// 구독 해제
un1(); un2()
ingest({ type: 'inspector_result', part_id: 'P3', score: 0.1, tau: 0.5, verdict: 'OK' })
ok(got.inspector_result.length === 2, '해제 후 미수신(구독 해제 동작)')
ok(getLatestType('inspector_result').part_id === 'P3', '해제와 무관하게 latest는 갱신')

console.log(`\n결과: ${pass} PASS / ${fail} FAIL  (단일 ingest → 구조화 상태 + raw 팬아웃 동시 동작)`) 
process.exit(fail ? 1 : 0)
