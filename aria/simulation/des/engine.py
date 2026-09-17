"""Priority queue DES. Single owner; simulation time never depends on rendering.

Finite resource slots retain finished parts until downstream admits them
(blocking-after-service). Failures interrupt and resume unfinished work.
"""
import heapq
import math
import random
import time
import uuid
from collections import deque
from .model import FactoryModel, STATES

class Engine:
    def __init__(self, model, inspect=None):
        self.model = FactoryModel.model_validate(model.model_dump() if isinstance(model, FactoryModel) else model)
        self.inspect = inspect
        self.reset()

    def reset(self):
        self.run_token = uuid.uuid4().hex
        self.inspections = deque(maxlen=30)
        self.now = 0.
        self.status = 'paused'
        self.error = None
        self.heap = []
        self.sequence = 0
        self.serial = 0
        self.events_processed = 0
        self.history = deque(maxlen=160)
        self.moves = deque(maxlen=300)
        self.counts = dict(OK=0, NG=0, SKIPPED=0, UNINSPECTED=0)
        self.lead_sum = 0.
        self.last_exit = None
        self.cycle_sum = 0.
        self.cycle_n = 0
        self.nodes = {}
        for index, c in enumerate(self.model.components):
            self.nodes[c.id] = dict(c=c, jobs=[], down=False, epoch=0, total=0, wait=0.,
                                    wait_n=0, area=0., busy=0., blocked=0.,
                                    states={s: 0. for s in STATES}, state='IDLE',
                                    rng=random.Random(self.model.seed + index * 104729), pending_source=False)
        for c in self.model.components:
            if c.kind == 'Source':
                self.schedule(0., 'arrival', c.id)
            if c.kind in ('Machine', 'Inspection'):
                self._next_failure(self.nodes[c.id])
        self._settle()

    def schedule(self, at, kind, node, part=None, epoch=None):
        self.sequence += 1
        heapq.heappush(self.heap, (at, self.sequence, kind, node, part, epoch))

    def emit(self, kind, **payload):
        self.history.append(dict(type=kind, time=round(self.now, 6), **payload))

    def _next_failure(self, node):
        c = node['c']
        mtbf = c.mtbf or (c.mttr * c.availability / (1 - c.availability) if c.availability < 1 else 0)
        if mtbf:
            self.schedule(self.now + max(.01, node['rng'].expovariate(1 / mtbf)), 'failure', c.id)

    def _state(self, node):
        c, jobs = node['c'], node['jobs']
        if c.maintenance:
            return 'MAINTENANCE'
        if node['down']:
            return 'DOWN'
        if any(j['phase'] == 'process' for j in jobs):
            return 'PROCESSING'
        if any(j['phase'] == 'setup' for j in jobs):
            return 'SETUP'
        if jobs:
            return 'BLOCKED'
        return 'STARVED' if c.kind in ('Machine', 'Inspection', 'Conveyor') else 'IDLE'

    def _advance(self, at):
        dt = at - self.now
        for n in self.nodes.values():
            n['states'][n['state']] += dt
            n['area'] += len(n['jobs']) * dt
            if not n['down'] and not n['c'].maintenance:
                n['busy'] += sum(j['phase'] == 'process' for j in n['jobs']) * dt
                n['blocked'] += sum(j['phase'] == 'ready' for j in n['jobs']) * dt
        self.now = at

    def _admit(self, n, part, previous=None):
        c = n['c']
        if c.kind == 'Sink':
            v = part.get('verdict') or 'UNINSPECTED'
            self.counts[v] += 1
            self.lead_sum += self.now - part['born']
            if self.last_exit is not None:
                self.cycle_sum += self.now - self.last_exit
                self.cycle_n += 1
            self.last_exit = self.now
            n['total'] += 1
            self.emit('part_exit', component=c.id, part=part['id'], verdict=v)
            self.moves.append(dict(part=part['id'], source=previous, target=c.id, time=self.now, verdict=v))
            return
        duration = c.length / c.speed if c.kind == 'Conveyor' else c.processing_time
        if c.robot_model:
            from .robot import program
            duration = program(c.processing_time)[1]
        service = c.kind in ('Machine', 'Inspection', 'Conveyor')
        phase = ('setup' if c.setup_time and c.kind in ('Machine', 'Inspection') else 'process') if service else 'ready'
        delay = c.setup_time if phase == 'setup' else duration
        j = dict(part=part, entered=self.now, phase=phase, due=self.now + delay, duration=duration, motion_start=self.now + (delay if phase=='setup' else 0), robot_checks=[], gripper_closed=False)
        n['jobs'].append(j)
        if service:
            self._schedule_job(n, j)
        self.moves.append(dict(part=part['id'], source=previous, target=c.id, time=self.now, verdict=part.get('verdict')))
        self.emit('part_move', component=c.id, source=previous, part=part['id'])

    def _target(self, node, job):
        edges = [e for e in self.model.connections if e.source == node['c'].id]
        v = job['part'].get('verdict')
        exact = next((e for e in edges if e.condition == v), None)
        edge = exact or next((e for e in edges if e.condition == 'always'), None)
        return self.nodes[edge.target] if edge else None

    def _settle(self):
        changed = True
        while changed:
            changed = False
            for n in self.nodes.values():
                c = n['c']
                if n['down'] or c.maintenance:
                    continue
                jobs = list(n['jobs'])
                if c.queue_discipline == 'LIFO' and c.kind == 'Buffer':
                    jobs.reverse()
                for j in jobs:
                    if j['phase'] != 'ready':
                        continue
                    dest = self._target(n, j)
                    if dest is None or dest['down'] or dest['c'].maintenance:
                        break
                    if dest['c'].kind != 'Sink' and len(dest['jobs']) >= dest['c'].capacity:
                        break
                    n['jobs'].remove(j)
                    n['total'] += 1
                    if c.kind in ('Source', 'Buffer', 'Diverter'):
                        n['wait'] += self.now - j['entered']
                        n['wait_n'] += 1
                    self._admit(dest, j['part'], c.id)
                    changed = True
                if c.kind == 'Source' and n['pending_source'] and len(n['jobs']) + c.batch_size <= c.capacity:
                    n['pending_source'] = False
                    self.schedule(self.now, 'arrival', c.id)
            # All transfers traverse a validated DAG, so no zero-time circulation.
        for n in self.nodes.values():
            state = self._state(n)
            if state != n['state']:
                self.emit('component_state', component=n['c'].id, state=state)
                n['state'] = state

    def _event(self):
        at, _, kind, cid, pid, epoch = heapq.heappop(self.heap)
        self._advance(at)
        n = self.nodes[cid]
        c = n['c']
        self.events_processed += 1
        self.emit('simulation_event', event=kind, component=cid, part=pid)
        if kind == 'arrival':
            if c.maintenance or len(n['jobs']) + c.batch_size > c.capacity:
                n['pending_source'] = True
            else:
                for _ in range(c.batch_size):
                    self.serial += 1
                    self._admit(n, dict(id=f'P{self.serial:07d}', serial=self.serial, born=self.now,
                                        product_type=c.product_type, verdict=None))
                self.schedule(self.now + c.interarrival, 'arrival', cid)
        elif kind == 'failure' and not c.maintenance and not n['down']:
            n['down'] = True
            n['epoch'] += 1
            for j in n['jobs']:
                if j['phase'] != 'ready':
                    j['remaining'] = max(0., j['due'] - self.now)
            self.schedule(self.now + (float(epoch) if epoch is not None else c.mttr), 'repair', cid)
        elif kind == 'repair' and n['down'] and not n.get('fault'):
            self._resume_node(n)
        elif kind.startswith('robot:') and epoch == n['epoch'] and not n['down']:
            j=next((j for j in n['jobs'] if j['part']['id']==pid),None)
            if j and j['phase']=='process':
                from .robot import program, sample
                rows,_=program(c.processing_time)
                stage=kind.split(':',1)[1];index=next(i for i,r in enumerate(rows) if r['stage']==stage)
                if stage not in j['robot_checks']:
                    if len(j['robot_checks'])!=index:
                        raise ValueError('Robot command acknowledgement order mismatch')
                    row=rows[index]
                    position=sample(c.processing_time,row['start']+row['duration'])['joints']
                    error=max(abs(a-b) for a,b in zip(position,row['target']))
                    if error>1e-6:raise ValueError('Robot failed to reach joint target')
                    if stage=='GRIP':j['gripper_closed']=True
                    if stage=='INSPECT' and not j['gripper_closed']:raise ValueError('Product not gripped at inspection')
                    if stage=='RELEASE':j['gripper_closed']=False
                    j['robot_checks'].append(stage)
                    self.emit('robot_ack',component=cid,part=pid,stage=stage,joint_error_rad=error,gripper_closed=j['gripper_closed'],source='virtual controller')
        elif kind == 'complete' and epoch == n['epoch'] and not n['down']:
            j = next((j for j in n['jobs'] if j['part']['id'] == pid), None)
            if j:
                if j['phase'] == 'setup':
                    j['phase'] = 'process'
                    j['motion_start'] = self.now
                    j['due'] = self.now + j['duration']
                    self._schedule_job(n, j)
                else:
                    if c.robot_model and (len(j['robot_checks'])!=7 or j['gripper_closed']):
                        raise ValueError('Robot cycle cannot complete without all command acknowledgements')
                    j['phase'] = 'ready'
                    if c.kind == 'Inspection':
                        if c.inspection_mode == 'mock':
                            result = dict(verdict='NG' if n['rng'].random() < c.defect_rate else 'OK', mode='mock')
                        else:
                            try:
                                result = self.inspect(c, j['part']) if self.inspect else dict(verdict='SKIPPED', reason='Detector adapter unavailable')
                                if result.get('verdict') not in ('OK', 'NG', 'SKIPPED'):
                                    raise ValueError('Invalid detector verdict')
                                if 'score' in result and not math.isfinite(result['score']):
                                    raise ValueError('Non-finite detector score')
                            except Exception as exc:
                                result = dict(verdict='SKIPPED', reason=str(exc)[:300])
                        j['part'].update(verdict=result['verdict'], inspection=result)
                        self.inspections.append(dict(component=cid,part=pid,time=self.now,**result))
                        self.emit('inspection_result', component=cid, part=pid, **result)
        self._settle()

    def _schedule_job(self, n, j):
        if n['c'].robot_model and j['phase']=='process':
            from .robot import program
            rows,_=program(n['c'].processing_time)
            for row in rows:
                if row['stage'] not in j['robot_checks']:
                    at=j['motion_start']+row['start']+row['duration']
                    self.schedule(max(self.now,min(j['due'],at)),'robot:'+row['stage'],n['c'].id,j['part']['id'],n['epoch'])
        self.schedule(j['due'],'complete',n['c'].id,j['part']['id'],n['epoch'])

    def _resume_node(self, n, schedule_failure=True):
        n['down'] = False
        for j in n['jobs']:
            if j['phase'] != 'ready':
                remaining=j.pop('remaining', 0.)
                if j['phase']=='process':
                    j['motion_start']=self.now-(j['duration']-remaining)
                j['due'] = self.now + remaining
                self._schedule_job(n, j)
        if schedule_failure:
            self._next_failure(n)

    def step(self):
        self.status = 'paused'
        if self.heap:
            self._event()
        return self.snapshot()

    def run_until(self, until, max_events=200000, deadline=None):
        if not math.isfinite(until) or until < self.now:
            raise ValueError('Horizon must be finite and >= simulation time')
        count = 0
        while self.heap and self.heap[0][0] <= until:
            if deadline is not None and count % 64 == 0 and time.monotonic() > deadline:
                raise ValueError('Simulation wall-time budget exceeded')
            if count >= max_events:
                raise ValueError('Simulation event budget exceeded; reduce horizon or arrival rate')
            self._event()
            count += 1
        self._advance(until)
        return self.metrics()

    def robot_state(self, n, j=None):
        if not n['c'].robot_model:
            return None
        from .robot import sample, self_test
        if n.get('fault',{}).get('test_q') is not None:
            return self_test(n['fault']['test_q'],n['fault']['test_elapsed'])
        j=j or next(iter(n['jobs']),None)
        elapsed=0.
        if j and j['phase']!='setup':
            elapsed=j['duration']-j['remaining'] if n['down'] and 'remaining' in j else self.now-j['motion_start']
        result=sample(n['c'].processing_time,elapsed,stopped=n['down'] or self.status!='running' or not j or j['phase']!='process')
        result['completed_steps']=list(j['robot_checks']) if j else []
        result['attached']=bool(j and j['gripper_closed'])
        result['gripper']='CLOSED' if result['attached'] else 'OPEN'
        return result

    def metrics(self):
        total = sum(self.counts.values())
        resources = {}
        for cid, n in self.nodes.items():
            c = n['c']
            denom = max(self.now * c.capacity, 1e-12)
            utilization = n['busy'] / denom
            downtime = n['states']['DOWN'] + n['states']['MAINTENANCE']
            availability = max(0., 1 - downtime / self.now) if self.now else 0.
            active = max((self.now - downtime) * c.capacity, 1e-12)
            performance = min(1., n['total'] * c.processing_time / active) if c.kind in ('Machine', 'Inspection') else None
            quality = self.counts['OK'] / total if total else 0.
            resources[cid] = dict(robot=self.robot_state(n), fault=n.get('fault'), kind=c.kind, state=n['state'], occupancy=len(n['jobs']), capacity=c.capacity,
                completed=n['total'], utilization=utilization, avg_queue=n['area'] / self.now if self.now else 0.,
                waiting_time=n['wait'] / n['wait_n'] if n['wait_n'] else 0.,
                blocking_time=n['states']['BLOCKED'], blocked_slot_time=n['blocked'],
                starvation_time=n['states']['STARVED'], downtime=downtime,
                state_times=dict(n['states']), availability=availability, performance=performance,
                oee=availability * performance * quality if performance is not None else None)
        machines = [v for v in resources.values() if v['kind'] == 'Machine']
        return dict(time=self.now, generated=self.serial, completed=total, counts=dict(self.counts),
            throughput_per_hour=total * 3600 / self.now if self.now else 0.,
            good_throughput_per_hour=self.counts['OK'] * 3600 / self.now if self.now else 0.,
            wip=sum(len(n['jobs']) for n in self.nodes.values()),
            lead_time=self.lead_sum / total if total else 0.,
            cycle_time=self.cycle_sum / self.cycle_n if self.cycle_n else 0.,
            defect_rate=self.counts['NG'] / (self.counts['OK'] + self.counts['NG']) if self.counts['OK'] + self.counts['NG'] else 0.,
            oee=min((v['oee'] for v in machines), default=0.), resources=resources,
            events_processed=self.events_processed)

    def bottlenecks(self):
        metrics = self.metrics()
        ranked = []
        for c in self.model.components:
            if c.kind not in ('Machine', 'Inspection', 'Conveyor'):
                continue
            r = metrics['resources'][c.id]
            upstream = [metrics['resources'][e.source] for e in self.model.connections if e.target == c.id]
            queue = sum(x['avg_queue'] for x in upstream)
            wait = sum(x['waiting_time'] for x in upstream)
            score = r['utilization'] + min(queue / 10, 1.) + min(wait / 60, 1.) - r['blocking_time'] / max(self.now, 1) - r['starvation_time'] / max(self.now, 1)
            ranked.append(dict(component=c.id, score=score, utilization=r['utilization'], upstream_queue=queue,
                               upstream_wait=wait, blocking_time=r['blocking_time'], starvation_time=r['starvation_time'],
                               throughput_sensitivity=None))
        return sorted(ranked, key=lambda x: (-x['score'], x['component']))

    def snapshot(self):
        parts = []
        for cid, n in self.nodes.items():
            for j in n['jobs']:
                parts.append(dict(**j['part'], robot=self.robot_state(n,j), component=cid, phase=j['phase'], entered=j['entered'], due=j['due']))
        return dict(run_token=self.run_token, inspections=list(self.inspections), model=self.model.model_dump(), status=self.status, time=self.now, error=self.error,
                    metrics=self.metrics(), bottlenecks=self.bottlenecks(), parts=parts,
                    moves=list(self.moves), events=list(self.history),
                    next_events=[dict(time=e[0], event=e[2], component=e[3]) for e in sorted(self.heap)[:12]])
