"""Deterministic bounded logistics demo sharing the production Engine implementation.

Own runtime: the saved Engineering model is cloned, not overwritten. Source
arrivals are external here. Trucks/forklifts use graph routes; rendering cannot
advance state. Fixed 100ms quanta make chunking independent of browser cadence.
"""
import copy
import heapq
import math
import re
import threading
import uuid
from collections import deque
from .contract import build_site
from ...persistence.contracts import digest,envelope,utcnow,PersistenceFault
from ..des.engine import Engine
from ..des.model import FactoryModel

TRUCK_STATES={'PLANNED','ARRIVING','WAITING','ASSIGNED_TO_DOCK','DRIVING','DOCKED','LOADING','UNLOADING','DEPARTING','DEPARTED'}
FORKLIFT_STATES={'IDLE','ASSIGNED','TO_PICKUP','LOADING','TO_DESTINATION','UNLOADING','RETURNING'}
DOCK_STATES={'AVAILABLE','RESERVED','OCCUPIED','LOADING','UNLOADING','BLOCKED'}
SHIPMENT_STATES={'PLANNED','ARRIVING','AT_GATE','DOCK_ASSIGNED','UNLOADING','IN_PROCESS','READY_FOR_OUTBOUND','LOADING','DEPARTED','ON_HOLD'}

class RouteNetwork:
    def __init__(self, definition):
        self.nodes={n.id:list(n.position) for n in definition.transport_nodes}
        self.edges=definition.transport_edges
    def route(self, start, end, mode):
        if start not in self.nodes or end not in self.nodes:raise ValueError('Unknown transport node')
        queue=[(0.,start,[start])];visited=set()
        while queue:
            cost,node,path=heapq.heappop(queue)
            if node in visited:continue
            if node==end:return path
            visited.add(node)
            for e in sorted(self.edges,key=lambda e:e.id):
                nxt=e.target if e.source==node else e.source if e.bidirectional and e.target==node else None
                if nxt and mode in e.modes and nxt not in visited:
                    heapq.heappush(queue,(cost+math.dist(self.nodes[node],self.nodes[nxt]),nxt,path+[nxt]))
        raise ValueError(f'No {mode} route from {start} to {end}')
    def assign(self, vehicle, destination):
        path=self.route(vehicle['node'],destination,vehicle['kind'])
        vehicle.update(route=path,route_index=0,destination=destination)
    def advance(self, vehicle, dt):
        route=vehicle.get('route',[]);i=vehicle.get('route_index',0);remaining=vehicle['speed']*dt
        while i<len(route)-1:
            target=self.nodes[route[i+1]];pos=vehicle['position'];dist=math.dist(pos,target)
            if dist>1e-9:
                vehicle['heading']=math.atan2(target[0]-pos[0],target[2]-pos[2])
            if dist<=remaining+1e-9:
                vehicle['position']=list(target);remaining-=dist;i+=1;vehicle['node']=route[i]
            else:
                vehicle['position']=[a+(b-a)*remaining/dist for a,b in zip(pos,target)];break
        vehicle['route_index']=i
        return i>=len(route)-1

class SiteRuntime:
    def __init__(self, model, inspect=None, revision=0, history=None):
        self.lock=threading.RLock();self.inspect=inspect;self.history=history
        self.reset(model,revision)
    def reset(self, model=None, revision=None):
        with self.lock:
            if self.history:self.history.can_advance()
            self.model=FactoryModel.model_validate(model or self.model.model_dump())
            self.revision=revision if revision is not None else self.revision
            self.definition=build_site(self.model);self.network=RouteNetwork(self.definition)
            self.run_token=uuid.uuid4().hex;self.time=0.;self.steps=0;self.accumulator=0.
            self.status='paused';self.speed=1.;self.error=None;self.sequence=0;self.events=deque(maxlen=2048)
            self.history_context=dict(run_id=self.run_token,site_id=self.definition.sites[0].id,twin_revision=self.revision,site_definition_hash=digest(self.definition.model_dump()),definition=self.definition.model_dump(),model=self.model.model_dump(),seed=self.model.seed,started_at=utcnow())
            if self.history:self.history.register(self.history_context)
            self.shipments={};self.pallets={};self.workpieces={};self.trucks={};self.jobs=deque();self.job_ids=set()
            self.docks={d.id:dict(id=d.id,node=d.id+'-N',kind=d.kind,state='AVAILABLE',truck_id=None,shipment_id=None,blocked=False,since=0.) for d in self.definition.docks}
            self.forklifts={'FORKLIFT-01':dict(id='FORKLIFT-01',kind='forklift',state='IDLE',since=0.,node='FORK-HOME-N',position=list(self.network.nodes['FORK-HOME-N']),heading=0.,speed=3.,route=[],job=None,pallet_id=None)}
            for i in range(3):
                sid=f'SHIPMENT-{101+i}';pid=f'PALLET-{101+i}';tid=f'TRUCK-{i+1:02}';oid=f'TRUCK-OUT-{i+1:02}'
                wp=[f'WP-{101+i}-{n+1:03}' for n in range(3)]
                self.shipments[sid]=dict(id=sid,state='PLANNED',since=0.,arrival_at=i*8.,truck_id=tid,outbound_truck_id=oid,dock_id=None,pallet_id=pid,workpiece_ids=wp,good_ids=[],reject_ids=[],hold_ids=[],event_ids=[])
                self.pallets[pid]=dict(id=pid,shipment_id=sid,workpiece_ids=wp,state='ON_TRUCK',location=tid,position=list(self.network.nodes['GATE-01']),carrier=tid)
                for wid in wp:self.workpieces[wid]=dict(id=wid,shipment_id=sid,pallet_id=pid,state='PLANNED',component=None,verdict=None,inspection=None)
                for truck_id,flow in [(tid,'inbound'),(oid,'outbound')]:
                    self.trucks[truck_id]=dict(id=truck_id,kind='truck',flow=flow,shipment_id=sid,state='PLANNED',since=0.,node='GATE-01',position=list(self.network.nodes['GATE-01']),heading=math.pi/2,speed=6.,route=[],dock_id=None,wait_reason=None)
            source_ids=[c.id for c in self.model.components if c.kind=='Source']
            self.engine=Engine(self.model,self.inspect,external_sources=source_ids,event_sink=self._production_event)
            self.emit('site_reset',message='Synthetic demo; production Source is externally supplied',component='SITE-DEMO-01')
    def emit(self, kind, **data):
        self.sequence+=1
        e=dict(id=f'{self.run_token}:{self.sequence}',sequence=self.sequence,time=round(self.time,4),type=kind,origin='synthetic deterministic site',**data)
        self.events.append(e)
        s=self.shipments.get(e.get('shipment_id'))
        if s:s['event_ids']=(s['event_ids']+[e['id']])[-256:]
        if self.history:
            try:self.history.submit(envelope(e,self.history_context))
            except PersistenceFault as exc:
                self.status='paused';self.error=str(exc)
                if hasattr(self,'engine'):self.engine.status='paused'
                raise
        return e
    def transition(self, obj, state, **extra):
        valid=FORKLIFT_STATES if obj.get('kind')=='forklift' else TRUCK_STATES if obj.get('kind')=='truck' else SHIPMENT_STATES
        if state not in valid:raise ValueError('Unsupported lifecycle state: '+state)
        if obj['state']==state and not extra:return
        old=obj['state'];obj.update(state=state,since=self.time,**extra)
        self.emit('state_transition',component=obj['id'],shipment_id=obj.get('shipment_id',obj['id'] if obj['id'] in self.shipments else None),previous=old,state=state)
    def dock_state(self,d,state):
        if state not in DOCK_STATES:raise ValueError('Unknown dock state')
        if state!=d['state']:
            d.update(state=state,since=self.time)
            self.emit('dock_state',component=d['id'],state=state,shipment_id=d['shipment_id'],truck_id=d['truck_id'])
    def _production_event(self,e):
        e=dict(e);kind=e.pop('type');e.pop('time',None)
        wid=e.get('part');wp=self.workpieces.get(wid)
        if wp:
            if kind in ('part_move','external_material_admitted'):wp.update(state='IN_PROCESS',component=e.get('component'))
            if kind=='inspection_result':wp['inspection']=dict(e);wp['verdict']=e['verdict']
            if kind=='part_exit':
                wp.update(state='EXITED',component=e['component'],verdict=e['verdict'])
                s=self.shipments[wp['shipment_id']]
                target='good_ids' if e['verdict']=='OK' else 'reject_ids' if e['verdict']=='NG' else 'hold_ids'
                s[target].append(wid)
        self.emit('production_'+kind,**e)
    def control(self, operation, speed=None):
        with self.lock:
            if speed is not None:
                if speed not in (1,2,5,20):raise ValueError('Demo speed must be 1, 2, 5 or 20')
                self.speed=float(speed)
            if operation in ('run','resume'):
                if self.history:self.history.can_advance()
                if self.status=='completed':raise ValueError('Reset the completed site demo')
                self.status='running';self.engine.status='running'
            elif operation=='pause':self.status='paused';self.engine.status='paused'
            elif operation=='step':
                if self.history:self.history.can_advance()
                if self.status=='running':raise ValueError('Pause before stepping')
                self._step();self.status='paused';self.engine.status='paused'
            elif operation=='reset':self.reset()
            else:raise ValueError('Unknown site control')
            return self.snapshot()
    def tick(self, dt):
        with self.lock:
            if self.status!='running':return
            if not math.isfinite(dt) or dt<0:raise ValueError('Invalid elapsed time')
            self.accumulator+=min(dt,1.)*self.speed
            while self.accumulator>=.1-1e-9 and self.status=='running':
                self.accumulator-=.1
                try:
                    if self.history:self.history.can_advance()
                    self._step()
                except PersistenceFault as exc:
                    self.status='paused';self.engine.status='paused';self.error=str(exc);break
                except Exception as exc:
                    self.status='error';self.engine.status='error';self.error=str(exc);self.emit('runtime_error',message=self.error)
                    break
    def _step(self):
        if self.steps>=18000:
            self.status='completed';self.engine.status='completed';self.emit('horizon_reached',message='Bounded demo horizon reached; unfinished entities retain their states');return
        self.steps+=1;self.time=round(self.steps*.1,4)
        # Shared simulation time. No production is generated until material is admitted.
        self.engine.run_until(self.time)
        for s in self.shipments.values():
            if s['state']=='PLANNED' and self.time>=s['arrival_at']:
                self.transition(s,'ARRIVING');t=self.trucks[s['truck_id']];self.transition(t,'ARRIVING');self.network.assign(t,'ROAD-N01')
        for t in self.trucks.values():self._truck_tick(t)
        for f in self.forklifts.values():self._forklift_tick(f)
        for s in self.shipments.values():self._material_tick(s)
        for p in self.pallets.values():
            carrier=self.trucks.get(p['carrier']) or self.forklifts.get(p['carrier'])
            if carrier:p['position']=list(carrier['position'])
        if all(s['state'] in ('DEPARTED','ON_HOLD') for s in self.shipments.values()) and all(t['state'] in ('DEPARTED','PLANNED') for t in self.trucks.values()) and all(f['state']=='IDLE' for f in self.forklifts.values()):
            self.status='completed';self.engine.status='completed';self.emit('demo_completed',component='SITE-DEMO-01')
    def _truck_tick(self,t):
        s=self.shipments[t['shipment_id']];state=t['state']
        if state in ('PLANNED','DEPARTED'):return
        if state=='ARRIVING':
            if self.network.advance(t,.1):
                self.emit('gate_passed',component='GATE-01',truck_id=t['id'],shipment_id=s['id'])
                if t['flow']=='inbound':self.transition(s,'AT_GATE')
                self.transition(t,'WAITING',wait_reason='Awaiting compatible available dock')
        elif state=='WAITING':
            kind=t['flow']+'_dock'
            d=next((d for d in self.docks.values() if d['kind']==kind and d['state']=='AVAILABLE'),None)
            if d:
                d.update(truck_id=t['id'],shipment_id=s['id']);t['dock_id']=d['id'];s['dock_id']=d['id'];self.dock_state(d,'RESERVED')
                self.transition(t,'ASSIGNED_TO_DOCK',deadline=self.time+1,wait_reason=None)
                if t['flow']=='inbound':self.transition(s,'DOCK_ASSIGNED')
                self.emit('dock_assigned',component=d['id'],truck_id=t['id'],shipment_id=s['id'])
            else:t['wait_reason']='No available '+kind+'; inspect dock ownership / blocked state'
        elif state=='ASSIGNED_TO_DOCK' and self.time>=t['deadline']:
            self.network.assign(t,self.docks[t['dock_id']]['node']);self.transition(t,'DRIVING')
        elif state=='DRIVING':
            if self.network.advance(t,.1):
                self.transition(t,'DOCKED',deadline=self.time+2);self.dock_state(self.docks[t['dock_id']],'OCCUPIED')
        elif state=='DOCKED':
            p=self.pallets[s['pallet_id']]
            if t['flow']=='inbound' and p['state']=='ON_TRUCK' and self.time>=t['deadline']:
                self.transition(t,'UNLOADING',deadline=self.time+6);self.transition(s,'UNLOADING');self.dock_state(self.docks[t['dock_id']],'UNLOADING')
            elif t['flow']=='outbound':
                if p['location']==t['dock_id']:
                    self.transition(t,'LOADING',deadline=self.time+8);self.transition(s,'LOADING');self.dock_state(self.docks[t['dock_id']],'LOADING')
                elif p['location']=='STAGING-OUT-01':
                    self.enqueue(p,'STAGING-OUT-01-N',self.docks[t['dock_id']]['node'],'outbound_dock')
                    t['wait_reason']='Awaiting forklift transfer from STAGING-OUT-01'
                else:t['wait_reason']='Awaiting produced OK material at outbound staging'
        elif state=='UNLOADING' and self.time>=t['deadline']:
            p=self.pallets[s['pallet_id']];p.update(state='AT_DOCK',location=t['dock_id'],carrier=None,position=list(t['position']))
            self.emit('pallet_unloaded',component=t['dock_id'],pallet_id=p['id'],shipment_id=s['id'],truck_id=t['id'])
            self.enqueue(p,self.docks[t['dock_id']]['node'],'STAGING-IN-01-N','inbound_staging')
            self.transition(t,'DOCKED',wait_reason='Awaiting forklift pickup; dock retained',deadline=None)
        elif state=='LOADING' and self.time>=t['deadline']:
            p=self.pallets[s['pallet_id']];p.update(state='ON_OUTBOUND_TRUCK',location=t['id'],carrier=t['id'])
            self.depart(t)
        elif state=='DEPARTING' and self.network.advance(t,.1):
            self.transition(t,'DEPARTED')
            if t['flow']=='outbound':self.transition(s,'DEPARTED');self.emit('shipment_departed',component='EXIT-01',shipment_id=s['id'],truck_id=t['id'],workpiece_ids=list(s['good_ids']),reject_ids=list(s['reject_ids']),hold_ids=list(s['hold_ids']))
    def depart(self,t):
        if t['dock_id']:
            d=self.docks[t['dock_id']];d.update(truck_id=None,shipment_id=None);self.dock_state(d,'AVAILABLE')
        t['wait_reason']=None;self.network.assign(t,'EXIT-01');self.transition(t,'DEPARTING')
    def enqueue(self,p,pickup,destination,purpose):
        jid=f'{p["id"]}:{purpose}'
        if jid in self.job_ids:return
        self.job_ids.add(jid);self.jobs.append(dict(id=jid,pallet_id=p['id'],shipment_id=p['shipment_id'],pickup=pickup,destination=destination,purpose=purpose,created_at=self.time))
        self.emit('transport_job_queued',component=pickup,shipment_id=p['shipment_id'],pallet_id=p['id'],destination=destination,job_id=jid)
    def _forklift_tick(self,f):
        state=f['state']
        if state=='IDLE' and self.jobs:
            f['job']=self.jobs.popleft();f['shipment_id']=f['job']['shipment_id'];self.transition(f,'ASSIGNED',deadline=self.time+1)
        elif state=='ASSIGNED' and self.time>=f['deadline']:
            self.network.assign(f,f['job']['pickup']);self.transition(f,'TO_PICKUP')
        elif state=='TO_PICKUP' and self.network.advance(f,.1):self.transition(f,'LOADING',deadline=self.time+3)
        elif state=='LOADING' and self.time>=f['deadline']:
            p=self.pallets[f['job']['pallet_id']];p.update(carrier=f['id'],location=f['id'],state='IN_TRANSFER');f['pallet_id']=p['id']
            if f['job']['purpose']=='inbound_staging':self.depart(self.trucks[self.shipments[p['shipment_id']]['truck_id']])
            self.emit('pallet_picked',component=f['id'],pallet_id=p['id'],shipment_id=p['shipment_id'],node=f['node'])
            self.network.assign(f,f['job']['destination']);self.transition(f,'TO_DESTINATION')
        elif state=='TO_DESTINATION' and self.network.advance(f,.1):self.transition(f,'UNLOADING',deadline=self.time+2)
        elif state=='UNLOADING' and self.time>=f['deadline']:
            job=f['job'];p=self.pallets[job['pallet_id']];purpose=job['purpose']
            location={'inbound_staging':'STAGING-IN-01','production':'PRODUCTION-IN-01','finished_outbound':'STAGING-OUT-01','outbound_dock':'DOCK-B01'}[purpose]
            p.update(carrier=None,location=location,position=list(f['position']),state='AT_PRODUCTION' if purpose=='production' else 'STAGED')
            self.emit('pallet_delivered',component=location,pallet_id=p['id'],shipment_id=p['shipment_id'],purpose=purpose)
            if purpose=='inbound_staging':self.enqueue(p,'STAGING-IN-01-N','PRODUCTION-IN-01-N','production')
            f.update(pallet_id=None,job=None);self.network.assign(f,'FORK-HOME-N');self.transition(f,'RETURNING')
        elif state=='RETURNING' and self.network.advance(f,.1):f['shipment_id']=None;self.transition(f,'IDLE')
    def _material_tick(self,s):
        p=self.pallets[s['pallet_id']]
        if p['state']=='AT_PRODUCTION':
            source=self.definition.source_component
            if not source:
                s['unsupported']='No Source component binding';return
            for wid in s['workpiece_ids']:
                w=self.workpieces[wid]
                if w['state']=='PLANNED':
                    if not self.engine.admit_external(source,workpiece_id=wid,shipment_id=s['id'],pallet_id=p['id']):break
                    self.transition(s,'IN_PROCESS')
            if all(self.workpieces[w]['state']!='PLANNED' for w in s['workpiece_ids']):p.update(state='IN_PROCESS',location='CELL-01')
        if s['state']=='IN_PROCESS' and all(self.workpieces[w]['state']=='EXITED' for w in s['workpiece_ids']):
            if not s['good_ids']:
                p.update(state='HOLD',location='REJECT-HOLD-01',position=[39,0,-29]);self.transition(s,'ON_HOLD');self.emit('shipment_on_hold',shipment_id=s['id'],component='REJECT-HOLD-01',reason='No accepted output; outbound not fabricated');return
            p.update(state='FINISHED_GOODS',location='FG-01',position=list(self.network.nodes['FG-01-N']),workpiece_ids=list(s['good_ids']))
            self.transition(s,'READY_FOR_OUTBOUND')
            self.emit('finished_goods_staged',component='FG-01',shipment_id=s['id'],workpiece_ids=list(s['good_ids']))
            self.enqueue(p,'FG-01-N','STAGING-OUT-01-N','finished_outbound')
            t=self.trucks[s['outbound_truck_id']];self.transition(t,'ARRIVING');self.network.assign(t,'ROAD-N01')
    def block_dock(self,dock_id,blocked):
        with self.lock:
            d=self.docks[dock_id]
            if d['truck_id']:raise ValueError('Only an unoccupied dock may be blocked in this demo')
            d['blocked']=bool(blocked);self.dock_state(d,'BLOCKED' if blocked else 'AVAILABLE')
            return self.snapshot()
    def snapshot(self):
        with self.lock:
            docks=[]
            for d in self.docks.values():
                waiting=[t['id'] for t in self.trucks.values() if t['state']=='WAITING' and t['flow']+'_dock'==d['kind']]
                docks.append(dict(d,queue=waiting,elapsed_operation_time=round(self.time-d['since'],3)))
            return copy.deepcopy(dict(scope='site',synthetic=True,run_token=self.run_token,status=self.status,time=self.time,speed=self.speed,error=self.error,source_revision=self.revision,definition=self.definition.model_dump(),production=self.engine.snapshot(),trucks=list(self.trucks.values()),forklifts=list(self.forklifts.values()),docks=docks,pallets=list(self.pallets.values()),shipments=list(self.shipments.values()),workpieces=list(self.workpieces.values()),events=list(self.events)[-400:],metrics=dict(active_shipments=sum(s['state'] not in ('DEPARTED','ON_HOLD') for s in self.shipments.values()),departed_shipments=sum(s['state']=='DEPARTED' for s in self.shipments.values()),waiting_trucks=sum(t['state']=='WAITING' for t in self.trucks.values()),finished_goods=sum(len(s['good_ids']) for s in self.shipments.values() if self.pallets[s['pallet_id']]['location']=='FG-01'),reject_units=sum(len(s['reject_ids']) for s in self.shipments.values()),held_units=sum(len(s['hold_ids']) for s in self.shipments.values())),unsupported=['traffic/collision physics','GPS/PLC control','full WMS/MES','site throughput optimization / counterfactual delay attribution']))
    def query(self,message):
        """Evidence-only read tools. Never edits routes, model, or dispatch decisions."""
        with self.lock:
            snap=self.snapshot();lower=message.lower();evidence={};tool='get_site_state'
            selected=next((x for x in snap['trucks']+snap['forklifts']+snap['shipments']+snap['docks'] if x['id'].lower() in lower),None)
            if re.search(r'(truck|forklift|shipment|dock|pallet)-[a-z0-9-]+',lower) and not selected:
                answer='요청한 ID는 현재 bounded site demo에 없습니다. 존재하지 않는 차량·출하 상태는 추정하지 않습니다.';evidence={'unsupported':'unknown entity ID'}
            elif any(w in lower for w in ('improve','optimiz','개선','높여','caused','원인')) and not selected:
                answer='사이트 전체 처리량 최적화·반사실적 지연 원인 분석은 아직 지원하지 않습니다. 현재 상태·대기 사유·도크 점유·shipment 이력은 조회할 수 있습니다.';evidence={'unsupported':snap['unsupported']}
            elif selected:
                tool='get_site_entity';evidence={'component':selected['id'],'entity':selected,'events':[e for e in self.events if e.get('component')==selected['id'] or e.get('shipment_id')==selected['id'] or e.get('shipment_id')==selected.get('shipment_id')][-45:]}
                answer=f"{selected['id']}: {selected['state']}. "
                if selected.get('wait_reason'):answer+=selected['wait_reason']+'. '
                if selected.get('node'):answer+=f"현재 노드 {selected['node']}, 상태 경과 {self.time-selected['since']:.1f}s. "
                if 'workpiece_ids' in selected:answer+=f"제품 {len(selected['workpiece_ids'])}개, OK {len(selected['good_ids'])}, NG {len(selected['reject_ids'])}, HOLD {len(selected['hold_ids'])}. "
                answer+='합성 demo의 실제 runtime 기록 기준입니다.'
            elif any(w in lower for w in ('dock','도크','congest','혼잡')):
                tool='get_dock_status';evidence={'docks':snap['docks'],'waiting_trucks':[t for t in snap['trucks'] if t['state']=='WAITING']}
                answer='; '.join(f"{d['id']} {d['state']}, truck {d['truck_id'] or '없음'}, 호환 도크 공동 대기열 {len(d['queue'])}대" for d in snap['docks'])
            elif any(w in lower for w in ('bottleneck','병목')):
                rows=self.engine.bottlenecks();tool='get_bottleneck_analysis';evidence={'bottlenecks':rows}
                answer='생산 공정 proxy 순위: '+(', '.join(r['component'] for r in rows[:3]) if rows else '없음')+'. 사이트 전체 지연의 인과적 기여도는 미검증입니다.'
            elif any(w in lower for w in ('staging','finished','완제품')):
                tool='get_finished_goods';evidence={'metrics':snap['metrics'],'pallets':snap['pallets'],'pending_transport_jobs':list(self.jobs)}
                answer=f"현재 FG-01의 실제 OK 제품 {snap['metrics']['finished_goods']}개, 운반 대기 작업 {len(self.jobs)}개. 누적 생산량과 현재 staging 재고를 구분합니다."
            else:
                evidence={'status':snap['status'],'time':snap['time'],'metrics':snap['metrics'],'inspection_modes':{c.id:c.inspection_mode for c in self.model.components if c.kind=='Inspection'}}
                answer=f"합성 사이트 t={self.time:.1f}s, {self.status}. 활성 shipment {snap['metrics']['active_shipments']}, 출하 완료 {snap['metrics']['departed_shipments']}, 도크 대기 truck {snap['metrics']['waiting_trucks']}. 검사 모드: {evidence['inspection_modes']}."
            return dict(answer=answer,route='deterministic site tools',evidence=evidence,trace=[dict(tool=tool,arguments={'query':message},result=evidence)],proposal=None)
