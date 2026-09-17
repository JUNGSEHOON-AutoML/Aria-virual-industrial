import math
import json
import numpy as np
import pytest
from PIL import Image
from aria.simulation.des import Engine, demo_factory
from aria.simulation.des.patrol import PatrolSupervisor
from aria.simulation.des.maintenance import MaintenanceHarness
from aria.simulation.des.robot import JOINTS, POSES, fk, program, sample, validate, tool_point
from aria.simulation.des.evidence import EvidenceStore


def make_robot():
    model=demo_factory()
    c=next(c for c in model.components if c.id=='MACHINE-01')
    c.robot_model='m0609';c.mtbf=0
    return Engine(model)


def tick(e,p,h,n=1):
    for _ in range(n):
        p.tick(dict(**e.snapshot(),revision=0),.25);h.tick(e,p,.25)


def test_joint_profile_limits_fk_and_station_targets():
    rows,duration=program(3)
    assert duration>3
    for t in np.linspace(0,duration,500):
        state=sample(3,float(t))
        validate(state['joints'])
        assert all(abs(v)<=j['velocity']+1e-9 for v,j in zip(state['velocity'],JOINTS))
        frames,tcp=fk(state['joints'])
        assert np.allclose(tool_point(tcp),state['tcp'])
        for m in frames:
            assert np.allclose(m[:3,:3].T@m[:3,:3],np.eye(3))
    for row in rows:
        if row['stage'] in ('GRIP','INSPECT','RELEASE'):
            state=sample(3,row['start']+.01)
            assert state['target_error_rad']<1e-9
    with pytest.raises(ValueError):validate([0,0,20,0,0,0])
    with pytest.raises(ValueError):validate([math.nan]*6)


def test_no_completion_during_managed_fault_then_resume_exact_motion(tmp_path):
    e=make_robot();e.run_until(13)
    node=e.nodes['MACHINE-01'];assert node['jobs']
    before=e.robot_state(node)
    h=MaintenanceHarness();p=PatrolSupervisor(tmp_path)
    task=h.start(e,'MACHINE-01','gripper_jam')
    remaining=node['jobs'][0]['remaining']
    e.schedule(14,'repair','MACHINE-01')  # old timer must not clear managed fault
    e.run_until(40)
    assert node['down'] and node['total']==0
    assert e.robot_state(node)['joints']==before['joints']
    tick(e,p,h,240)
    task=h.tasks[-1]
    assert task['state']=='RESTORED' and task['robot']
    assert [s['state'] for s in task['trace']]==['DISPATCHED','DIAGNOSING','REPAIRING','VERIFYING','RESTORED']
    assert not node['down'] and node['total']==0
    assert e.robot_state(node)['joints']==before['joints']
    e.run_until(40+remaining-.001);assert node['total']==0
    e.run_until(40+remaining+.001);assert node['total']==1
    assert json.loads((tmp_path/'patrol_reports.json').read_text())


def test_unknown_cause_escalates_and_pause_disables_harness(tmp_path):
    e=make_robot();p=PatrolSupervisor(tmp_path);h=MaintenanceHarness();h.start(e,'MACHINE-01','unknown')
    p.enabled=False;tick(e,p,h,500)
    assert h.tasks[-1]['state']=='DISPATCHED' and h.tasks[-1]['elapsed']==0
    p.enabled=True;tick(e,p,h,240)
    assert h.tasks[-1]['state']=='ESCALATED' and e.nodes['MACHINE-01']['down']
    assert h.tasks[-1]['attempts']==0


def test_verification_failure_never_releases_interlock(tmp_path):
    e=make_robot();p=PatrolSupervisor(tmp_path);h=MaintenanceHarness();h.start(e,'MACHINE-01','gripper_jam')
    for _ in range(240):
        tick(e,p,h)
        if h.tasks[-1]['state']=='VERIFYING':break
    assert h.tasks[-1]['state']=='VERIFYING'
    e.nodes['MACHINE-01']['fault']['sensors']['drive_alarm']=True
    tick(e,p,h,20)
    assert h.tasks[-1]['state']=='ESCALATED' and e.nodes['MACHINE-01']['down']


def test_reset_at_zero_cancels_stale_repair(tmp_path):
    e=make_robot();p=PatrolSupervisor(tmp_path);h=MaintenanceHarness();h.start(e,'MACHINE-01','gripper_jam');tick(e,p,h)
    token=e.run_token;e.reset();assert e.run_token!=token
    tick(e,p,h)
    assert h.tasks[-1]['state']=='INTERRUPTED'
    assert all(r['status']=='interrupted' for r in p.reports)


def test_evidence_peak_coordinates_and_safe_assets(tmp_path):
    image=tmp_path/'test.png';Image.new('RGB',(400,200),'white').save(image)
    store=EvidenceStore(tmp_path);heat=np.array([[0,1,3,0],[0,0,0,0]],dtype='f')
    e=store.save(image,{'heatmap':heat},{'verdict':'NG','score':3.,'threshold':2.})
    assert e['peak_pixel']==[250,50]
    assert e['peak_uv']==[.625,.25]
    assert Image.open(store.file(e['id'],'overlay.png')).size==(400,200)
    with pytest.raises(ValueError):store.file('../private','metadata.json')
    with pytest.raises(ValueError):store.file(e['id'],'../../x')
    with pytest.raises(ValueError):store.save(image,{'heatmap':[[float('nan')]]},{})


def test_fractional_resume_keeps_final_robot_ack_before_completion(tmp_path):
    for i in range(10):
        e=make_robot();e.run_until(12+i*.11)
        p=PatrolSupervisor(tmp_path/str(i));h=MaintenanceHarness();h.start(e,'MACHINE-01','gripper_jam')
        for _ in range(500):
            e.run_until(e.now+.25);tick(e,p,h)
            if h.tasks[-1]['state']=='RESTORED':break
        assert h.tasks[-1]['state']=='RESTORED'
        e.run_until(e.now+20)
        assert e.nodes['MACHINE-01']['total']>0


def test_all_urdf_visuals_shipped_and_http_routes_serve_xml():
    import asyncio
    import xml.etree.ElementTree as ET
    from pathlib import Path
    from httpx import AsyncClient, ASGITransport
    from server.app import app
    root=Path(__file__).resolve().parents[1]
    names=[Path(v.get('filename')).name for v in ET.parse(root/'assets/robots/doosan_m0609/m0609.urdf').findall('.//visual/geometry/mesh')]
    assert len(names)==10
    async def check():
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            for name in names:
                assert (root/'frontend/public/robots/doosan_m0609'/name).is_file()
                # HTTP integration is checked against the existing frontend build.
                response=await client.get('/robots/doosan_m0609/'+name)
                assert response.status_code==200
                assert ET.fromstring(response.text).tag.endswith('COLLADA')
            assert (await client.get('/robots/doosan_m0609/missing.dae')).status_code==404
    asyncio.run(check())


def test_preview_reuses_detector_across_images(tmp_path,monkeypatch):
    from aria.simulation.des.inspection import InspectionAdapter
    from aria.simulation.des.model import Component
    from aria.inspection import detectors
    built=[]
    class FakeDetector:
        tau=.5
        def __init__(self,run):built.append(run)
        def infer(self,image):return dict(score=.8,heatmap=np.array([[0,.8],[.1,.2]],dtype='f'))
    monkeypatch.setattr(detectors,'CCIFPSDetector',FakeDetector)
    (tmp_path/'data').mkdir()
    adapter=InspectionAdapter(tmp_path)
    for i in range(2):
        Image.new('RGB',(20,20),(i*100,0,0)).save(tmp_path/f'data/{i}.png')
        result=adapter(Component(id='I',kind='Inspection',inspection_mode='ccifps',run_id='test',image_paths=[f'data/{i}.png']),{'serial':1})
        assert result['verdict']=='NG' and result['evidence']['id']
    assert built==['test']
