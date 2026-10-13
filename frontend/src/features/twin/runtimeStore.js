import { create } from 'zustand'
import { subscribeType } from '../../hmi/signalFanout'
import { factoryApi } from '../../hmi/factory/factoryStore'
import { reconcilePoses, engineEvents } from './presentation'
import { useSelection } from './selectionStore'
import { siteEntity } from '../site/spatial'
export const diagnostics = { enabled: typeof location !== 'undefined' && new URLSearchParams(location.search).has('measure'), snapshots: [], frames: [], renders: {}, camera: [], production: [] }
if (diagnostics.enabled) window.__ARIA_V2_METRICS__ = diagnostics
export function countRender(name) { if (diagnostics.enabled) diagnostics.renders[name] = (diagnostics.renders[name] || 0) + 1 }
const initialPose = { run: null, time: -1, targets: [] }
export const useRuntime = create((set, get) => ({
  snapshot: null, model: null, modelKey: '', site: null, definition: null, definitionKey: '', patrol: null, poses: initialPose, events: [],
  receivedAt: 0, patrolAt: 0, now: Date.now(), error: '', busy: false,
  receive: snapshot => {
    if (!snapshot?.model || !snapshot?.metrics) return
    const prev = get(), modelKey = JSON.stringify(snapshot.model)
    const poses = reconcilePoses(prev.poses, snapshot)
    if (diagnostics.enabled) { diagnostics.snapshots.push(performance.now()); if (diagnostics.snapshots.length > 2000) diagnostics.snapshots.shift() }
    set({ snapshot, poses, modelKey, model: modelKey === prev.modelKey ? prev.model : snapshot.model,
      events: engineEvents(snapshot), receivedAt: Date.now(), error: snapshot.error || snapshot.storage_error || '' })
    const id = useSelection.getState().selected
    if (poses.reset || (id && !siteEntity(get().definition,get().site,id))) useSelection.getState().overview()
  },
  receiveSite: site => {
    if(!site?.definition || !site?.production)return
    const key=JSON.stringify(site.definition),previous=get()
    set({site,definitionKey:key,definition:key===previous.definitionKey?previous.definition:site.definition})
    get().receive(site.production)
    if(site.error)set({error:site.error})
  },
  receivePatrol: patrol => set({ patrol, patrolAt: Date.now() }),
  refresh: async () => {
    // Reject an old HTTP reply if a newer WS frame arrived while it was in flight.
    const before = get().receivedAt, patrolBefore = get().patrolAt
    await Promise.all([
      factoryApi('/site/snapshot').then(s => { if (get().receivedAt === before) get().receiveSite(s) }),
      factoryApi('/patrol').then(p => { if (get().patrolAt === patrolBefore) get().receivePatrol(p) }),
    ]).catch(e => set({ error: e.message }))
  },
  action: async (path, body = {}) => {
    if (get().busy) return
    set({ busy: true, error: '' })
    try { const result = await factoryApi('/site/control'+path, body); if (result.production) get().receiveSite(result); else await get().refresh(); return result }
    catch (e) { set({ error: e.message }) }
    finally { set({ busy: false }) }
  },
}))
if(diagnostics.enabled) window.__ARIA_SET_FIXTURE__=site=>useRuntime.getState().receiveSite(site)
export function connectRuntime() {
  if(diagnostics.enabled && new URLSearchParams(location.search).has('fixture'))return ()=>{}

  const a = subscribeType('site_state', s => useRuntime.getState().receiveSite(s))
  const b = subscribeType('patrol_state', p => useRuntime.getState().receivePatrol(p))
  useRuntime.getState().refresh()
  // Polling also recovers a paused snapshot after a WebSocket reconnect.
  const clock = setInterval(() => useRuntime.setState({ now: Date.now() }), 1000)
  const poll = setInterval(() => useRuntime.getState().refresh(), 5000)
  return () => { a(); b(); clearInterval(clock); clearInterval(poll) }
}
export const productionStale = s => !s.receivedAt || s.now - s.receivedAt > 8000
export const patrolStale = s => !s.patrolAt || s.now - s.patrolAt > 8000
