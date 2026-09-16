import { create } from 'zustand'
import { subscribeType } from '../signalFanout'

export async function factoryApi(path, body, method) {
  const response = await fetch(`/api/factory${path}`, {
    method: method || (body === undefined ? 'GET' : 'POST'),
    headers: { 'Content-Type': 'application/json' },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  })
  const result = await response.json()
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail || result))
  return result
}
export const useFactory = create((set, get) => ({
  snapshot: null, selected: null, error: '', busy: false, proposal: null,
  messages: [], experiment: null, scenarios: [], patrol: null,
  select: selected => set({ selected }),
  receive: snapshot => set({ snapshot }),
  refresh: async () => { try { const [snapshot, patrol] = await Promise.all([factoryApi('/snapshot'), factoryApi('/patrol')]); set({ snapshot, patrol }) } catch (e) { set({ error: e.message }) } },
  action: async (path, body = {}, method) => {
    set({ busy: true, error: '' })
    try {
      const result = await factoryApi(path, body, method)
      if (result.status === 'pending') set({ proposal: result })
      if (result.model && result.metrics) set({ snapshot: result })
      return result
    } catch (e) { set({ error: e.message }); return null }
    finally { set({ busy: false }) }
  },
  decide: async decision => {
    const p = get().proposal
    if (!p) return
    const result = await get().action(`/proposals/${p.id}/${decision}`)
    if (result) { set({ proposal: null }); await get().refresh() }
  },
  chat: async message => {
    set(s => ({ messages: [...s.messages.slice(-29), { role: 'user', text: message }], busy: true, error: '' }))
    try {
      const result = await factoryApi('/agent', { message })
      set(s => ({ messages: [...s.messages, { role: 'agent', text: result.answer, route: result.route, trace: result.trace }],
        proposal: result.proposal || s.proposal,
        experiment: result.evidence?.candidates ? result.evidence : s.experiment }))
      await get().refresh()
    } catch (e) { set({ error: e.message }) }
    finally { set({ busy: false }) }
  },
  loadScenarios: async () => { try { set({ scenarios: await factoryApi('/scenarios') }) } catch (e) { set({ error: e.message }) } },
}))

export function subscribeFactory() {
  const state = subscribeType('simulation_state', message => useFactory.getState().receive(message))
  const patrol = subscribeType('patrol_state', message => useFactory.setState({ patrol: message }))
  return () => { state(); patrol() }
}
