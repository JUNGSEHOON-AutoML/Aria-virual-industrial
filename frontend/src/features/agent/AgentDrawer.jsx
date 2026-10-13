import { useEffect, useRef, useState } from 'react'
import { Sparkles, X, Send, ArrowUpRight } from 'lucide-react'
import { factoryApi, useFactory } from '../../hmi/factory/factoryStore'
import { useRuntime } from '../twin/runtimeStore'
import { useSelection } from '../twin/selectionStore'
import { staticEntities } from '../site/spatial'
import { evidenceComponent, formatValue } from '../twin/presentation'
export default function AgentDrawer({ open, onClose, onFocus, scope = 'site' }) {
  const [messages,setMessages] = useState([]), [text,setText] = useState(''), [busy,setBusy] = useState(false), [error,setError] = useState(''), [proposal,setProposal] = useState(null), [evidence,setEvidence] = useState(null)
  const input = useRef(), panel = useRef(), pending = useRef(false)
  useEffect(()=>{setMessages([]);setProposal(null);setEvidence(null);setError('')},[scope])
  useEffect(()=>{ if (!open) return; const previous=document.activeElement; input.current?.focus(); return ()=>previous?.focus?.() },[open])
  async function ask(message) {
    if (!message.trim() || pending.current) return
    pending.current=true; setBusy(true);setError('');setText('');setMessages(m=>[...m,{role:'user',text:message}])
    try {
      const r=await factoryApi('/agent',{message,scope})
      const runtime=useRuntime.getState()
      const ids=scope==='site'?[...staticEntities(runtime.definition),...(runtime.site?.trucks||[]),...(runtime.site?.forklifts||[]),...(runtime.site?.shipments||[]),...(runtime.site?.pallets||[])].map(e=>e.id):(useFactory.getState().snapshot?.model.components||[]).map(c=>c.id)
      const id=evidenceComponent(r,ids)
      setMessages(m=>[...m,{role:'agent',text:r.answer,trace:r.trace,route:r.route,asset:id}])
      if(r.proposal)setProposal(r.proposal)
      if(r.evidence?.candidates)setEvidence(r.evidence)
      if(id){(scope==='site'?useSelection:useFactory).getState().select(id);onFocus()}
      await useRuntime.getState().refresh()
    } catch(e){setError(e.message)} finally{pending.current=false;setBusy(false)}
  }
  async function decide(decision) {
    if(pending.current || !proposal)return
    pending.current=true;setBusy(true);setError('')
    try {await factoryApi(`/proposals/${proposal.id}/${decision}`,{});setProposal(null);await useRuntime.getState().refresh()}
    catch(e){setError(e.message)}finally{pending.current=false;setBusy(false)}
  }
  if (!open) return null
  return <div className="ct-drawer-backdrop" onClick={onClose}><aside ref={panel} className="ct-agent" role="dialog" aria-modal="true" aria-label="Ask ARIA" onClick={e=>e.stopPropagation()} onKeyDown={e=>{
    if(e.key==='Escape')onClose()
    if(e.key==='Tab'){const all=[...panel.current.querySelectorAll('button:not(:disabled),input,summary')];const first=all[0],last=all[all.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}
  }}><div className="ct-agent-heading"><div><Sparkles size={21}/><h2>Ask ARIA · {scope==='site'?'Site':'Engineering'}</h2></div><button className="ct-icon-button" aria-label="Close Ask ARIA" onClick={onClose}><X size={20}/></button></div><p className="ct-agent-intro">{scope==='site'?'Query recorded site state, dock occupancy and shipment history. Site optimization is not implemented.':'Understand the line. Review changes before applying them.'}</p>
    <div className="ct-prompts">{(scope==='site'?['Which dock is congested?','Where is SHIPMENT-101?','Why is TRUCK-02 still waiting?']:['현재 상태를 알려줘','현재 병목을 분석해줘','처리량 10% 개선']).map(q=><button className="ct-button" disabled={busy} key={q} onClick={()=>ask(q)}>{q}<ArrowUpRight size={13}/></button>)}</div>
    <div className="ct-conversation" aria-live="polite">{messages.length===0 && <div className="ct-agent-empty"><Sparkles size={34}/><h3>Grounded in your factory</h3><p>Responses use the existing industrial agent and its recorded tool results.</p></div>}{messages.map((m,i)=><article className={`ct-message ${m.role}`} key={i}><span>{m.role==='user'?'YOU':'ARIA'}</span><p>{m.text}</p>{m.asset&&<button className="ct-button" onClick={()=>{(scope==='site'?useSelection:useFactory).getState().select(m.asset);onFocus();onClose()}}>Locate {m.asset}<ArrowUpRight size={13}/></button>}{m.trace?.length>0&&<details><summary>{m.trace.length} tool results · {m.route}</summary>{m.trace.map((t,j)=><div className="ct-trace" key={j}><b>{t.tool}</b><pre>{JSON.stringify({arguments:t.arguments,result:t.result},null,2)}</pre></div>)}</details>}</article>)}{busy&&<p className="ct-muted" role="status">Working…</p>}</div>
    {evidence&&<details className="ct-experiment"><summary>Measured scenario comparison</summary><p>Independent simulations · {evidence.component}</p><pre>{JSON.stringify(evidence,null,2)}</pre></details>}
    {proposal&&<section className="ct-proposal" aria-label="Proposal review"><h3>Change awaiting your approval</h3><p>{proposal.summary || proposal.description || proposal.id}</p><p>Apply resets production. Revision {formatValue(proposal.revision)} is checked by the server.</p><details><summary>Review before / after & evidence</summary><pre>{JSON.stringify(proposal,null,2)}</pre></details><div><button className="ct-button" disabled={busy} onClick={()=>decide('reject')}>Reject</button><button className="ct-button ct-primary" disabled={busy} onClick={()=>decide('apply')}>Apply</button></div></section>}
    {error&&<p role="alert" className="ct-error">{error}</p>}
    <form className="ct-agent-input" onSubmit={e=>{e.preventDefault();ask(text)}}><input ref={input} aria-label="Agent message" value={text} onChange={e=>setText(e.target.value)} placeholder="Ask about this factory…" disabled={busy}/><button className="ct-icon-button" aria-label="Send" disabled={busy||!text.trim()}><Send size={19}/></button></form><small className="ct-agent-foot">Proposals require explicit Apply. No automatic layout changes.</small>
  </aside></div>
}
