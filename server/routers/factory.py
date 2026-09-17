"""Factory REST and agent gateway; shares ARIA's existing WS channel."""
import asyncio
import time
import os
import threading
from pathlib import Path
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel, Field
from aria.simulation.des.service import FactoryService, TOOL_NAMES
from aria.simulation.des.inspection import InspectionAdapter
from aria.simulation.des.agent import IndustrialAgent
from aria.simulation.des.patrol import PatrolSupervisor
from aria.simulation.des.maintenance import MaintenanceHarness
from typing import Literal
from server.ws import manager

ROOT = Path(__file__).resolve().parents[2]
service = FactoryService(Path(os.environ.get('ARIA_FACTORY_STATE_DIR', str(ROOT / 'outputs' / 'factory'))), InspectionAdapter(ROOT))
router = APIRouter(prefix='/api/factory', tags=['factory'])
agent_lock = asyncio.Lock()
patrol = PatrolSupervisor(service.directory)
patrol_lock = threading.RLock()
maintenance = MaintenanceHarness()

def patrol_view():
    with patrol_lock:
        return patrol.snapshot()

def patrol_tick(dt):
    with service.lock, patrol_lock:
        patrol.tick(service.snapshot(), dt)
        maintenance.tick(service.engine, patrol, dt)
        return patrol.snapshot()

@router.get('/patrol')
async def get_patrol():
    return await asyncio.to_thread(patrol_view)

@router.get('/patrol/report')
async def patrol_report():
    with patrol_lock:
        report = patrol.markdown()
    return Response(report, media_type='text/markdown', headers={'Content-Disposition': 'attachment; filename="aria-incident-report.md"'})

class PatrolControl(BaseModel):
    enabled: bool

@router.post('/patrol/control')
async def patrol_control(payload: PatrolControl):
    with patrol_lock:
        patrol.enabled = payload.enabled
    return patrol_view()

class FaultRequest(BaseModel):
    component: str
    duration: float = Field(default=60, ge=1, le=300)

@router.post('/patrol/fault')
async def virtual_fault(payload: FaultRequest):
    def inject():
        with service.lock:
            e=service.engine
            if payload.component not in e.nodes or e.nodes[payload.component]['c'].kind not in ('Machine','Inspection'):
                raise ValueError('Select a machine or inspection station')
            if e.nodes[payload.component]['down']:
                raise ValueError('Equipment is already down')
            if e.now >= e.model.simulation.duration:
                raise ValueError('Reset the completed simulation before running a fault scenario')
            e.schedule(e.now,'failure',payload.component,epoch=payload.duration)
            e.emit('fault_injected', component=payload.component, duration=payload.duration, source='operator simulation test')
            e.run_until(e.now)
            e.status='running'
        return patrol_tick(0)
    try:
        result=await asyncio.to_thread(inject)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    await publish()
    await manager.broadcast(dict(type='patrol_state', **result))
    return result


class MaintenanceFaultRequest(BaseModel):
    component: str
    cause: Literal['gripper_jam', 'camera_disconnect', 'unknown'] = 'gripper_jam'

@router.post('/maintenance/fault')
async def maintenance_fault(payload: MaintenanceFaultRequest):
    def inject():
        with service.lock, patrol_lock:
            task=maintenance.start(service.engine,payload.component,payload.cause)
            patrol_tick(0)
            return task
    try:
        result=await asyncio.to_thread(inject)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    await publish()
    await manager.broadcast(dict(type='patrol_state', **patrol_view()))
    return result

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)

async def invoke(name, args=None, human=False):
    if name == 'get_patrol_report':
        return await asyncio.to_thread(patrol_view)
    try:
        result = await asyncio.to_thread(service.call, name, args, human)
    except (ValueError, KeyError, StopIteration, PermissionError) as exc:
        raise HTTPException(status_code=409 if isinstance(exc, PermissionError) else 422, detail=str(exc)) from exc
    return result

async def publish():
    snap = await asyncio.to_thread(service.snapshot)
    await manager.broadcast(dict(type='simulation_state', **snap))
    return snap

@router.get('/snapshot')
async def snapshot():
    return await asyncio.to_thread(service.snapshot)

@router.get('/model')
async def model():
    return await invoke('get_factory_model')

@router.put('/model')
async def set_model(payload: dict = Body(...)):
    return await invoke('propose_factory_change', dict(model=payload, reason='Load factory model'))

@router.get('/components')
async def components():
    return await invoke('list_components')

@router.post('/components')
async def create(payload: dict = Body(...)):
    return await invoke('create_component', dict(component=payload))

@router.patch('/components/{cid}')
async def update(cid: str, payload: dict = Body(...)):
    return await invoke('update_component', dict(id=cid, changes=payload))

@router.delete('/components/{cid}')
async def delete(cid: str):
    return await invoke('delete_component', dict(id=cid))

@router.post('/connect')
async def connect(payload: dict = Body(...)):
    return await invoke('connect_components', payload)

def control_route(tool):
    async def endpoint(payload: dict = Body(default={})):
        await invoke(tool, payload)
        return await publish()
    return endpoint

for operation, tool in [('run', 'start_simulation'), ('pause', 'pause_simulation'),
                         ('resume', 'resume_simulation'), ('step', 'step_simulation'), ('reset', 'reset_simulation')]:
    router.add_api_route('/' + operation, control_route(tool), methods=['POST'], name=operation)

@router.get('/metrics')
async def metrics():
    return await invoke('get_simulation_metrics')

@router.get('/bottlenecks')
async def bottlenecks():
    return await invoke('get_bottleneck_analysis')

@router.get('/scenarios')
async def scenarios():
    return await invoke('list_scenarios')

@router.post('/scenarios')
async def scenario(payload: dict = Body(default={})):
    return await invoke('create_scenario', payload)

@router.post('/scenarios/{sid}/run')
async def run_scenario(sid: str, payload: dict = Body(default={})):
    return await invoke('run_scenario', dict(payload, id=sid))

@router.post('/experiments')
async def experiment(payload: dict = Body(...)):
    await manager.broadcast(dict(type='experiment_progress', status='running'))
    try:
        result = await invoke('run_parameter_sweep', payload)
        await manager.broadcast(dict(type='experiment_progress', status='completed', result=result))
        return result
    except Exception:
        await manager.broadcast(dict(type='experiment_progress', status='failed'))
        raise

@router.get('/tools')
async def tools():
    return dict(tools=(*TOOL_NAMES, 'get_patrol_report'), changes='All model mutations create reviewable proposals')

@router.post('/tools/{name}')
async def tool(name: str, payload: dict = Body(default={})):
    result = await invoke(name, payload)
    await publish()
    return result

@router.post('/proposals/{pid}/{decision}')
async def decide(pid: str, decision: str):
    if decision not in ('apply', 'reject'):
        raise HTTPException(422, 'Use apply or reject')
    result = await invoke('apply_factory_change' if decision == 'apply' else 'reject_factory_change', dict(id=pid), human=True)
    await publish()
    return result

@router.post('/agent')
async def chat(payload: ChatRequest):
    if agent_lock.locked():
        raise HTTPException(409, 'Agent already processing a request')
    async with agent_lock:
        await manager.broadcast(dict(type='agent_plan', scope='factory', goal=payload.message))
        def execute():
            if any(word in payload.message.lower() for word in ('보고', '문제', '순찰', 'report', 'patrol', 'incident')):
                evidence=patrol_view()
                rows=evidence['reports'][:5]
                summaries=[f"{r['component']}: {r['kind']} ({r['status']}, 현장 확인 {r['verified_by'] or '대기'})" for r in rows]
                answer=f"관찰된 문제 {len(evidence['reports'])}건, 현재 활성 {evidence['open_incidents']}건입니다. " + ('; '.join(summaries) if rows else '현재까지 관찰된 이상은 없습니다.')
                return dict(answer=answer,route='deterministic reporter',evidence=evidence,trace=[dict(tool='get_patrol_report',arguments={},result=evidence)])
            # A proposal must describe exactly the model observed by its experiment.
            with service.lock:
                return IndustrialAgent(service).run(payload.message)
        result = await asyncio.to_thread(execute)
        for step in result.get('trace', []):
            await manager.broadcast(dict(type='agent_action', scope='factory', tool=step['tool']))
            await manager.broadcast(dict(type='agent_observation', scope='factory', tool=step['tool'], result=step['result']))
        await manager.broadcast(dict(type='agent_result', scope='factory', **result))
        await publish()
        return result

async def simulation_loop():
    previous = time.monotonic()
    while True:
        await asyncio.sleep(.15)
        now = time.monotonic()
        snap = await asyncio.to_thread(service.tick, now - previous)
        patrol_state = await asyncio.to_thread(patrol_tick, now - previous)
        await manager.broadcast(dict(type='patrol_state', **patrol_state))
        previous = now
        if snap is not None or patrol_state.get('maintenance'):
            await publish()


@router.get('/evidence/{key}/{name}')
async def evidence_file(key: str,name: str):
    from aria.simulation.des.evidence import EvidenceStore
    try:
        return FileResponse(EvidenceStore(ROOT).file(key,name))
    except ValueError as exc:
        raise HTTPException(404,str(exc)) from exc

@router.get('/inspection/catalog')
async def inspection_catalog():
    import json
    bundles=[]
    for path in sorted((ROOT/'banks/ccifps').glob('*/manifest.json')):
        try:
            m=json.loads(path.read_text())
            if m.get('status')=='completed':
                bundles.append({k:m[k] for k in ('run_id','category','threshold')})
        except (ValueError,KeyError):continue
    images=[]
    for b in bundles:
        for group in sorted((ROOT/'data'/b['category']/'test').glob('*')):
            for p in sorted(group.glob('*.png'))[:12]:
                images.append(dict(path=str(p.relative_to(ROOT)),category=b['category'],label=group.name))
    return dict(bundles=bundles,images=images[:200])

class InspectionPreviewRequest(BaseModel):
    image: str = Field(max_length=500)
    run_id: str = Field(pattern=r'^ccifps_[a-f0-9]{32}$')

preview_adapter = InspectionAdapter(ROOT)
preview_lock = asyncio.Lock()

@router.post('/inspection/preview')
async def inspection_preview(payload: InspectionPreviewRequest):
    from aria.simulation.des.model import Component
    if preview_lock.locked():raise HTTPException(409,'Inspection preview already running')
    async with preview_lock:
        try:
            component=Component(id='PREVIEW',kind='Inspection',inspection_mode='ccifps',run_id=payload.run_id,image_paths=[payload.image])
            return await asyncio.to_thread(preview_adapter,component,{'serial':1})
        except Exception as exc:
            raise HTTPException(422,str(exc)[:300]) from exc


@router.get('/robot/model')
async def robot_model():
    from aria.simulation.des.robot import model_info
    return model_info()
