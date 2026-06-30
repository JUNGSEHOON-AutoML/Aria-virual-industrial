// MaintenanceController — Observe→Think→Act 루프(규칙기반). 비시각(null 렌더).
// 변경: 자동 승인 모달 금지(경보 피로). 발견사항을 ★보고서에 누적 → 운영자가 보고서에서 필요할 때만 조치.
// 아바타는 가상 점검 시연만 수행(시각). 실 액션 승인은 운영자가 보고서/카드에서 시작.
import { useEffect, useRef } from 'react'
import { useSignalStore } from '../signalStore'
import { selectKpi, selectScan } from '../signalReducer'
import { deriveAssets, faultyAssets, ASSET_ACTION } from './assetModel'

// ★실 LLM 훅: 지금은 규칙기반(asset.status/code→tool). 후속에 vision_agent/LLM 응답으로 교체.
function decideAction(asset) {
  const a = ASSET_ACTION[asset.id]
  if (!a) return null
  return { assetId: asset.id, assetName: asset.name, action: a.id, actionLabel: a.label }
}

export default function MaintenanceController() {
  const kpi = useSignalStore(selectKpi)
  const scan = useSignalStore(selectScan)
  const agent = useSignalStore(s => s.agent)
  const setAgent = useSignalStore(s => s.setAgent)
  const addReport = useSignalStore(s => s.addReport)
  const logEpisode = useSignalStore(s => s.logEpisode)

  const busy = useRef(false)          // 시연 진행 중 재진입 방지
  const cooldownUntil = useRef(0)     // 같은 결함 반복 트리거 억제
  const timers = useRef([])
  const seqRef = useRef(0)

  useEffect(() => () => timers.current.forEach(clearTimeout), [])

  const connected = useSignalStore(s => s.wsStatus) === 'open'

  useEffect(() => {
    if (!connected) return            // 끊기면 루프 정지
    if (busy.current) return
    if (Date.now() < cooldownUntil.current) return
    if (agent?.task && agent.task !== 'IDLE') return

    const faulty = faultyAssets(deriveAssets(kpi, scan, 0))
    if (!faulty.length) return
    const target = faulty[0]
    const decision = decideAction(target)
    if (!decision) return

    // ── Act: 가상 시연 시퀀스 (move → repair → 승인 요청) ──
    busy.current = true
    const evId = `ep_${++seqRef.current}_${target.id}`
    setAgent({ task: 'MOVING', targetAssetId: target.id })

    const t1 = setTimeout(() => setAgent({ task: 'REPAIRING', targetAssetId: target.id }), 2400)
    const t2 = setTimeout(() => {
      // 점검 시연 완료 → ★승인 모달 대신 보고서에 누적(자동 모달 금지)
      addReport({
        key: `maint:${target.id}`, kind: 'maintenance', ts: Date.now(),
        asset: decision.assetId, assetName: decision.assetName,
        title: `${decision.assetName} ${target.status}`,
        observation: `${decision.assetName} 상태 ${target.status} — 가상 점검 시연 완료`,
        recommendedAction: decision.actionLabel, action: decision.action,
      })
      logEpisode({
        ts: Date.now(), event: `report ${target.name} ${target.status}`, assetId: target.id,
        action: decision.action, approval: 'reported', result: 'sim_done',
      })
      setAgent({ task: 'IDLE', targetAssetId: null })
      busy.current = false
      cooldownUntil.current = Date.now() + 30000   // 30s 쿨다운(보고 누적 억제)
    }, 4800)

    timers.current.push(t1, t2)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kpi, scan, agent?.task, connected])

  return null
}
