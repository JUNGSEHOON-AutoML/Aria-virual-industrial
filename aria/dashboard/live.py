"""Isolated CPU Live Ops adapter over the existing DES, detector, robot and patrol.

No writes to experiment data or the saved factory. Research/replay APIs stay read-only.
"""
import asyncio
import copy
import json
import math
import os
import threading
import time
import uuid
from pathlib import Path
import numpy as np
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Literal
from aria.simulation.des.service import FactoryService
from aria.simulation.des.engine import Engine
from aria.simulation.des.model import demo_factory, FactoryModel
from aria.simulation.des.inspection import InspectionAdapter
from aria.simulation.des.patrol import PatrolSupervisor
from aria.simulation.des.maintenance import MaintenanceHarness
from aria.simulation.des.robot import fk, tool_point, POSES, JOINTS, model_info
from .store import ROOT

router=APIRouter(prefix='/api/live',tags=['isolated CPU live'])
CONFIG=ROOT/'configs/live_ops.json'

class LiveOps:
    def __init__(self, directory=None, inspect=None, seed=0):
        self.config=json.loads(CONFIG.read_text())
        self.session=uuid.uuid4().hex
        self.directory=Path(directory or ROOT/'outputs/cnotta-live'/self.session)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.stop=threading.Event();self.thread=None
        self.inspection=inspect or InspectionAdapter(ROOT)
        if inspect is None:
            # Bounded input set <=64 gives <=64 unique evidence folders per session.
            # This never invokes retention on the old factory/research evidence.
            self.inspection.evidence.directory=self.directory/'evidence'
        self.decisions={};self.inspection_busy=False;self.busy_snapshot=None;self.elapsed_inference=0.;self.stream_sequence=0
        self.service=FactoryService(self.directory/'service',self.inspect_once)
        self.service.engine=Engine(self.model(seed),self.inspect_once)
        self.service.speed='1'
        self.patrol=PatrolSupervisor(self.directory/'patrol');self.maintenance=MaintenanceHarness()
        self.events=[];self.releases=set();self.info=model_info()
        q=list(POSES['place']);q[0]*=self.config['motion']['ng_base_scale']
        self.info['fixtures']['ng']=tool_point(fk(q)[1])
        q=list(POSES['place']);q[0]*=self.config['motion']['hold_base_scale']
        self.info['fixtures']['hold']=tool_point(fk(q)[1])
        self._observe(0)

    def model(self,seed):
        model=demo_factory().model_dump();model.update(id='cnotta-live-cpu',name='BOTTLE CCIFPS Live (simulation)',seed=seed)
        model['simulation'].update(duration=3600,speed='1')
        positions={'SOURCE':[-11,0,0],'CONVEYOR-01':[-9,0,0],'BUFFER-01':[-7,0,0],'MACHINE-01':[-5.5,0,0],'CONVEYOR-02':[-4.6,0,0],'AI-INSPECTION':[-3.6,0,0],'DIVERTER':[-.7,0,0],'GOOD-SINK':[6.3,0,-1.4],'REJECT-SINK':[6.3,0,1.4],'HOLD-SINK':[6.3,0,2.8]}
        groups=[sorted(p.glob('*.png')) for p in sorted((ROOT/'data/bottle/test').iterdir()) if p.is_dir()]
        # Input preparation only: cycle folders without exposing ground truth to inspection.
        images=[group[i] for i in range(max(map(len,groups),default=0)) for group in groups if i<len(group)][:self.config['max_images']['value']]
        if not images:raise ValueError('Live BOTTLE images are missing')
        for c in model['components']:
            c['position']=positions[c['id']];c['mtbf']=0
            if c['kind']=='Source':c['interarrival']=self.config['interarrival_seconds']['value']
            if c['kind']=='Conveyor':c['length']=1.6;c['speed']=.5
            if c['kind']=='Machine':c['processing_time']=1.
            if c['kind']=='Inspection':
                c.update(inspection_mode='ccifps',run_id=self.config['run_id'],category='bottle',image_paths=[str(x.relative_to(ROOT)) for x in images],robot_model='m0609',processing_time=self.config['inspection_hold_seconds']['value'])
        return FactoryModel.model_validate(model)

    def inspect_once(self,component,part):
        pid=part['id']
        if pid not in self.decisions:
            if os.environ.get('CUDA_VISIBLE_DEVICES','').strip():raise ValueError('Live Ops requires CPU-only process (CUDA_VISIBLE_DEVICES empty)')
            self.inspection_busy=True;begin=time.monotonic()
            try:
                result=self.inspection(component,part)
                if result.get('verdict') not in ('OK','NG','SKIPPED'):raise ValueError('Invalid inspection result')
                result=copy.deepcopy(result)
                if result.get('evidence'):
                    key=result['evidence']['id']
                    result['evidence']['original_url']=f'/api/live/evidence/{key}/original.png'
                    result['evidence']['overlay_url']=f'/api/live/evidence/{key}/overlay.png'
                self.decisions[pid]=result
            except Exception as exc:self.decisions[pid]=dict(verdict='SKIPPED',reason=str(exc),mode='ccifps')
            finally:self.elapsed_inference+=time.monotonic()-begin;self.inspection_busy=False
            self.record('live_inspection_ready',part=pid,**self.decisions[pid])
        return copy.deepcopy(self.decisions[pid])

    def record(self,kind,**fields):
        event=dict(sequence=len(self.events),sim_time=self.service.engine.now,type=kind,**fields)
        self.events.append(event)
        with (self.directory/'live_events.jsonl').open('a') as f:f.write(json.dumps(event,ensure_ascii=False)+'\n')

    def _observe(self,dt):
        snap=self.service.snapshot()
        self.patrol.tick(snap,dt);self.maintenance.tick(self.service.engine,self.patrol,dt)
        # Inference is performed once at the existing INSPECT stage. The original
        # DES receives that same result at its unchanged completion boundary.
        for node in self.service.engine.nodes.values():
            if node['c'].kind!='Inspection' or not node['c'].robot_model:continue
            for job in node['jobs']:
                robot=self.service.engine.robot_state(node,job)
                if robot['stage']=='INSPECT' and not node['down'] and job['part']['id'] not in self.decisions:
                    self.busy_snapshot=self.snapshot()
                    self.inspect_once(node['c'],job['part'])
                if 'RELEASE' in job['robot_checks'] and job['part']['id'] not in self.releases:
                    pid=job['part']['id'];self.releases.add(pid)
                    self.record('live_robot_release',part=pid,verdict=self.decisions.get(pid,{}).get('verdict','SKIPPED'),component=node['c'].id)

    def advance(self,wall_dt):
        with self.lock:
            if self.service.engine.status!='running':return
            remaining=min(max(wall_dt,0),.25)
            while remaining>1e-8 and self.service.engine.status=='running':
                step=min(remaining,.2/float(self.service.speed));before=self.service.engine.now
                self.service.tick(step);self._observe(self.service.engine.now-before);remaining-=step
            self.stream_sequence+=1

    def ensure_thread(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return
            def run():
                previous=time.monotonic()
                while not self.stop.wait(.08):
                    now=time.monotonic()
                    try:self.advance(now-previous)
                    except Exception as exc:
                        with self.lock:self.service.engine.status='error';self.service.engine.error=str(exc)
                    previous=time.monotonic()  # CPU inference time never becomes a catch-up jump.
            self.thread=threading.Thread(target=run,name='cnotta-cpu-live',daemon=True);self.thread.start()

    def control(self,operation,speed=1):
        with self.lock:
            if operation=='start':
                if speed not in (1,2,5,20):raise ValueError('Unsupported live speed')
                self.service.call('start_simulation',{'speed':str(speed)})
            elif operation=='pause':self.service.call('pause_simulation')
            else:raise ValueError('Unknown live operation')
            return self.snapshot()

    def pose(self,robot,verdict):
        if not robot:return None
        result=copy.deepcopy(robot)
        # Distinct OK/NG fixtures, using the same seven-stage schedule. Verify
        # the derived base-joint move against the official velocity/position limits.
        ng_motion=result['stage'] in ('MOVE_PLACE','RELEASE','RETURN_HOME') or (result['stage']=='MAINTENANCE_SELF_TEST' and 'INSPECT' in result.get('completed_steps',[]))
        if verdict!='OK' and ng_motion:
            scale=self.config['motion']['ng_base_scale' if verdict=='NG' else 'hold_base_scale']
            for key in ('joints','target','velocity'):result[key][0]*=scale
            if any(abs(v)>j['velocity']+1e-9 for v,j in zip(result['velocity'],JOINTS)):raise ValueError('Live robot velocity exceeds URDF limit')
            frames,tool=fk(result['joints']);result.update(frames=[m.T.flatten().tolist() for m in frames],tool_frame=tool.T.flatten().tolist(),tcp=tool_point(tool))
        result['placement']=verdict if verdict in ('OK','NG') else 'HOLD'
        result['controller']='existing URDF trajectory + assumed NG/HOLD base-joint scaling'
        return result

    def stream_snapshot(self):
        # Keep the last exact INSPECT state visible while the CPU detector works.
        # Neither the browser nor this adapter advances DES time during inference.
        if self.inspection_busy and self.busy_snapshot is not None:
            result=copy.deepcopy(self.busy_snapshot);result['inspection_busy']=True
            return result
        return self.snapshot()

    def snapshot(self):
        with self.lock:
            snap=self.service.snapshot()
            for part in snap['parts']:
                decision=self.decisions.get(part['id'])
                if decision:part.update(live_inspection=copy.deepcopy(decision),verdict=decision['verdict'])
                if part.get('robot',{} ) and part['robot']['stage']=='MAINTENANCE_SELF_TEST':
                    job=next(j for j in self.service.engine.nodes[part['component']]['jobs'] if j['part']['id']==part['id'])
                    part['robot'].update(completed_steps=list(job['robot_checks']),attached=job['gripper_closed'],gripper='CLOSED' if job['gripper_closed'] else 'OPEN')
                part['robot']=self.pose(part.get('robot'),part.get('verdict'))
                if part.get('robot') and 'RELEASE' in part['robot'].get('completed_steps',[]):
                    q=list(POSES['place']);q[0]*=1 if part.get('verdict')=='OK' else self.config['motion']['ng_base_scale' if part.get('verdict')=='NG' else 'hold_base_scale']
                    part['released_tcp']=tool_point(fk(q)[1])
            for cid,resource in snap['metrics']['resources'].items():
                part=next((p for p in snap['parts'] if p['component']==cid),None)
                resource['robot']=part['robot'] if part else self.pose(resource.get('robot'),None)
            patrol=self.patrol.snapshot();patrol['source']='existing A* supervisor; time delta from live DES'
            snap.update(mode='live',sim=1,session=self.session,sequence=self.stream_sequence,device='cpu',class_name='bottle',selector='ccifps',patrol=patrol,live_events=copy.deepcopy(self.events[-80:]),inspection_busy=self.inspection_busy,inference_wall_seconds=self.elapsed_inference,robot_info=self.info,source='isolated existing FactoryService; not research results',assumptions=self.config)
            return snap

_runtime=None
_runtime_lock=threading.Lock()
def runtime():
    global _runtime
    with _runtime_lock:
        if _runtime is None:_runtime=LiveOps()
        return _runtime

class Control(BaseModel):
    speed:Literal[1,2,5,20]=1

@router.get('/snapshot')
def snapshot():return runtime().stream_snapshot()

@router.post('/control/{operation}')
def control(operation:Literal['start','pause'],request:Control):
    r=runtime();result=r.control(operation,request.speed)
    if operation=='start':r.ensure_thread()
    return result

class Fault(BaseModel):
    cause:Literal['gripper_jam','camera_disconnect']='gripper_jam'

@router.post('/fault')
def fault(request:Fault):
    r=runtime()
    with r.lock:
        task=r.maintenance.start(r.service.engine,'AI-INSPECTION',request.cause);r._observe(0)
    return task

@router.get('/evidence/{key}/{name}')
def evidence(key:str,name:str):
    try:return FileResponse(runtime().inspection.evidence.file(key,name))
    except ValueError as exc:raise HTTPException(404,str(exc)) from exc

@router.websocket('/ws')
async def stream(socket:WebSocket):
    await socket.accept()
    try:
        while True:
            data=await asyncio.to_thread(runtime().stream_snapshot)
            await socket.send_json(data)
            await asyncio.sleep(.1)
    except (WebSocketDisconnect,RuntimeError):pass
