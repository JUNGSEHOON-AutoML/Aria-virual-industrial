"""Autonomous patrol and evidence-based incident reporting for the virtual plant.

Patrol uses wall time so observation continues while production is paused.
Findings refer to DES telemetry, never unmeasured physical hardware conditions.
"""
import copy
import heapq
import json
import math
import time
from pathlib import Path
from datetime import datetime, timezone


def utc():
    return datetime.now(timezone.utc).isoformat()

class FloorPlanner:
    step = .5
    def __init__(self, model):
        self.components = {c['id']: c for c in model['components']}
        self.obstacles = []
        xs = [c['position'][0] for c in self.components.values()]
        zs = [c['position'][2] for c in self.components.values()]
        self.bounds = (min(xs)-3.5, max(xs)+3.5, min(zs)-4, max(zs)+4.5)
        for c in self.components.values():
            x, _, z = c['position']
            # Conservative equipment + robot safety-cell footprint, expanded for body clearance.
            width = max(1.8, c['length']/2) if c['kind']=='Conveyor' else 1.9
            za, zb = (-1.6,3.7) if c['kind']=='Machine' else (-1.6,1.9)
            corners=[]
            for dx in (-width,width):
                for dz in (za,zb):
                    a=c['rotation'];corners.append((x+dx*math.cos(a)+dz*math.sin(a),z-dx*math.sin(a)+dz*math.cos(a)))
            self.obstacles.append((min(p[0] for p in corners), max(p[0] for p in corners), min(p[1] for p in corners), max(p[1] for p in corners)))
        for e in model['connections']:
            a=self.components[e['source']]['position'];b=self.components[e['target']]['position']
            distance=math.hypot(b[0]-a[0],b[2]-a[2])
            if 2.6<distance<10:
                for i in range(int(distance/.4)+1):
                    t=i/max(1,int(distance/.4));x=a[0]+(b[0]-a[0])*t;z=a[2]+(b[2]-a[2])*t
                    self.obstacles.append((x-.55,x+.55,z-.55,z+.55))

    def free(self, point):
        x,z=point;l,r,b,f=self.bounds
        return l<=x<=r and b<=z<=f and not any(a<=x<=d and b0<=z<=e for a,d,b0,e in self.obstacles)

    def nearest(self, point):
        base=(round(point[0]/self.step),round(point[1]/self.step))
        for radius in range(25):
            options=[(base[0]+x,base[1]+z) for x in range(-radius,radius+1) for z in range(-radius,radius+1) if max(abs(x),abs(z))==radius]
            options.sort(key=lambda p:(p[0]*self.step-point[0])**2+(p[1]*self.step-point[1])**2)
            for p in options:
                if self.free((p[0]*self.step,p[1]*self.step)):return p
        return None

    def approach(self, cid):
        c=self.components[cid];x,_,z=c['position'];a=c['rotation']
        offset=4.2 if c['kind']=='Machine' else 2.5
        return self.nearest((x+offset*math.sin(a),z+offset*math.cos(a)))

    def route(self, position, target):
        start=self.nearest((position[0],position[2]))
        if start is None or target is None:return []
        queue=[(0,start)];cost={start:0};parent={}
        while queue and len(cost)<20000:
            _,current=heapq.heappop(queue)
            if current==target:
                path=[current]
                while current in parent:
                    current=parent[current];path.append(current)
                return [[x*self.step,0,z*self.step] for x,z in reversed(path)]
            for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
                p=(current[0]+dx,current[1]+dz)
                if not self.free((p[0]*self.step,p[1]*self.step)):continue
                new=cost[current]+1
                if new<cost.get(p,float('inf')):
                    cost[p]=new;parent[p]=current
                    heapq.heappush(queue,(new+abs(p[0]-target[0])+abs(p[1]-target[1]),p))
        return []

class PatrolSupervisor:
    def __init__(self, directory):
        self.directory=Path(directory)
        self.maintenance=[];self.reports=[];self.active={};self.robots=[];self.enabled=True
        self.planner=None;self.revision=None;self.last_sim=0.;self.run=0;self.elapsed=0.
        self.persist_error=None;self.sequence=0;self.seen=set()
        p=self.directory/'patrol_reports.json'
        if p.is_file():
            try:
                self.reports=json.loads(p.read_text())[-200:]
                self.sequence=max((r['sequence'] for r in self.reports),default=0)
                for r in self.reports:
                    if r['status']=='open':
                        r['status']='interrupted';r['outcome']='Server restarted; recovery not verified'
            except (ValueError,KeyError,TypeError) as exc:self.persist_error=str(exc)

    def save(self):
        try:
            self.directory.mkdir(parents=True,exist_ok=True)
            p=self.directory/'patrol_reports.json.tmp';p.write_text(json.dumps(self.reports,ensure_ascii=False,indent=2));p.replace(self.directory/'patrol_reports.json')
            self.persist_error=None
        except OSError as exc:self.persist_error=str(exc)

    def configure(self, snap):
        for r in self.active.values():
            r.update(status='interrupted',outcome='Factory model/run changed; recovery not verified',closed_at=utc())
        self.active={};self.seen=set();self.run+=1;self.revision=snap['revision'];self.planner=FloorPlanner(snap['model'])
        targets=[c['id'] for c in snap['model']['components'] if c['kind'] in ('Machine','Inspection','Conveyor','Buffer')]
        if not targets:targets=list(self.planner.components)
        self.robots=[]
        for i in range(2):
            start=self.planner.nearest((self.planner.bounds[i],self.planner.bounds[3]-.5))
            self.robots.append(dict(id=f'ARIA-{i+1:02d}',name='FIELD INSPECTOR' if i==0 else 'RELIABILITY SCOUT',
                position=[start[0]*.5,0,start[1]*.5] if start else [0,0,0], heading=0., phase=0.,
                state='PATROLLING' if start else 'ROUTE_BLOCKED',target=None,path=[],route=targets[i::2] or targets,
                cursor=0,dwell=0.,visits=0,last_observation=None))
        self.save()

    def observe(self, snap):
        changed=False
        for cid,r in snap['metrics']['resources'].items():
            kind=None;severity='warning';evidence={};recommendation=''
            if r['state']=='DOWN':
                kind='equipment_down';severity='critical';evidence={'state':'DOWN','downtime_s':r['downtime']}
                recommendation='Check drive, power and maintenance events. Wait for verified repair; no robot repair was executed.'
            elif r['state']=='BLOCKED' and r['blocking_time']>=5 and r['occupancy']>=r['capacity']:
                kind='flow_blocked';evidence={'state':'BLOCKED','occupancy':r['occupancy'],'capacity':r['capacity'],'blocking_time_s':r['blocking_time']}
                recommendation='Inspect downstream capacity and routing; compare a scenario before changing settings.'
            elif r['kind']=='Machine' and r['state']=='STARVED' and snap['time']>=30 and r['starvation_time']/max(snap['time'],1)>.7:
                kind='material_starvation';evidence={'state':'STARVED','starvation_s':r['starvation_time'],'simulation_s':snap['time']}
                recommendation='Check upstream material supply and connections.'
            key=f'{self.run}:{cid}'
            old=self.active.get(key)
            if old and (kind is None or old['kind']!=kind):
                old.update(status='recovered',closed_at=utc(),closed_sim_time=snap['time'],outcome='Telemetry condition cleared; physical repair is not inferred.')
                del self.active[key];changed=True;old=None
            if kind and old is None:
                self.sequence+=1
                entry=dict(id=f'INC-{self.sequence:06d}',sequence=self.sequence,run=self.run,revision=snap['revision'],
                    component=cid,kind=kind,severity=severity,status='open',detected_at=utc(),detected_sim_time=snap['time'],
                    evidence=evidence,source='DES telemetry',detected_by='ARIA REPORTER',verified_by=None,
                    recommendation=recommendation,outcome='Robot inspection pending',visits=[])
                self.reports.append(entry);self.reports=self.reports[-200:];self.active[key]=entry;changed=True
        # Actual detector error evidence remains visible even after the part exits.
        for event in snap.get('events',[]):
            if event.get('type')!='inspection_result':continue
            event_key=(event.get('part'),event['time'],event['component'])
            if event_key in self.seen:continue
            self.seen.add(event_key)
            if len(self.seen)>4096:self.seen={event_key}
            key=f"{self.run}:{event['component']}:inspection"
            if event.get('verdict')!='SKIPPED':
                if key in self.active:
                    previous=self.active.pop(key)
                    previous.update(status='recovered',closed_at=utc(),closed_sim_time=event['time'],outcome='A subsequent inspection produced a valid verdict')
                    changed=True
                continue
            if key in self.active:continue
            self.sequence+=1
            r=dict(id=f'INC-{self.sequence:06d}',sequence=self.sequence,run=self.run,revision=snap['revision'],component=event['component'],
                kind='inspection_skipped',severity='warning',status='open',detected_at=utc(),detected_sim_time=event['time'],
                evidence={k:event[k] for k in ('part','verdict','reason') if k in event},source='DES inspection result',
                detected_by='ARIA REPORTER',verified_by=None,recommendation='Check image assets and detector model availability.',
                outcome='Needs operator review',visits=[])
            self.reports.append(r);self.reports=self.reports[-200:];self.active[key]=r;changed=True
        if changed:self.save()

    def tick(self, snap, dt):
        if self.planner is None or self.revision!=snap['revision'] or snap['time']<self.last_sim or getattr(self,'run_token',None)!=snap.get('run_token'):
            self.configure(snap)
            self.run_token=snap.get("run_token")
        self.last_sim=snap['time'];self.observe(snap)
        dt=max(0.,min(float(dt),.5));self.elapsed+=dt
        if self.enabled:
            reserved=set()
            for robot in self.robots:
                if robot.get('maintenance_hold'):
                    reserved.add(robot['target'])
                    continue
                if robot['dwell']>0:
                    robot['dwell']=max(0.,robot['dwell']-dt)
                    if robot['state']!='ROUTE_BLOCKED':robot['state']='INSPECTING'
                    if robot['dwell']==0:robot['target']=None
                    if robot['target']:reserved.add(robot['target'])
                    continue
                if robot['state']=='PATROLLING' and any(r['severity']=='critical' and r['verified_by'] is None and r['component']!=robot['target'] and r['component'] not in reserved for r in self.active.values()):
                    robot['target']=None;robot['path']=[]
                if not robot['target']:
                    urgent=next((r['component'] for r in sorted(self.active.values(),key=lambda r:r['severity']!='critical') if r['status']=='open' and r['verified_by'] is None and r['component'] not in reserved),None)
                    target=urgent or robot['route'][robot['cursor']%len(robot['route'])]
                    robot['cursor']+=1;robot['target']=target
                    robot['path']=self.planner.route(robot['position'],self.planner.approach(target))
                    robot['state']='RESPONDING' if urgent else 'PATROLLING'
                    if not robot['path']:
                        robot['state']='ROUTE_BLOCKED';robot['last_observation']='No safe route through the current equipment footprints';robot['target']=None
                        robot['dwell']=2.;continue
                reserved.add(robot['target'])
                distance=dt*1.6
                while distance>0 and robot['path']:
                    point=robot['path'][0];dx=point[0]-robot['position'][0];dz=point[2]-robot['position'][2];d=math.hypot(dx,dz)
                    if d<1e-8:robot['path'].pop(0);continue
                    step=min(distance,d);robot['position'][0]+=dx/d*step;robot['position'][2]+=dz/d*step
                    robot['heading']=math.atan2(dx,dz);robot['phase']+=step*5;distance-=step
                    if step>=d-1e-8:robot['path'].pop(0)
                if not robot['path']:
                    cid=robot['target'];resource=snap['metrics']['resources'][cid]
                    robot.update(state='INSPECTING',dwell=2.,visits=robot['visits']+1,last_observation=f"{cid}: {resource['state']}")
                    for incident in self.active.values():
                        if incident['component']==cid and incident['status']=='open':
                            incident['verified_by']=robot['id'];incident['outcome']='On-site virtual inspection confirmed telemetry; no repair executed'
                            incident['visits'].append(dict(robot=robot['id'],at=utc(),sim_time=snap['time'],state=resource['state']))
                            incident['visits']=incident['visits'][-10:];self.save()
        return self.snapshot()

    def snapshot(self):
        return copy.deepcopy(dict(maintenance=self.maintenance, enabled=self.enabled,elapsed=self.elapsed,robots=self.robots,
            open_incidents=sum(r['status']=='open' for r in self.reports),reports=list(reversed(self.reports)),
            storage_error=self.persist_error,source='virtual factory telemetry; patrol uses wall time'))

    def markdown(self):
        lines=['# ARIA autonomous factory incident report',f'Generated: {utc()}',
               'Evidence source: virtual DES telemetry. Repairs, when recorded, are virtual harness actions only; no physical hardware repair is claimed.','']
        for r in reversed(self.reports):
            lines += [f"## {r['id']} — {r['component']} / {r['kind']}",
                f"Status: {r['status']} | Severity: {r['severity']} | Simulation time: {r['detected_sim_time']:.2f}s",
                f"Detected: {r['detected_at']} | Verified by: {r['verified_by'] or 'pending'}",
                'Evidence: '+json.dumps(r['evidence'],ensure_ascii=False),
                'Recommendation: '+r['recommendation'],'Outcome: '+r['outcome'], 'Maintenance trace: '+json.dumps(r.get('maintenance',{}),ensure_ascii=False),'']
        if not self.reports:lines+=['No incidents observed.']
        return '\n'.join(lines)
