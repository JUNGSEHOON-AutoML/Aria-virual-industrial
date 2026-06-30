// VisionPiP — 명세 §A + §4. 카메라/시편 클릭 시 슬라이드. 2D 원본+heatmap 토글 + VLM 분석.
// 데이터: store.scan(inspector_result) 우선, Standalone은 data override(합성 image/heatmap).
// VLM: 관측/추정원인(가설+신뢰도, 확인 요망)/권장조치 — 원인 단정 금지. 새 ws 없음.
import { useState, useEffect } from 'react'
import { useSignalStore } from '../signalStore'
import { selectScan } from '../signalReducer'
import { buildVlmReport } from '../scene/vlmReport'

const wrap = {
  position: 'absolute', top: 0, right: 0, height: '100%', width: 330, zIndex: 8,
  background: 'rgba(11,15,24,0.97)', borderLeft: '1px solid rgba(31,184,205,0.4)',
  transition: 'transform .32s cubic-bezier(.4,0,.2,1)',
  display: 'flex', flexDirection: 'column', padding: 14, gap: 10, overflowY: 'auto',
  fontFamily: "'Courier New',monospace", color: '#e2e8f0', boxSizing: 'border-box',
}
const chip = { fontSize: 11, padding: '3px 8px', borderRadius: 5,
  background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)' }
const secHead = { fontSize: 9, color: '#6b7280', letterSpacing: 1, marginTop: 6 }

export default function VisionPiP({ open, onClose, data }) {
  const scan = useSignalStore(selectScan)
  const [mode, setMode] = useState('overlay')

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose?.() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // F1: 클릭된 부품(data) 우선 — 헤더·이미지·VLM 전부 그 부품 record 기준. 없으면 최신 scan.
  const r = (data && data.part_id) ? data : scan
  const verdict = r?.verdict
  const vColor = verdict === 'NG' ? '#f87171' : verdict === 'OK' ? '#34d399' : '#9aa0aa'

  const img = r?.image_b64
  const heat = r?.heatmap_b64
  const isMock = !!data?._mock

  const report = buildVlmReport(r, isMock)

  return (
    <div style={{ ...wrap, transform: open ? 'translateX(0)' : 'translateX(100%)' }}>
      <button onClick={onClose} style={{ position: 'absolute', top: 8, right: 12,
        background: 'none', border: 'none', color: '#6b7280', fontSize: 18, cursor: 'pointer' }}>✕</button>
      <h3 style={{ margin: 0, fontSize: 13, color: '#1FB8CD', letterSpacing: 1 }}>VISION PiP · 분석</h3>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        <span style={chip}>PART {r?.part_id || '—'}</span>
        <span style={chip}>SCORE {r?.score != null && r.score >= 0 ? r.score.toFixed(3) : '—'}</span>
        <span style={chip}>τ {r?.tau != null ? r.tau.toFixed(3) : '—'}</span>
        <span style={{ ...chip, color: vColor, fontWeight: 700 }}>{verdict || '—'}</span>
      </div>

      {/* 2D 캔버스 */}
      <div style={{ position: 'relative', width: '100%', aspectRatio: '1/1',
        border: '1px solid rgba(255,255,255,0.12)', borderRadius: 6, overflow: 'hidden',
        background: '#05080e', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {img ? (
          <img src={img} alt="원본" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%',
            objectFit: 'cover', opacity: mode === 'heat' ? 0.15 : 1 }} />
        ) : (
          <span style={{ fontSize: 11, color: '#5b6677', textAlign: 'center', padding: 16 }}>
            2D 원본 대기 중<br />(patchcore/combined 가동 시 표출)
          </span>
        )}
        {heat && (mode === 'heat' || mode === 'overlay') && (
          <img src={heat} alt="heatmap" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%',
            objectFit: 'cover', mixBlendMode: 'screen' }} />
        )}
      </div>

      <div style={{ display: 'flex', gap: 6 }}>
        {[['base', '원본'], ['heat', 'heatmap'], ['overlay', 'overlay']].map(([m, label]) => (
          <button key={m} onClick={() => setMode(m)} style={{
            flex: 1, fontFamily: 'inherit', fontSize: 11, cursor: 'pointer', padding: '6px 0', borderRadius: 5,
            color: mode === m ? '#1FB8CD' : '#9aa3b2',
            background: mode === m ? 'rgba(31,184,205,0.12)' : 'rgba(255,255,255,0.04)',
            border: `1px solid ${mode === m ? '#1FB8CD' : 'rgba(255,255,255,0.1)'}` }}>{label}</button>
        ))}
      </div>

      {/* T1-A: 2D(u,v)→3D 좌표 + blob 면적 */}
      {Array.isArray(r?.defect_xy) && (
        <div style={{ fontSize: 10, color: '#9aa3b2', lineHeight: 1.5 }}>
          <span style={{ color: '#6b7280' }}>좌표 · </span>
          (u,v)=({r.defect_xy[0].toFixed(3)}, {r.defect_xy[1].toFixed(3)}) → 3D 표면 투영(decal·laser)
          {r?.defect_blob?.area != null && (
            <span> · blob {(r.defect_blob.area * 100).toFixed(1)}%</span>
          )}
        </div>
      )}

      {/* VLM 구조화 분석 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ ...secHead, marginTop: 0 }}>VLM 분석</span>
        {report.placeholder && <span style={{ ...chip, fontSize: 9, color: '#a78b4b', padding: '1px 6px' }}>
          placeholder(합성)
        </span>}
      </div>

      <div style={{ fontSize: 11, color: '#cbd5e1', lineHeight: 1.5 }}>
        <div style={{ marginBottom: 6 }}>
          <span style={{ color: '#6b7280' }}>관측 · </span>{report.observation}
        </div>
        {report.cause ? (
          <div style={{ marginBottom: 6 }}>
            <span style={{ color: '#6b7280' }}>추정 원인 · </span>
            <span style={{ color: '#facc15' }}>{report.cause.text}</span>
            <span style={{ color: '#9aa0aa' }}> (신뢰도 {report.cause.confidence.toFixed(2)} · {report.cause.note})</span>
          </div>
        ) : (
          <div style={{ marginBottom: 6, color: '#34d399' }}>추정 원인 · 해당 없음(정상)</div>
        )}
        <div>
          <span style={{ color: '#6b7280' }}>권장 조치 · </span>{report.action}
        </div>
      </div>

      <div style={{ fontSize: 10, color: '#5b6677', marginTop: 'auto' }}>
        원인은 가설(확인 요망) — 단정 아님. 판정은 PatchCore τ가 결정.<br />
        실 분석은 vision_agent/VLM 연결 시 이미지 근거로 대체.
      </div>
    </div>
  )
}
