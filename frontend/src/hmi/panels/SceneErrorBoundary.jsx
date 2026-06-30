// SceneErrorBoundary — 3D 씬 컴포넌트가 throw해도 블랙스크린 대신 메시지 표시(+콘솔 로그).
import { Component } from 'react'

export default class SceneErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { err: null } }
  static getDerivedStateFromError(err) { return { err } }
  componentDidCatch(err, info) { console.error('[ARIA 씬 오류]', err, info) }
  render() {
    if (this.state.err) {
      return (
        <div style={{ position: 'absolute', inset: 0, zIndex: 30, display: 'flex',
          flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10,
          background: 'rgba(20,8,10,0.9)', fontFamily: "'Courier New',monospace", padding: 24 }}>
          <div style={{ fontSize: 16, color: '#f87171', fontWeight: 700 }}>⛔ 3D 씬 오류</div>
          <div style={{ fontSize: 12, color: '#cbd5e1', maxWidth: 560, textAlign: 'center' }}>
            {String(this.state.err?.message || this.state.err)}
          </div>
          <button onClick={() => this.setState({ err: null })}
            style={{ marginTop: 8, fontFamily: 'inherit', fontSize: 12, padding: '6px 14px',
              borderRadius: 6, cursor: 'pointer', color: '#1FB8CD',
              background: 'rgba(31,184,205,0.12)', border: '1px solid #1FB8CD' }}>
            다시 시도
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
