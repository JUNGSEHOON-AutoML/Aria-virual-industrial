// MaintenanceController — Observe→Think→Act 루프(규칙기반). 명세 §3·§8. 비시각(null 렌더).
// Observe: 실 신호(kpi/scan)에서 결함 설비 도출. Think: 규칙(asset→tool) — ★실 LLM 교체 지점.
// Act: 아바타 가상 시연(move→repair) → 실 액션은 승인 게이트 경유(Simulate-then-Approve).
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
  const addApproval = useSignalStore(s => s.addApproval)
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
      // 수리 시연 완료 → 실 액션은 승인 게이트로(자동 실행 금지)
      const apprId = `ap_${seqRef.current}_${target.id}`
      addApproval({
        id: apprId, assetId: decision.assetId, assetName: decision.assetName,
        action: decision.action, actionLabel: decision.actionLabel,
        status: 'pending', ts: Date.now(),
      })
      logEpisode({
        ts: Date.now(), event: `${target.name} ${target.status}`, assetId: target.id,
        action: decision.action, approval: 'pending', result: 'sim_done',
      })
      setAgent({ task: 'IDLE', targetAssetId: null })
      busy.current = false
      cooldownUntil.current = Date.now() + 12000   // 12s 쿨다운(반복 억제)
    }, 4800)

    timers.current.push(t1, t2)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kpi, scan, agent?.task, connected])

  return null
}
