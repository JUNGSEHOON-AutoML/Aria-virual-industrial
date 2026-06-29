// vlmReport — 검사 결과 → 구조화 분석(관측/추정원인/권장조치). 명세 §4.
// ⚠️ 원인 단정 금지(환각). 원인은 항상 "가설 + 신뢰도 + 확인 요망".
// Standalone/Mock 또는 실 vision_agent 출력이 없으면 placeholder 라벨.
// anomaly score=낮을수록 정상, OK if score<τ (불변).

function quadrant(xy) {
  if (!Array.isArray(xy)) return '중앙'
  const [x, y] = xy
  const h = x < 0.4 ? '좌' : x > 0.6 ? '우' : '중'
  const v = y < 0.4 ? '상' : y > 0.6 ? '하' : '중'
  if (h === '중' && v === '중') return '중앙'
  return `${h}${v}`
}

export function buildVlmReport(scan, isMock = false) {
  const score = scan?.score != null && scan.score >= 0 ? scan.score : null
  const tau = scan?.tau ?? 0.5
  const ng = score != null ? score >= tau : (scan?.verdict === 'NG')
  const defect = scan?.defect_class || null
  const loc = quadrant(scan?.defect_xy)

  // 심각도 — τ 대비(낮을수록 정상)
  let severity = '낮음'
  if (score != null) severity = score >= tau ? '높음' : score >= tau * 0.6 ? '보통' : '낮음'
  else severity = ng ? '높음' : '낮음'

  // 관측(데이터 근거)
  const observation = ng
    ? `${defect ? `${defect} ` : '표면 이상 '}관측 · 위치 ${loc} · 심각도 ${severity}` +
      (score != null ? ` (score ${score.toFixed(3)} ≥ τ ${tau.toFixed(3)})` : '')
    : `유의 결함 없음 · 심각도 ${severity}` +
      (score != null ? ` (score ${score.toFixed(3)} < τ ${tau.toFixed(3)})` : '')

  // 추정 원인 — 가설 + 신뢰도 + 확인 요망 (단정 아님)
  let cause = null
  if (ng) {
    const hyp = defect
      ? `${defect} 유형 공정 편차 의심`
      : '이송 마찰/이물에 의한 표면 손상 의심'
    cause = { text: hyp, confidence: defect ? 0.45 : 0.35, note: '확인 요망(단정 아님)' }
  }

  // 권장 조치
  const action = ng
    ? '재검사 → 해당 클래스 학습 뱅크 점검 · 카메라 교정 상태 확인'
    : '조치 불필요 (정상)'

  return {
    observation, cause, action, severity, ng,
    placeholder: isMock,   // Mock/합성 데이터면 placeholder 표기
  }
}
