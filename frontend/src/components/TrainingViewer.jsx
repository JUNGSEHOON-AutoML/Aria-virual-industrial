import { useState } from 'react'
import { uploadTraining, intakeDataset } from '../api/apiClient'
import { UploadCloud, AlertOctagon } from 'lucide-react'

export default function TrainingViewer({ training }) {
  const [busy, setBusy] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [intakeResult, setIntakeResult] = useState(null)

  const onPick = async (e) => {
    const f = e.target.files?.[0]
    if (!f) return
    setBusy(true)
    setErrorMsg('')
    try {
      await uploadTraining(f)
    } catch (err) {
      setErrorMsg(err.message || '업로드 실패')
    } finally {
      setBusy(false)
    }
  }

  const onIntakePick = async (e) => {
    const f = e.target.files?.[0]
    if (!f) return
    setBusy(true)
    setErrorMsg('')
    try {
      const res = await intakeDataset(f)
      setIntakeResult(res)
    } catch (err) {
      setErrorMsg(err.message || '인테이크 실패')
    } finally {
      setBusy(false)
    }
  }

  const pct = training
    ? Math.round((training.step / training.total_steps) * 100)
    : 0

  return (
    <div className="glass-panel p-4 mb-2.5 flex flex-col items-center justify-center border transition-all duration-300"
         style={training ? { borderColor: 'var(--cyan)', boxShadow: '0 0 15px rgba(56,189,248,0.15)' } : {}}>
      
      <div className="w-full flex items-center justify-between mb-3 border-b border-white/[0.04] pb-2">
        <span className="text-[11px] font-black uppercase tracking-wider font-mono text-[var(--text-secondary)] flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--cyan)]" style={{ boxShadow: '0 0 6px var(--cyan)' }} />
          Training Control
        </span>
        {training && (
          <span className="text-[9px] font-mono font-bold px-2 py-0.5 rounded border uppercase tracking-wider"
                style={{
                  color: training.status === 'done' ? 'var(--green)' : 'var(--cyan)',
                  borderColor: training.status === 'done' ? 'rgba(74,222,128,0.2)' : 'rgba(56,189,248,0.2)',
                  background: training.status === 'done' ? 'rgba(74,222,128,0.06)' : 'rgba(56,189,248,0.06)'
                }}>
            {training.status}
          </span>
        )}
      </div>

      {!training ? (
        <div className="w-full flex flex-col items-center py-2 gap-3">
          <div className="flex gap-3">
            <label className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-white/[0.08] hover:border-[var(--cyan)] cursor-pointer transition-all whitespace-nowrap w-fit"
                   style={busy ? { opacity: 0.5, cursor: 'not-allowed' } : {}}>
              <UploadCloud size={16} className={busy ? 'animate-bounce text-[var(--text-muted)]' : 'text-[var(--cyan)]'} />
              <span className="text-[10px] font-mono font-bold tracking-wider text-[var(--text-secondary)] whitespace-nowrap">
                {busy ? '아카이브 압축해제 중...' : '데이터셋 업로드 (ZIP, TAR)'}
              </span>
              <input type="file" accept=".zip,.tar,.tar.gz,.tgz" hidden onChange={onPick} disabled={busy} />
            </label>

            <label className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-white/[0.08] hover:border-[var(--violet)] cursor-pointer transition-all whitespace-nowrap w-fit"
                   style={busy ? { opacity: 0.5, cursor: 'not-allowed' } : {}}>
              <UploadCloud size={16} className={busy ? 'animate-bounce text-[var(--text-muted)]' : 'text-[var(--violet)]'} />
              <span className="text-[10px] font-mono font-bold tracking-wider text-[var(--text-secondary)] whitespace-nowrap">
                {busy ? '인테이크 진행 중...' : '데이터셋 인테이크 (ZIP, TAR)'}
              </span>
              <input type="file" accept=".zip,.tar,.tar.gz,.tgz" hidden onChange={onIntakePick} disabled={busy} />
            </label>
          </div>
          {errorMsg && (
            <div className="mt-2 text-[9px] font-mono text-[var(--red)] flex items-center gap-1">
              <AlertOctagon size={10} />
              {errorMsg}
            </div>
          )}
        </div>
      ) : (
        <div className="w-full flex flex-col items-center gap-3">
          {training.preview_image && (
            <div className="relative rounded-xl overflow-hidden border border-white/[0.08] bg-black/40 p-1 flex items-center justify-center"
                 style={{ width: '100%', maxHeight: '180px' }}>
              <img
                src={training.preview_image.startsWith('/') ? training.preview_image : '/' + training.preview_image}
                alt="preview"
                className="max-h-[170px] object-contain rounded-lg"
              />
            </div>
          )}
          
          <div className="w-full flex flex-col gap-1.5">
            <div className="flex justify-between text-[9px] font-mono text-[var(--text-secondary)]">
              <span>Step {training.step} / {training.total_steps}</span>
              {training.metrics?.loss !== undefined && (
                <span>Loss: {training.metrics.loss.toFixed(4)}</span>
              )}
            </div>
            
            <div className="w-full h-2.5 bg-black/50 rounded-full overflow-hidden border border-white/[0.04]">
              <div
                className="h-full rounded-full transition-all duration-300"
                style={{
                  width: `${pct}%`,
                  background: 'linear-gradient(90deg, var(--cyan), var(--violet))',
                  boxShadow: '0 0 8px var(--cyan)'
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Intake Result Modal */}
      {intakeResult && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(6px)' }}
          onClick={() => setIntakeResult(null)}
        >
          <div
            className="glass-panel max-w-md w-full p-6 relative border transition-all duration-300"
            style={{
              borderColor: 'var(--violet)',
              boxShadow: '0 0 20px rgba(167,139,250,0.15)',
              maxHeight: '90vh',
              overflowY: 'auto'
            }}
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4 border-b border-white/[0.08] pb-2">
              <span className="text-[12px] font-black tracking-wider font-mono text-[var(--violet)] flex items-center gap-1.5 uppercase">
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--violet)]" style={{ boxShadow: '0 0 6px var(--violet)' }} />
                Dataset Intake Report
              </span>
              <button
                onClick={() => setIntakeResult(null)}
                className="text-[var(--text-muted)] hover:text-white text-lg font-mono leading-none transition-colors"
              >
                ×
              </button>
            </div>

            <div className="flex flex-col gap-4 text-[11px] font-mono text-[var(--text-secondary)]">
              {/* Domain Block */}
              <div className="bg-white/[0.02] p-3 rounded-lg border border-white/[0.04]">
                <div className="text-[9px] text-[var(--text-muted)] uppercase tracking-wider mb-1 font-bold">Detected Domain</div>
                <div className="text-[15px] font-black text-[var(--violet)] capitalize mb-1">
                  {intakeResult.domain?.domain || 'unknown'}
                </div>
                <div className="text-[9px] leading-relaxed text-[var(--text-secondary)] italic">
                  &ldquo;{intakeResult.domain?.rationale || 'No explanation provided.'}&rdquo;
                </div>
              </div>

              {/* Stats Grid */}
              <div className="grid grid-cols-2 gap-2">
                <div className="bg-white/[0.02] p-2.5 rounded-lg border border-white/[0.04]">
                  <div className="text-[8px] text-[var(--text-muted)] uppercase tracking-wider mb-0.5 font-bold">Total Images</div>
                  <div className="text-[13px] font-bold text-white">{intakeResult.n_images} pics</div>
                </div>
                <div className="bg-white/[0.02] p-2.5 rounded-lg border border-white/[0.04]">
                  <div className="text-[8px] text-[var(--text-muted)] uppercase tracking-wider mb-0.5 font-bold">Classes Found</div>
                  <div className="text-[13px] font-bold text-white">{Object.keys(intakeResult.classes || {}).length} cls</div>
                </div>
              </div>

              {/* Resolution Info */}
              {intakeResult.resolution?.w && (
                <div className="bg-white/[0.02] p-3 rounded-lg border border-white/[0.04]">
                  <div className="text-[9px] text-[var(--text-muted)] uppercase tracking-wider mb-1 font-bold">Resolution Range</div>
                  <div className="flex justify-between text-white mt-1">
                    <span>Width: {intakeResult.resolution.w[0]}px ~ {intakeResult.resolution.w[1]}px</span>
                    <span>Height: {intakeResult.resolution.h[0]}px ~ {intakeResult.resolution.h[1]}px</span>
                  </div>
                </div>
              )}

              {/* Format Distribution */}
              {intakeResult.formats && Object.keys(intakeResult.formats).length > 0 && (
                <div className="bg-white/[0.02] p-3 rounded-lg border border-white/[0.04]">
                  <div className="text-[9px] text-[var(--text-muted)] uppercase tracking-wider mb-1.5 font-bold">Format Distribution</div>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(intakeResult.formats).map(([ext, count]) => (
                      <span key={ext} className="bg-white/[0.05] px-2 py-1 rounded text-[10px] text-white border border-white/[0.02]">
                        {ext}: <span className="font-bold text-[var(--cyan)]">{count}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Classes Detail */}
              {intakeResult.classes && Object.keys(intakeResult.classes).length > 0 && (
                <div className="bg-white/[0.02] p-3 rounded-lg border border-white/[0.04]">
                  <div className="text-[9px] text-[var(--text-muted)] uppercase tracking-wider mb-1.5 font-bold">Classes & File Counts</div>
                  <div className="flex flex-col gap-1 max-h-[120px] overflow-y-auto pr-1">
                    {Object.entries(intakeResult.classes).map(([cls, count]) => (
                      <div key={cls} className="flex justify-between py-0.5 border-b border-white/[0.02]">
                        <span className="text-white capitalize">{cls}</span>
                        <span className="text-[var(--violet)]">{count} images</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
