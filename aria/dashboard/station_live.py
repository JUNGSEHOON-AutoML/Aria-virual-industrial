"""Read-only live station view over existing DES snapshots/events."""
import copy
import numpy as np
from . import transfer, stations
from aria.simulation.des.robot import program as inspection_program, JOINTS


class LiveStationView:
    def __init__(self):
        self.geometry,self.values,self.parameters=stations.configuration()
        self.seen=set();self.ok=[];self.boxes=[];self.triggers={};self.arrivals={};self.decisions={}
        self.events=[];self.tasks=[]
        self.rows,self.duration=transfer.program(self.values['transfer_seconds'])
        from .logistics import configuration
        _,values=configuration();self.capacity=int(values['parts_per_box']);self.pack_seconds=values['packing_seconds_per_box']
        self.resolution=None

    def observe(self,snap,events):
        for e in snap['events']:
            key=(e.get('type'),e.get('part'),e.get('time'))
            if e.get('type')!='part_exit' or key in self.seen:continue
            self.seen.add(key)
            if e.get('verdict')=='OK':self.ok.append((e['part'],e['time']))
        # Same configured box capacity as the existing logistics layer.
        capacity=self.capacity
        while len(self.ok)>=(len(self.boxes)+1)*capacity:
            i=len(self.boxes);group=self.ok[i*capacity:(i+1)*capacity]
            ready=group[-1][1]+self.pack_seconds;object_id=f'{snap["run_token"]}:LIVE-BOX:{i:05d}'
            self.boxes.append(dict(id=object_id,ready=ready,parts=[p for p,_ in group]))
            self.events.append(dict(id='live-box-ready:'+object_id,time=ready,object_id=object_id,kind='box',actor='production'))
            self.tasks=transfer.schedule(self.events,self.values['transfer_seconds'])
        for e in snap['moves']:
            if e.get('target')=='DIVERTER':self.arrivals[e['part']]=e['time']
        for e in events:
            if e['type']=='live_inspection_ready':self.decisions[e['part']]=dict(id=e['part'],time=e['sim_time'],verdict=e['verdict'],score=e.get('score'),threshold=e.get('threshold'),evidence=e.get('evidence'),latency_ms=e.get('inspection_wall_ms'))
        component=next(c for c in snap['model']['components'] if c['id']=='AI-INSPECTION')
        if self.resolution is None:
            from PIL import Image
            from .store import ROOT
            with Image.open(ROOT/component['image_paths'][0]) as im:self.resolution=list(im.size)
        rows,_=inspection_program(component['processing_time']);start=next(r['start'] for r in rows if r['stage']=='INSPECT')
        for p in snap['parts']:
            # The existing INSPECT phase entering is the camera trigger; no
            # invented capture at pick/move phases and no DES program changes.
            if p['component']=='AI-INSPECTION' and p.get('robot',{}).get('stage')=='INSPECT':
                self.triggers.setdefault(p['id'],snap['time']-(p['robot']['elapsed']-start))

    def snapshot(self,snap):
        state=snap['metrics']['resources']['AI-INSPECTION']['state']
        conveyor=snap['metrics']['resources']['CONVEYOR-02']
        speed=next(c['speed'] for c in snap['model']['components'] if c['id']=='CONVEYOR-02')
        # Exact accumulated DES PROCESSING duration, never integrated client dt.
        distance=conveyor['state_times']['PROCESSING']*speed
        parts=[]
        for pid,trigger in self.triggers.items():
            decision=self.decisions.get(pid,{})
            verdict=decision.get('verdict')
            parts.append(dict(id=pid,trigger=trigger,decision=decision.get('time'),arrival=self.arrivals.get(pid),
                              verdict=verdict,route=verdict if verdict in ('OK','NG') else 'HOLD'))
        active=[]
        for task in self.tasks:
            if task['start']<=snap['time']<task['end']:
                active.append({**task,'state':transfer.sample(snap['time']-task['start'],object_id=task['object_id'],transfer_seconds=self.values['transfer_seconds'],stopped=snap['status']!='running')})
        recent=sorted(self.decisions.values(),key=lambda d:d['time'])[-10:]
        latencies=[d['latency_ms'] for d in self.decisions.values() if d.get('latency_ms') is not None]
        return dict(latency_ms={q:float(np.percentile(latencies,n)) if latencies else None for q,n in [('p50',50),('p95',95)]},run_id=snap['run_token'],geometry=self.geometry,parameters=self.parameters,camera_resolution=self.resolution,
                    parts=sorted(parts,key=lambda p:(p['trigger'],p['id'])),
                    equipment=[dict(start=snap['time'],end=snap['time'],speed=speed if conveyor['state']=='PROCESSING' else 0.,distance=distance,state=state,lamp='FAULT' if state=='DOWN' else 'RUN' if state=='PROCESSING' else 'STOP')],
                    transfer_tasks=copy.deepcopy(self.tasks),source_events=copy.deepcopy(self.events),
                    transfer_program=self.rows,transfer_duration=self.duration,robot_joints=JOINTS,
                    active_transfers=active,recent=recent,
                    source='unchanged DES state_times, INSPECT entry, DIVERTER move, OK part_exit',
                    role='fixed camera inspection; robot only downstream transfer')
