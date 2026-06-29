// 신호 스토어 React 훅 — 컴포넌트가 타입별 신호를 구독.
import { useState, useEffect } from 'react'
import { subscribe, getLatest, subscribeStatus, getStatus } from './twinStore'

// 특정 타입의 최신 메시지 (없으면 initial)
export function useTwinSignal(type, initial = null) {
  const [v, setV] = useState(() => getLatest(type) ?? initial)
  useEffect(() => subscribe(type, setV), [type])
  return v
}

// 누적 스트림 (최근 max개, 최신이 앞)
export function useTwinStream(type, max = 50) {
  const [arr, setArr] = useState([])
  useEffect(() => subscribe(type, (d) => setArr(prev => [d, ...prev].slice(0, max))), [type, max])
  return arr
}

// 여러 타입을 한 핸들러로 누적 (메시지/알람 피드용)
export function useTwinFeed(types, map, max = 60) {
  const [arr, setArr] = useState([])
  useEffect(() => {
    const offs = types.map(t => subscribe(t, (d) => {
      const item = map(d, t)
      if (item) setArr(prev => [{ ...item, _ts: Date.now() }, ...prev].slice(0, max))
    }))
    return () => offs.forEach(off => off())
  }, [types.join(','), max])  // eslint-disable-line
  return arr
}

export function useTwinStatus() {
  const [s, setS] = useState(getStatus())
  useEffect(() => subscribeStatus(setS), [])
  return s
}
