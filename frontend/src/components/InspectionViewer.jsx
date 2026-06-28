/**
 * InspectionViewer.jsx — 비전 HUD & 진단 패널
 *
 * 주요 변경사항:
 * - 슬라이더 → HudToggle 스위치 (원본 ↔ 히트맵)
 * - 텍스트 버튼 → 아이콘 기반 Action Console (action-pill)
 * - 스캐닝 오버레이: CSS spinner-ring + typewriter 텍스트
 * - DiagnosticReport: 기존 레이아웃 유지, 스타일 정돈
 */

import { useState, useRef, useCallback, useEffect } from 'react'
import { Camera, RotateCcw, Zap, Eye, Activity } from 'lucide-react'
import { analyzeImage } from '../api/apiClient'
import HudToggle from './HudToggle'
import StatusBeacon from './StatusBeacon'

// BASE_URL: Vite proxy 사용 시 빈 문자열 → /api/* 요청이 localhost:8000으로 자동 포워딩
const BASE_URL = import.meta.env.VITE_API_URL || ''

// ── SVG 도넛 차트 ───────────────────────────────────────────────
function DonutChart({ pct, color }) {
  const R = 26
  const CIRC = 2 * Math.PI * R  // ≈ 163.36
  const offset = CIRC * (1 - pct / 100)

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="text-[7px] font-black uppercase tracking-widest text-[var(--text-muted)]">
        Defect Prob.
      </div>
      <svg width="62" height="62" viewBox="0 0 62 62" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx="31" cy="31" r={R} fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="6" />
        <circle
          cx="31" cy="31" r={R}
          fill="none"
          stroke={color || 'rgba(255,255,255,0.15)'}
          strokeWidth="6"
          strokeDasharray={CIRC}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.6s cubic-bezier(0.16,1,0.3,1), stroke 0.4s ease' }}
        />
      </svg>
      <div className="text-[11px] font-black" style={{ color: color || 'rgba(255,255,255,0.25)' }}>
        {pct}%
      </div>
    </div>
  )
}

function DiagnosticReport({ diag, modelTag, isScanning, scanMs }) {
  if (isScanning || diag.status === 'inspecting') {
    return (
      <div className="glass-panel flex-shrink-0">
        <div className="panel-header mb-2.5">
          <span className="panel-label">
            <span style={{ color: 'var(--cyan)' }} className="animate-pulse">◈</span>
            Diagnostic Report
          </span>
          <span className="text-[9px] font-mono font-bold px-2 py-0.5 rounded border animate-pulse"
                style={{ color: 'var(--cyan)', borderColor: 'rgba(56,189,248,0.2)', background: 'rgba(56,189,248,0.04)' }}>
            STATUS: INSPECTING
          </span>
        </div>
        <div className="flex flex-col items-center justify-center py-6 gap-2">
          <div className="text-[12px] font-bold text-[var(--cyan)] uppercase tracking-widest flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[var(--cyan)] animate-ping" />
            추론 분석 진행 중 (Inference Pipeline Active)
          </div>
          <div className="font-mono text-2xl font-light text-[var(--text-secondary)]">
            {scanMs ? `${scanMs.toLocaleString()} ms` : '0 ms'}
          </div>
          <div className="text-[9px] font-mono text-[var(--text-muted)] mt-1">
            Evaluating model candidates & compiling verification report...
          </div>
        </div>
      </div>
    )
  }

  // [§1] image_domain 분기: 일반/문서 이미지는 이상탐지 패널 숨김
  const isContentMode = diag.status === 'content' || diag.image_domain === 'general_object'

  const isAnomaly   = !isContentMode && (diag.status === 'anomaly' || diag.status === 'detected' || diag.status === 'fail')
  const scoreColor  = isAnomaly ? '#f87171' : '#38bdf8'
  const probColor   = isAnomaly ? '#f87171' : '#4ade80'

  const threshold   = diag.threshold || 15
  const score       = diag.score || 0
  const maxScore    = threshold * 2
  const progressPct = Math.min((score / maxScore) * 100, 100)
  const markerPct   = Math.min((threshold / maxScore) * 100, 100)

  const hasScore    = diag.score != null && !isContentMode
  const isNG        = hasScore && diag.score > threshold
  const verdict     = !hasScore ? null : (isNG ? 'NG' : 'OK')
  const verdictColor = isNG ? '#f87171' : '#34d399'

  return (
    <div className="glass-panel flex-shrink-0">
      <div className="panel-header">
        <span className="panel-label">
          <span style={{ color: 'var(--violet)' }}>◈</span>
          Diagnostic Report
        </span>
        <div className="flex items-center gap-1.5 shrink-0">
          {diag.device && (
            <span
              className="text-[9px] font-mono font-bold px-2 py-0.5 rounded border"
              style={{
                color: diag.device.startsWith('cuda') ? 'var(--green)' : 'var(--red)',
                background: diag.device.startsWith('cuda') ? 'rgba(74,222,128,0.06)' : 'rgba(239,68,68,0.06)',
                borderColor: diag.device.startsWith('cuda') ? 'rgba(74,222,128,0.2)' : 'rgba(239,68,68,0.2)',
              }}
              title={diag.device_reason}
            >
              DEVICE: {diag.device.toUpperCase()} {diag.device === 'cpu' ? '⚠' : ''}
            </span>
          )}
          {modelTag && (
            <span
              className="text-[9px] font-mono font-bold px-2 py-0.5 rounded border"
              style={{
                color: 'var(--violet)',
                background: 'rgba(167,139,250,0.06)',
                borderColor: 'rgba(167,139,250,0.2)',
              }}
            >
              MODEL: {modelTag}
            </span>
          )}
        </div>
      </div>

      {isContentMode ? (
        /* [§1] 일반/문서 이미지 → VLM 내용 설명 표시, 이상탐지 패널 숨김 */
        <div className="px-3 py-3">
          <div className="text-[8px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
            이미지 내용 분석
          </div>
          <div className="text-[11px] font-mono text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap">
            {diag.vlm_scene || diag.model_discussion || '분석 결과가 여기에 표시됩니다.'}
          </div>
          {diag.device === 'cpu' && diag.device_reason && (
            <div className="mt-3 text-[9px] font-mono text-[var(--red)] border border-red-500/20 bg-red-500/5 rounded p-2">
              ⚠ CPU 추론 실행 사유: {diag.device_reason}
            </div>
          )}
          <div className="mt-3 flex items-center gap-2">
            <span className="text-[8px] px-2 py-0.5 rounded border font-mono"
              style={{ color: '#38bdf8', borderColor: 'rgba(56,189,248,0.3)', background: 'rgba(56,189,248,0.06)' }}>
              CONTENT MODE
            </span>
            <span className="text-[8px] text-[var(--text-muted)] font-mono">
              이상탐지 미적용 (일반 이미지)
            </span>
          </div>
          {/* Latency는 내용 모드에서도 표시 */}
          <div className="mt-2 text-[9px] font-mono text-[var(--text-muted)]">
            {diag.inference_time_ms ? `Completed in ${diag.inference_time_ms}ms` : ''}
          </div>
        </div>
      ) : (
        <>
          {/* 3-card row */}
          <div
            className="grid gap-2.5 px-3 pt-2.5 pb-1.5"
            style={{ gridTemplateColumns: '1fr 74px 1fr' }}
          >
            {/* Anomaly Score */}
            <div className="diag-card">
              <div className="text-[8px] font-black uppercase tracking-widest text-[var(--text-muted)]">
                Anomaly Score
              </div>
              <div className="font-mono text-2xl font-light" style={{ color: scoreColor }}>
                {score.toFixed(2)}
              </div>
              <div className="relative h-1.5 bg-white/[0.04] rounded-full overflow-hidden mt-1">
                <div
                  className="absolute left-0 top-0 h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${progressPct}%`,
                    background: isAnomaly
                      ? 'linear-gradient(90deg,#fbbf24,#f87171)'
                      : 'linear-gradient(90deg,#4ade80,#38bdf8)',
                  }}
                />
                <div
                  className="absolute top-0 h-full w-0.5 bg-[#fbbf24]"
                  style={{ left: `${markerPct}%` }}
                />
              </div>
              <div className="flex justify-between items-center mt-1">
                {verdict ? (
                  <span style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: 10,
                                 color: verdictColor, letterSpacing: 1 }}>
                    판정: {verdict} {isNG ? '· 결함 감지' : '· 정상'}
                  </span>
                ) : <div />}
                <div className="text-[9px] font-mono text-[var(--text-muted)] text-right">
                  Thr: {threshold.toFixed(1)}
                </div>
              </div>
            </div>

            {/* Donut */}
            <DonutChart pct={diag.defect_probability_percent || 0} color={probColor} />

            {/* Latency */}
            <div className="diag-card">
              <div className="text-[8px] font-black uppercase tracking-widest text-[var(--text-muted)]">
                Inference Latency
              </div>
              <div className="font-mono text-2xl font-light" style={{ color: 'var(--green)' }}>
                {diag.inference_time_ms ?? 0}
                <span className="text-xs ml-1">ms</span>
              </div>
              <div className="text-[10px] font-mono text-[var(--text-muted)] mt-1">
                {diag.inference_time_ms
                  ? `Completed in ${diag.inference_time_ms}ms`
                  : 'Engine Idle'}
              </div>
            </div>
          </div>

          {diag.device === 'cpu' && diag.device_reason && (
            <div className="mx-3 mb-2 px-2.5 py-1.5 rounded-lg border border-red-500/20 bg-red-500/5 text-[9px] font-mono text-[var(--red)]">
              ⚠ CPU 추론 실행 사유: {diag.device_reason}
            </div>
          )}

          {/* Discussion & Location */}
          <div className="grid grid-cols-2 gap-2.5 px-3 pb-2.5">
            <div
              className="rounded-xl p-2.5 flex flex-col gap-1 border"
              style={{ background: 'rgba(0,0,0,0.2)', borderColor: 'rgba(63,63,70,0.3)' }}
            >
              <div
                className="text-[8px] font-black uppercase tracking-widest"
                style={{ color: 'var(--cyan)' }}
              >
                Agent Discussion
              </div>
              <div className="text-[10px] leading-snug text-[var(--text-secondary)] max-h-10 overflow-y-auto scrollbar-none">
                {diag.model_discussion || '모델 선택 및 적합성 평가 대기 중...'}
              </div>
            </div>
            <div
              className="rounded-xl p-2.5 flex flex-col gap-1 border"
              style={{ background: 'rgba(0,0,0,0.2)', borderColor: 'rgba(63,63,70,0.3)' }}
            >
              <div
                className="text-[8px] font-black uppercase tracking-widest"
                style={{ color: 'var(--orange)' }}
              >
                Defect Location
              </div>
              <div
                className="text-[10px] leading-snug max-h-10 overflow-y-auto scrollbar-none"
                style={{ color: isAnomaly ? 'var(--orange)' : 'var(--green)' }}
              >
                {isAnomaly
                  ? (diag.defect_location_description || '결함 위치 파악 중...')
                  : '정상 상태. 감지된 표면 결함 없음.'}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}


// ── CSS Spinner ──────────────────────────────────────────────────
function SpinnerRing({ size = 36, color = 'var(--cyan)' }) {
  return (
    <div
      style={{
        width: size, height: size,
        borderRadius: '50%',
        border: `2px solid rgba(56,189,248,0.15)`,
        borderTopColor: color,
        animation: 'spin-ring 0.9s linear infinite',
      }}
    />
  )
}

// ── InspectionViewer Main ────────────────────────────────────────────
function isAgentStatusMap(obj) {
  return obj && typeof obj === 'object' && !Array.isArray(obj)
}

export default function InspectionViewer({ beaconState = 'idle', onDiagnosticUpdate, onAgentStatus }) {
  const [file, setFile]               = useState(null)
  const [preview, setPreview]         = useState(null)
  const [heatmapUrl, setHeatmapUrl]   = useState(null)
  const [isDragging, setIsDragging]   = useState(false)
  const [isScanning, setIsScanning]   = useState(false)
  const [scanMs, setScanMs]           = useState(0)
  const [hudOn, setHudOn]             = useState(false)    // HUD overlay toggle
  const [autoScout, setAutoScout]     = useState(false)
  const [isAnomaly, setIsAnomaly]     = useState(false)
  const [diag, setDiag]               = useState({})
  const [modelTag, setModelTag]       = useState(null)

  const fileInputRef = useRef(null)
  const timerRef     = useRef(null)

  const handleFileSelect = useCallback((f) => {
    if (!f || !f.type.startsWith('image/')) return
    setFile(f)
    setPreview(URL.createObjectURL(f))
    setHeatmapUrl(null)
    setHudOn(false)
    setIsAnomaly(false)
    setDiag({})
    setModelTag(null)
  }, [])

  // 파일 선택 즉시 분석
  useEffect(() => {
    if (file) handleAnalyze()
  }, [file]) // eslint-disable-line

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setIsDragging(false)
    const f = e.dataTransfer.files?.[0]
    if (f) handleFileSelect(f)
  }, [handleFileSelect])

  const handleAnalyze = useCallback(async () => {
    if (!file || isScanning) return
    setIsScanning(true)
    setScanMs(0)

    const start = Date.now()
    onDiagnosticUpdate?.({ status: 'inspecting' })
    timerRef.current = setInterval(() => setScanMs(Date.now() - start), 16)

    try {
      const data = await analyzeImage(file, autoScout)
      clearInterval(timerRef.current)

      const detected = data.status === 'anomaly' || data.status === 'detected'
      setIsAnomaly(detected)
      setDiag(data)
      setModelTag(data.model_used || null)
      if (data.heatmap_url) {
        // BASE_URL='' 이면 상대경로로 Vite proxy를 통해 로드
        setHeatmapUrl(`${BASE_URL}${data.heatmap_url}?t=${Date.now()}`)
        setHudOn(true)   // 결과 나오면 HUD 자동 ON
      }
      onDiagnosticUpdate?.(data)

      // [§3 LED] HTTP 응답 body에 포함된 agents_status 스냅샷을 바로 Dashboard에 전달
      // WS 타이밍에 의존하지 않고 일관성 있는 LED 업데이트 보장
      if (onAgentStatus && isAgentStatusMap(data.agents_status)) {
        Object.entries(data.agents_status).forEach(([agent, msg]) => {
          const state  = msg.state  || 'ok'
          const detail = msg.detail || msg.message || ''
          onAgentStatus({ agent, state, detail })
        })
      }
    } catch (e) {
      clearInterval(timerRef.current)
      setDiag({ status: 'error' })
      alert(`❌ 분석 실패: ${e.message}`)
    } finally {
      setIsScanning(false)
    }
  }, [file, isScanning, autoScout, onDiagnosticUpdate])

  const handleReset = () => {
    clearInterval(timerRef.current)
    setFile(null); setPreview(null); setHeatmapUrl(null)
    setIsScanning(false); setScanMs(0); setHudOn(false)
    setIsAnomaly(false); setDiag({}); setModelTag(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const isContentMode = diag.status === 'content' || diag.image_domain === 'general_object'
  const threshold     = diag.threshold || 15.0
  const score         = diag.score
  const hasScore      = score != null && !isContentMode
  const isNG          = hasScore && score > threshold
  const verdict       = !hasScore ? null : (isNG ? 'NG' : 'OK')
  const verdictColor  = isNG ? '#f87171' : '#34d399'

  return (
    <div className="flex flex-col gap-2.5 h-full min-h-0">

      {/* ── Visual Analysis Panel ── */}
      <div
        className="glass-panel flex flex-col flex-1 min-h-0 transition-all duration-300"
        style={isAnomaly ? {
          borderColor: 'rgba(248,113,113,0.4)',
          boxShadow: 'inset 0 0 24px rgba(248,113,113,0.08), 0 8px 32px rgba(0,0,0,0.55)',
        } : {}}
      >
        {/* Header */}
        <div className="panel-header flex-shrink-0">
          <span className="panel-label">
            <Eye size={12} style={{ color: 'var(--cyan)' }} />
            Vision HUD
          </span>

          {/* HUD toggle (히트맵 있을 때) */}
          <div className="flex items-center gap-3">
            {heatmapUrl && (
              <HudToggle
                enabled={hudOn}
                onChange={setHudOn}
                label="Overlay"
              />
            )}
          </div>
        </div>

        {/* Image Area */}
        <div
          className="flex-1 min-h-0 m-3 rounded-xl overflow-hidden relative"
          style={{ background: 'rgba(0,0,0,0.6)', border: '1px solid rgba(63,63,70,0.3)' }}
        >
          {/* StatusBeacon 마운트 (우상단 플로팅 안돈 라이트) */}
          <div className="absolute right-4 top-4 z-40 transition-all duration-300">
            <StatusBeacon state={beaconState} />
          </div>
          {/* Critical Anomaly Banner */}
          {isAnomaly && (
            <div
              className="absolute top-3 left-0 right-0 z-50 text-center py-1.5 text-[12px] font-black tracking-widest"
              style={{
                background: 'rgba(248,113,113,0.92)',
                color: '#000',
                borderTop: '2px solid #ef4444',
                borderBottom: '2px solid #ef4444',
                boxShadow: '0 0 30px rgba(248,113,113,0.7)',
                animation: 'eva-blink 0.8s infinite alternate',
              }}
            >
              ⚠ CRITICAL ANOMALY DETECTED ⚠
            </div>
          )}

          {/* Scanning Overlay */}
          {isScanning && (
            <div className="absolute inset-0 z-40 flex flex-col items-center justify-center gap-4"
              style={{ background: 'rgba(9,9,11,0.85)' }}>
              <SpinnerRing size={44} />
              <div className="text-[12px] font-bold" style={{ color: 'var(--cyan)' }}>
                {autoScout
                  ? '🤖 Auto Scout — HuggingFace 탐색 중'
                  : '⚡ ARIA 추론 엔진 가동 중'}
                <span className="typewriter-cursor" />
              </div>
              <div className="font-mono text-[10px] text-[var(--text-muted)]">
                {scanMs.toLocaleString()}ms
              </div>
            </div>
          )}

          {/* Drop Zone */}
          {!preview ? (
            <div
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className="w-full h-full flex flex-col items-center justify-center gap-4 cursor-pointer
                         rounded-xl border-2 border-dashed transition-all duration-200"
              style={{
                borderColor: isDragging ? 'var(--cyan)' : 'rgba(56,189,248,0.2)',
                background: isDragging ? 'rgba(56,189,248,0.04)' : 'transparent',
              }}
            >
              <Camera
                size={48}
                style={{ color: 'var(--cyan)', opacity: isDragging ? 1 : 0.5 }}
              />
              <div className="text-center">
                <div className="text-[13px] font-bold text-[var(--text-secondary)]">
                  결함 이미지 업로드
                </div>
                <div className="text-[10px] font-mono text-[var(--text-muted)] mt-1">
                  드래그 & 드롭 또는 클릭 · PNG / JPG / BMP
                </div>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => handleFileSelect(e.target.files?.[0])}
              />
            </div>
          ) : (
            /* Image + Heatmap Overlay */
            <div className="w-full h-full relative flex items-center justify-center">
              <img
                src={preview}
                alt="Source Specimen"
                className="absolute inset-0 w-full h-full object-contain p-3"
              />
              {heatmapUrl && (
                <img
                  src={heatmapUrl}
                  alt="Defect Heatmap"
                  className="absolute inset-0 w-full h-full object-contain p-3 z-10 pointer-events-none transition-opacity duration-300"
                  style={{ opacity: hudOn ? 0.78 : 0 }}
                />
              )}
              {heatmapUrl && (
                <span style={{ position: 'absolute', bottom: 8, left: 8, zIndex: 5,
                  fontFamily: 'monospace', fontSize: 10, color: '#9aa0aa',
                  background: 'rgba(0,0,0,0.5)', padding: '2px 6px', borderRadius: 4 }}>
                  결함 영역 (히트맵)
                </span>
              )}
              {verdict && (
                <div style={{
                  position: 'absolute', top: 16, left: '50%', transform: 'translateX(-50%)',
                  zIndex: 5, padding: '6px 30px', borderRadius: 10,
                  fontFamily: 'monospace', fontSize: 34, fontWeight: 700, letterSpacing: 6,
                  color: verdictColor, background: 'rgba(0,0,0,0.55)',
                  border: `2px solid ${verdictColor}`, boxShadow: `0 0 26px ${verdictColor}66`,
                }}>
                  {verdict}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Action Console (Icon Pills) ── */}
        <div
          className="flex items-center gap-2 px-3 pb-3 pt-2 flex-shrink-0 border-t"
          style={{ borderColor: 'rgba(63,63,70,0.3)' }}
        >
          {/* Upload */}
          <button
            onClick={() => fileInputRef.current?.click()}
            className="action-pill"
            title="이미지 업로드"
          >
            <Camera size={16} style={{ color: 'var(--cyan)' }} />
            <span style={{ fontSize: '8px', color: 'var(--text-muted)' }}>Upload</span>
          </button>

          {/* Reset */}
          <button
            onClick={handleReset}
            disabled={!file}
            className="action-pill"
            title="초기화"
          >
            <RotateCcw size={14} style={{ color: 'var(--violet)' }} />
            <span style={{ fontSize: '8px', color: 'var(--text-muted)' }}>Reset</span>
          </button>

          {/* Analyze — glowing when ready */}
          <button
            onClick={handleAnalyze}
            disabled={!file || isScanning}
            className="action-pill"
            title="분석 실행"
            style={file && !isScanning ? {
              borderColor: 'var(--cyan)',
              background: 'rgba(56,189,248,0.06)',
              animation: 'glow-pulse 1.5s ease-in-out infinite alternate',
            } : {}}
          >
            <Zap size={16} style={{ color: file && !isScanning ? 'var(--cyan)' : 'var(--text-muted)' }} />
            <span style={{ fontSize: '8px', color: file && !isScanning ? 'var(--cyan)' : 'var(--text-muted)' }}>
              {isScanning ? '...' : 'Scan'}
            </span>
          </button>

          {/* Spacer */}
          <div className="flex-1" />

          {/* Auto Scout toggle */}
          <label className="flex flex-col items-center gap-1 cursor-pointer">
            <div
              className="action-pill"
              style={autoScout ? {
                borderColor: 'var(--violet)',
                background: 'rgba(167,139,250,0.08)',
                color: 'var(--violet)',
              } : {}}
              onClick={() => setAutoScout(!autoScout)}
            >
              <Activity size={14} style={{ color: autoScout ? 'var(--violet)' : 'var(--text-muted)' }} />
              <span style={{ fontSize: '8px', color: autoScout ? 'var(--violet)' : 'var(--text-muted)' }}>
                Scout
              </span>
            </div>
          </label>
        </div>
      </div>

      {/* ── Diagnostic Report ── */}
      <div className="flex-shrink-0">
        <DiagnosticReport diag={diag} modelTag={modelTag} isScanning={isScanning} scanMs={scanMs} />
      </div>
    </div>
  )
}
