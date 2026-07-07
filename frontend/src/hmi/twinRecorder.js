// twinRecorder — 3D 리플레이 블랙박스(①). signalStore.ingest를 탭해 WS 스트림을 링버퍼에 기록.
// 원리: 씬이 store 상태에서 렌더되므로, 기록한 프레임을 reducer로 되먹이면 3D가 과거를 자동 재생.
// 지오메트리/모션 별도 저장 불필요. 순수 모듈(Node 검증 가능).
const MAX = 2500   // 최근 N 프레임(메모리). 6Hz ≈ 7분.

const buffer = []   // { ts, msg }

// image_b64는 용량이 커서 리플레이엔 불필요 → 제거(heatmap_b64/defect_xy는 decal 재생에 필요하므로 유지).
function lighten(msg) {
  if (msg && msg.image_b64) { const { image_b64, ...rest } = msg; return rest }
  return msg
}

export function record(msg, ts) {
  if (!msg || !msg.type) return
  buffer.push({ ts: ts ?? Date.now(), msg: lighten(msg) })
  if (buffer.length > MAX) buffer.shift()
}

export function snapshot() { return buffer.slice() }
export function clearRecorder() { buffer.length = 0 }

// 이슈 마커: NG inspector_result / error 알람 → 타임라인 점프 지점
export function issueMarkers(frames) {
  const out = []
  for (const f of frames) {
    const m = f.msg
    if (m.type === 'inspector_result' && m.verdict === 'NG')
      out.push({ ts: f.ts, kind: 'NG', label: `${m.part_id || ''} NG ${m.defect_class || ''}`.trim() })
    else if (m.type === 'inspector_result' && m.verdict === 'SKIPPED')
      out.push({ ts: f.ts, kind: 'SKIP', label: `${m.part_id || ''} SKIP` })
  }
  return out
}
