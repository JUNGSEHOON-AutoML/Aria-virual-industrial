// MaintenanceController — 자율 유지보수 에이전트 FSM(비시각). 데이터 기반·다단계로 "인위적" 느낌 제거.
// 관측 → 이동 → 진단 → 수리 시도 → 검증 → (해결 | 재시도 | 운영자 에스컬레이션).
// 변동은 난수가 아니라 결함 심각도(Warning/Error)·시도 횟수·이벤트 순번에서 결정적으로 유도.
// 트윈 가상 수리는 자율, 실 시스템 변경만 승인 게이트(에스컬레이션 시).
import { useEffect, useRef } from 'react'
import { useSignalStore } from '../signalStore'
import { selectKpi, selectScan } from '../signalReducer'
import { deriveAssets, faultyAssets, ASSET_ACTION } from './assetModel'

function decideAction(asset) {
  const a = ASSET_ACTION[asset.id]
  if (!a) return null
  return { assetId: asset.id, assetName: asset.name, action: a.id, actionLabel: a.label, severe: asset.status === 'Error' }
}

export default function MaintenanceController() {
  const kpi = useSignalStore(selectKpi)
  const scan = useSignalStore(selectScan)
  const agent = useSignalStore(s => s.agent)
  const setAgent = useSignalStore(s => s.setAgent)
  const agentSay = useSignalStore(s => s.agentSay)
  const pushResolvedReport = useSignalStore(s => s.pushResolvedReport)
  const addReport = useSignalStore(s => s.addReport)
  const logEpisode = useSignalStore(s => s.logEpisode)
  const connected = useSignalStore(s => s.wsStatus) === 'open'
  const replayActive = useSignalStore(s => s.replay.active)

  const busy = useRef(false)
  const cooldownUntil = useRef(0)
  const resolvedUntil = useRef({})
  const timers = useRef([])
  const seqRef = useRef(0)

  useEffect(() => () => timers.current.forEach(clearTimeout), [])

  useEffect(() => {
    if (!connected || replayActive || busy.current) return
    if (Date.now() < cooldownUntil.current) return
    if (agent?.task && agent.task !== 'IDLE') return

    const now = Date.now()
    const faulty = faultyAssets(deriveAssets(kpi, scan, 0))
      .filter(a => (resolvedUntil.current[a.id] || 0) < now)
    if (!faulty.length) return
    const target = faulty[0]
    const decision = decideAction(target)
    if (!decision) return

    busy.current = true
    const evNo = ++seqRef.current
    const T = (ms, fn) => { const id = setTimeout(fn, ms); timers.current.push(id) }
    // 결정적 변동: Error는 1차 수리 미흡 후 2차 성공 / 3번째 Error 이벤트마다 에스컬레이션
    const escalates = decision.severe && (evNo % 3 === 0)
    const finish = (cdSec) => { setAgent({ task: 'IDLE', targetAssetId: null, thought: null }); busy.current = false; cooldownUntil.current = Date.now() + cdSec * 1000 }

    // 1) 이동 (거리감 위해 가변 지연)
    setAgent({ task: 'MOVING', targetAssetId: target.id, thought: `${decision.assetName}로 이동` })
    agentSay(`🤖 ${decision.assetName} 이상 감지 — 출동`)
    T(2200, () => {
      // 2) 진단
      setAgent({ task: 'DIAGNOSING', targetAssetId: target.id, thought: `진단 중: ${target.status}` })
      agentSay(`🔎 ${decision.assetName} 진단: ${target.status} → ${decision.actionLabel} 추정`)
      T(1600, () => attempt(1))
    })

    function attempt(n) {
      setAgent({ task: 'REPAIRING', targetAssetId: target.id, thought: `수리 시도 ${n}: ${decision.actionLabel}` })
      T(2000, () => {
        // 3) 검증
        setAgent({ task: 'VERIFYING', targetAssetId: target.id, thought: '검증: 상태 재확인' })
        T(1300, () => {
          const repaired = !decision.severe || n >= 2     // Error는 2차에 해결
          if (escalates && n >= 2) return escalate()
          if (repaired) return resolve(n)
          agentSay(`⚠ ${decision.assetName} 부분 개선 — 재시도(${n + 1})`)
          attempt(n + 1)
        })
      })
    }

    function resolve(n) {
      const ts = Date.now()
      pushResolvedReport({
        key: `maint:${target.id}`, kind: 'maintenance', ts,
        asset: decision.assetId, assetName: decision.assetName,
        title: `✓ 해결완료 — ${decision.assetName}`,
        observation: `자율 진단(${target.status}) → ${decision.actionLabel} ${n}회 시도 → 검증 통과`,
        recommendedAction: `${decision.actionLabel} · 실 조치는 승인 게이트`, action: decision.action,
      })
      logEpisode({ ts, event: `resolve ${target.name}`, assetId: target.id, action: decision.action, approval: 'auto', result: `resolved(${n})` })
      agentSay(`✅ ${decision.assetName} 자율 해결완료 (시도 ${n}회)`)
      resolvedUntil.current[target.id] = ts + 25000
      setAgent({ task: 'RESOLVED', targetAssetId: target.id, thought: '✓ 해결완료' })
      T(1500, () => finish(6))
    }

    function escalate() {
      const ts = Date.now()
      addReport({          // 운영자 처리 필요(open) — 승인 게이트로 실 조치
        key: `esc:${target.id}`, kind: 'maintenance', ts,
        asset: decision.assetId, assetName: decision.assetName,
        title: `🚨 자율 해결 실패 — ${decision.assetName}`,
        observation: `${target.status} 2회 수리 후에도 미해결 → 운영자 점검 필요`,
        recommendedAction: decision.actionLabel, action: decision.action,
      })
      logEpisode({ ts, event: `escalate ${target.name}`, assetId: target.id, action: decision.action, approval: 'pending', result: 'escalated' })
      agentSay(`🚨 ${decision.assetName} 자율 해결 실패 → 운영자 에스컬레이션`)
      resolvedUntil.current[target.id] = ts + 30000
      setAgent({ task: 'IDLE', targetAssetId: null, thought: null })
      busy.current = false; cooldownUntil.current = ts + 8000
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kpi, scan, agent?.task, connected, replayActive])

  return null
}
