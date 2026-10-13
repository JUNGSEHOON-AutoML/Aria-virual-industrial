import { useEffect, useState } from 'react'
import { Boxes, LayoutDashboard, Wrench, ScanLine, Sparkles, Activity } from 'lucide-react'
import Overview from './Overview'
import EngineeringWorkspace from '../engineering/EngineeringWorkspace'
import AgentDrawer from '../agent/AgentDrawer'
import { connectRuntime } from '../twin/runtimeStore'
import './controlTower.css'
export default function ControlTowerShell({ onOpenQC }) {
  const [page, setPage] = useState('overview'), [agentOpen, setAgentOpen] = useState(false)
  useEffect(connectRuntime, [])
  return <div className="ct-shell">
    <nav className="ct-nav" aria-label="Workspaces">
      <div className="ct-brand" title="ARIA"><Boxes size={25} /></div>
      <button aria-label="Overview" title="Overview" className={page === 'overview' ? 'active' : ''} onClick={() => setPage('overview')}><LayoutDashboard size={21}/><span>Overview</span></button>
      <button aria-label="Engineering" title="Engineering" className={page === 'engineering' ? 'active' : ''} onClick={() => setPage('engineering')}><Wrench size={21}/><span>Engineer</span></button>
      <button aria-label="QC Live" title="QC Live" onClick={onOpenQC}><ScanLine size={21}/><span>Quality</span></button>
      <div className="ct-nav-spacer"/><button aria-label="Ask ARIA" title="Ask ARIA" onClick={() => setAgentOpen(true)}><Sparkles size={22}/><span>Ask ARIA</span></button>
      <div className="ct-avatar">A</div>
    </nav>
    <main className="ct-main">
      <header className="ct-header"><div className="ct-wordmark">ARIA<span> / </span><strong>{page === 'overview' ? 'Control tower' : 'Engineering'}</strong></div><div className="ct-header-right"><span><Activity size={14}/> Industrial digital twin</span><button className="ct-button ct-primary" onClick={() => setAgentOpen(true)}><Sparkles size={15}/> Ask ARIA</button></div></header>
      {page === 'overview' ? <Overview onAsk={() => setAgentOpen(true)}/> : <EngineeringWorkspace/>}
    </main>
    <AgentDrawer scope={page==='overview'?'site':'factory'} open={agentOpen} onClose={() => setAgentOpen(false)} onFocus={() => setPage(page)}/>
  </div>
}
