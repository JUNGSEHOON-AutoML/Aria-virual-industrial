// PredictiveMaintenance — T1-B 컨트롤러(비시각). 실 scan stream → defectPatternEngine → predictions 상태기계.
// Live=백엔드 diagnostic_result(reducer가 처리) / Standalone=클라 엔진(동일 규칙). 둘 다 실 데이터만 집계.
// 자동 해소 sweep 주기 실행. 끊기면 freeze.
import { useEffect, useRef } from 'react'
import { useSignalStore } from '../signalStore'
import { selectScan } from '../signalReducer'
import { createDefectPatternEngine } from './defectPatternEngine'

export default function PredictiveMaintenance() {
  const scan = useSignalStore(selectScan)
  const liveCategory = useSignalStore(s => s.liveCategory)
  const connected = useSignalStore(s => s.wsStatus) === 'open'
  const upsertPrediction = useSignalStore(s => s.upsertPrediction)
  const sweepPredictions = useSignalStore(s => s.sweepPredictions)

  const engineRef = useRef(null)
  if (!engineRef.current) engineRef.current = createDefectPatternEngine()
  const lastPart = useRef(null)

  const replayActive = useSignalStore(s => s.replay.active)
  // 실 inspector_result 1건 → 엔진 관찰 → 가설이면 predictions upsert (리플레이 중 제외)
  useEffect(() => {
    if (!connected || replayActive || !scan || !scan.part_id) return
    if (scan.part_id === lastPart.current) return
    lastPart.current = scan.part_id
    const hyp = engineRef.current.observe(scan, { className: liveCategory, nowMs: Date.now() })
    if (hyp) upsertPrediction(hyp)
  }, [scan, connected, replayActive, liveCategory, upsertPrediction])

  // 자동 해소 — NG 멎은 cell 가설을 일정 시간 후 가라앉힘
  useEffect(() => {
    const id = setInterval(() => sweepPredictions(Date.now()), 4000)
    return () => clearInterval(id)
  }, [sweepPredictions])

  return null
}
