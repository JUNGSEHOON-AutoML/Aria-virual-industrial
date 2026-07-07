// ECharts 라이브 차트 — 트리거 ack vs 추론 p95 타임라인(비병목 증거) + 학습 loss.
import { useRef, useEffect } from 'react'
import * as echarts from 'echarts'
import { subscribe } from './twinStore'

export default function ChartPanel() {
  const ref = useRef()
  const chart = useRef()
  const ack = useRef([])
  const infer = useRef([])
  const loss = useRef([])

  useEffect(() => {
    chart.current = echarts.init(ref.current, 'dark', { renderer: 'canvas' })
    chart.current.setOption({
      backgroundColor: 'transparent',
      grid: [{ left: 38, right: 10, top: 18, height: '40%' }, { left: 38, right: 10, top: '62%', height: '30%' }],
      legend: { top: 0, textStyle: { fontSize: 10, color: '#9aa0aa' },
        data: ['ack max', 'infer p95', 'loss'] },
      xAxis: [{ type: 'time', gridIndex: 0, axisLabel: { fontSize: 9, color: '#6b7280' } },
        { type: 'value', gridIndex: 1, axisLabel: { fontSize: 9, color: '#6b7280' } }],
      yAxis: [{ type: 'value', gridIndex: 0, name: 'ms', nameTextStyle: { fontSize: 9 }, axisLabel: { fontSize: 9, color: '#6b7280' } },
        { type: 'value', gridIndex: 1, name: 'loss', nameTextStyle: { fontSize: 9 }, axisLabel: { fontSize: 9, color: '#6b7280' } }],
      series: [
        { name: 'ack max', type: 'line', showSymbol: false, smooth: true, lineStyle: { width: 2, color: '#34d399' }, data: [],
          markLine: { silent: true, symbol: 'none', data: [{ yAxis: 20 }], lineStyle: { color: '#f87171', type: 'dashed' },
            label: { formatter: 'SLA 20ms', fontSize: 9, color: '#f87171' } } },
        { name: 'infer p95', type: 'line', showSymbol: false, smooth: true, lineStyle: { width: 2, color: '#facc15' }, data: [] },
        { name: 'loss', type: 'line', xAxisIndex: 1, yAxisIndex: 1, showSymbol: false, lineStyle: { width: 2, color: '#1FB8CD' }, data: [] },
      ],
    })
    const onResize = () => chart.current && chart.current.resize()
    window.addEventListener('resize', onResize)
    const upd = () => chart.current && chart.current.setOption({
      series: [{ data: ack.current }, { data: infer.current }, { data: loss.current }] })
    const off1 = subscribe('inspector_state', (d) => {
      const t = Date.now()
      ack.current = [...ack.current, [t, d.ack_max_ms ?? 0]].slice(-120)
      infer.current = [...infer.current, [t, d.infer_latency_p95_ms ?? 0]].slice(-120)
      upd()
    })
    const off2 = subscribe('training', (d) => {
      if (d.metrics?.loss != null) { loss.current = [...loss.current, [d.step, d.metrics.loss]].slice(-200); upd() }
    })
    return () => { off1(); off2(); window.removeEventListener('resize', onResize); chart.current.dispose() }
  }, [])

  return (
    <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: 10, padding: '8px 10px', height: '100%', minHeight: 0 }}>
      <div style={{ fontSize: 10.5, color: '#6b7280', letterSpacing: 1, marginBottom: 4, fontFamily: "'Courier New', monospace" }}>
        LIVE · ack vs infer (비병목) · loss
      </div>
      <div ref={ref} style={{ width: '100%', height: 'calc(100% - 18px)', minHeight: 160 }} />
    </div>
  )
}
