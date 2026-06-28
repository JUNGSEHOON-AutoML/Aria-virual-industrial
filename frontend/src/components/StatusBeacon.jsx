import React from 'react'

const LABELS = {
  idle: 'STANDBY',
  inspecting: 'INSPECTING',
  pass: 'PASS',
  fail: 'DEFECT',
  content: 'CONTENT'
}

export default function StatusBeacon({ state = 'idle' }) {
  return (
    <div className={`beacon beacon--${state}`} role="status" aria-label={LABELS[state]}>
      <div className="beacon__lamps">
        <span className="lamp lamp--red" />
        <span className="lamp lamp--amber" />
        <span className="lamp lamp--green" />
        <span className="lamp lamp--blue" />
      </div>
      <div className="beacon__label">{LABELS[state]}</div>
    </div>
  )
}
