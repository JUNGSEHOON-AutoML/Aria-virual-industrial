import { useState, useEffect } from 'react'
import { fetchHardware } from '../api/apiClient'
import { Cpu, Thermometer, ShieldCheck, ShieldAlert } from 'lucide-react'

export default function HardwarePanel() {
  const [hw, setHw] = useState(null)

  useEffect(() => {
    const poll = async () => {
      try {
        const data = await fetchHardware()
        setHw(data)
      } catch (e) {
        console.error('Failed to fetch hardware stats:', e)
      }
    }
    poll()
    const id = setInterval(poll, 2000)
    return () => clearInterval(id)
  }, [])

  if (!hw) {
    return (
      <div className="glass-panel p-3.5 flex flex-col gap-2">
        <div className="text-[10px] font-mono text-[var(--text-muted)] text-center py-2">
          Loading hardware telemetry...
        </div>
      </div>
    )
  }

  return (
    <div className="glass-panel p-3 flex flex-col gap-3.5">
      <div className="panel-header flex-shrink-0">
        <span className="panel-label">
          <Cpu size={12} style={{ color: 'var(--cyan)' }} />
          System Resources
        </span>
        <span className="text-[8px] font-mono font-bold px-1.5 py-0.5 rounded border flex items-center gap-1"
              style={{
                color: hw.cuda_available ? 'var(--green)' : 'var(--red)',
                borderColor: hw.cuda_available ? 'rgba(74,222,128,0.2)' : 'rgba(239,68,68,0.2)',
                background: hw.cuda_available ? 'rgba(74,222,128,0.06)' : 'rgba(239,68,68,0.06)'
              }}>
          {hw.cuda_available ? <ShieldCheck size={10} /> : <ShieldAlert size={10} />}
          {hw.cuda_available ? 'CUDA ACTIVE' : 'CPU MODE'}
        </span>
      </div>

      {/* CPU Usage */}
      <div className="flex flex-col gap-1.5">
        <div className="flex justify-between text-[9px] font-mono text-[var(--text-secondary)]">
          <span>CPU Utilization</span>
          <span className="font-bold">{hw.cpu_pct !== null ? `${hw.cpu_pct.toFixed(1)}%` : 'N/A'}</span>
        </div>
        <div className="w-full h-1.5 bg-black/40 rounded-full overflow-hidden border border-white/[0.04]">
          <div className="h-full rounded-full transition-all duration-500"
               style={{
                 width: `${hw.cpu_pct ?? 0}%`,
                 background: 'linear-gradient(90deg, var(--cyan), var(--blue))',
                 boxShadow: '0 0 6px var(--cyan)'
               }}
          />
        </div>
      </div>

      {/* System RAM Usage */}
      <div className="flex flex-col gap-1.5">
        <div className="flex justify-between text-[9px] font-mono text-[var(--text-secondary)]">
          <span>System RAM</span>
          <span>
            {hw.ram_used_mb !== null && hw.ram_total_mb !== null
              ? `${hw.ram_used_mb}MB / ${hw.ram_total_mb}MB`
              : 'N/A'}
          </span>
        </div>
        <div className="w-full h-1.5 bg-black/40 rounded-full overflow-hidden border border-white/[0.04]">
          <div className="h-full rounded-full transition-all duration-500"
               style={{
                 width: `${hw.ram_used_mb && hw.ram_total_mb ? (hw.ram_used_mb / hw.ram_total_mb * 100) : 0}%`,
                 background: 'linear-gradient(90deg, var(--cyan), var(--violet))'
               }}
          />
        </div>
      </div>

      {/* GPU Devices */}
      {hw.gpus && hw.gpus.length > 0 ? (
        hw.gpus.map((gpu) => {
          const vramPct = gpu.vram_total_mb ? (gpu.vram_used_mb / gpu.vram_total_mb * 100) : 0
          return (
            <div key={gpu.index} className="flex flex-col gap-2.5 pt-2 border-t border-white/[0.04]">
              <div className="flex items-center justify-between text-[9px] font-mono font-bold text-[var(--cyan)]">
                <span className="truncate max-w-[120px]">{gpu.name}</span>
                <span className="flex items-center gap-1 shrink-0">
                  <Thermometer size={10} />
                  {gpu.temp_c}°C
                </span>
              </div>
              
              {/* GPU Core Util */}
              <div className="flex flex-col gap-1">
                <div className="flex justify-between text-[8px] font-mono text-[var(--text-muted)]">
                  <span>GPU Core</span>
                  <span>{gpu.util_pct}%</span>
                </div>
                <div className="w-full h-1 bg-black/40 rounded-full overflow-hidden border border-white/[0.04]">
                  <div className="h-full rounded-full transition-all duration-500"
                       style={{
                         width: `${gpu.util_pct}%`,
                         background: 'var(--cyan)'
                       }}
                  />
                </div>
              </div>

              {/* VRAM Util */}
              <div className="flex flex-col gap-1">
                <div className="flex justify-between text-[8px] font-mono text-[var(--text-muted)]">
                  <span>VRAM</span>
                  <span>{gpu.vram_used_mb}MB / {gpu.vram_total_mb}MB</span>
                </div>
                <div className="w-full h-1 bg-black/40 rounded-full overflow-hidden border border-white/[0.04]">
                  <div className="h-full rounded-full transition-all duration-500"
                       style={{
                         width: `${vramPct}%`,
                         background: 'var(--violet)'
                       }}
                  />
                </div>
              </div>
            </div>
          )
        })
      ) : (
        <div className="flex items-center justify-center p-2 rounded-lg border border-dashed border-white/[0.08] bg-black/25">
          <span className="text-[8px] font-mono uppercase text-[var(--text-muted)]">
            GPU 미감지 / CPU 모드
          </span>
        </div>
      )}
    </div>
  )
}
