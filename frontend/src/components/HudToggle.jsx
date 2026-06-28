/**
 * HudToggle.jsx — AR HUD 토글 스위치
 * 원본 이미지 ↔ 분석 결과 히트맵 교차 검증 컨트롤
 */

export default function HudToggle({ enabled, onChange, label = 'HUD' }) {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none group">
      {/* Track */}
      <div
        onClick={() => onChange(!enabled)}
        className={`hud-toggle-track ${enabled ? 'on' : ''}`}
        role="switch"
        aria-checked={enabled}
        aria-label={label}
      >
        <div className="hud-toggle-thumb" />
      </div>

      {/* Label */}
      <span
        className="text-[9px] font-black uppercase tracking-widest transition-colors"
        style={{ color: enabled ? 'var(--cyan)' : 'var(--text-muted)' }}
      >
        {label}
      </span>
    </label>
  )
}
