import copy
import json
import math
import threading
import pytest
from aria.dashboard.live import LiveOps
from aria.simulation.des.robot import fk, tool_point, JOINTS, POSES


def fixture_detector(c,p):
 return dict(verdict='NG' if int(p['id'][1:])%2 else 'OK',score=.8 if int(p['id'][1:])%2 else .2,threshold=.4,mode='fixture')


def test_same_part_inference_before_place_once_and_no_open_carry(tmp_path,monkeypatch):
 monkeypatch.setenv('CUDA_VISIBLE_DEVICES','')
 seen=[]
 def detector(c,p):seen.append((p['id'],r.service.engine.now));return fixture_detector(c,p)
 r=LiveOps(tmp_path,detector);r.control('start',1);released={};closed=0
 for _ in range(650):
  r.advance(.1);s=r.snapshot()
  assert s['metrics']['wip']==len(s['parts'])
  for p in s['parts']:
   robot=p['robot']
   if not robot:continue
   assert not (robot['gripper']=='OPEN' and robot['attached'])
   if robot['stage']=='MOVE_PLACE':assert p['id'] in r.decisions
   if robot['attached']:closed+=1
   if 'released_tcp' in p:
    q=list(POSES['place']);q[0]*=2 if p['verdict']=='NG' else 1
    assert p['released_tcp']==tool_point(fk(q)[1])
    if p['id'] in released:assert released[p['id']]==p['released_tcp']
    released[p['id']]=p['released_tcp']
   assert all(abs(v)<=j['velocity']+1e-9 for v,j in zip(robot['velocity'],JOINTS))
  if len(released)>=3 and s['metrics']['completed']>=3:break
 assert closed and len(released)>=3
 assert len(seen)==len({pid for pid,_ in seen})
 assert {e['part'] for e in r.events if e['type']=='live_robot_release'}<=set(r.decisions)
 for e in s['inspections']:
  d=r.decisions[e['part']];assert e['verdict']==d['verdict'] and e['score']==d['score']
 assert not math.isclose(r.info['fixtures']['ng'][0],r.info['fixtures']['pick'][0])
 assert r.info['fixtures']['ng']!=r.info['fixtures']['place']
 # Adapter must not publish early verdicts back into engine-owned part records.
 for n in r.service.engine.nodes.values():
  for j in n['jobs']:assert 'live_inspection' not in j['part']


@pytest.mark.parametrize('seed',range(10))
def test_fault_dispatch_onsite_verified_recovery_then_production(tmp_path,monkeypatch,seed):
 monkeypatch.setenv('CUDA_VISIBLE_DEVICES','')
 r=LiveOps(tmp_path,fixture_detector,seed);r.control('start',20)
 task=r.maintenance.start(r.service.engine,'AI-INSPECTION','gripper_jam');r._observe(0)
 assert r.snapshot()['metrics']['resources']['AI-INSPECTION']['state']=='DOWN'
 for _ in range(90):
  r.advance(.1)
  if r.maintenance.tasks[0]['state']=='RESTORED' and r.service.engine.counts['OK']+r.service.engine.counts['NG']>0:break
 t=r.maintenance.tasks[0]
 assert t['state']=='RESTORED',t
 assert [e['state'] for e in t['trace']]==['DISPATCHED','DIAGNOSING','REPAIRING','VERIFYING','RESTORED']
 assert t['trace'][-1]['evidence']['passed'] and t['robot']
 assert [e['sim_time'] for e in t['trace']]==sorted(e['sim_time'] for e in t['trace'])
 report=next(p for p in r.patrol.reports if p['kind']=='equipment_down')
 assert report['verified_by']==t['robot'] and report['visits'][0]['sim_time']<=t['trace'][1]['sim_time']
 assert not r.service.engine.nodes['AI-INSPECTION']['down']
 assert sum(r.service.engine.counts.values())>0


def test_pause_freezes_parts_patrol_and_clock(tmp_path,monkeypatch):
 monkeypatch.setenv('CUDA_VISIBLE_DEVICES','')
 r=LiveOps(tmp_path,fixture_detector);r.control('start',20);r.advance(.2);r.control('pause')
 a=r.snapshot();r.advance(.2);b=r.snapshot()
 assert a['time']==b['time'] and a['parts']==b['parts'] and a['patrol']['robots']==b['patrol']['robots']


def test_busy_inference_publishes_exact_held_state(tmp_path,monkeypatch):
 monkeypatch.setenv('CUDA_VISIBLE_DEVICES','')
 waiting=threading.Event();finish=threading.Event()
 def detector(c,p):waiting.set();assert finish.wait(5);return fixture_detector(c,p)
 r=LiveOps(tmp_path,detector);r.control('start',20)
 def advance():
  for _ in range(10):r.advance(.1)
 thread=threading.Thread(target=advance);thread.start()
 try:
  assert waiting.wait(5)
  a=r.stream_snapshot();b=r.stream_snapshot()
  assert a['inspection_busy'] and a==b
  part=next(p for p in a['parts'] if p['robot']);assert part['robot']['stage']=='INSPECT' and part['robot']['attached']
 finally:finish.set();thread.join(10)
 assert not thread.is_alive()


def test_api_and_websocket_share_isolated_state(tmp_path,monkeypatch):
 from fastapi.testclient import TestClient
 from aria.dashboard import live
 from aria.dashboard.server import app
 monkeypatch.setenv('CUDA_VISIBLE_DEVICES','')
 r=LiveOps(tmp_path,fixture_detector);monkeypatch.setattr(live,'_runtime',r)
 with TestClient(app) as client:
  a=client.get('/api/live/snapshot').json();assert a['device']=='cpu' and a['status']=='paused'
  with client.websocket_connect('/api/live/ws') as ws:
   b=ws.receive_json();assert b['session']==a['session'] and b['time']==a['time']
  assert client.post('/api/live/control/start',json={'speed':3}).status_code==422
  assert client.post('/api/live/control/pause',json={}).json()['status']=='paused'
  assert client.post('/api/live/fault',json={'cause':'camera_disconnect'}).status_code==200
  assert client.post('/api/live/fault',json={'cause':'camera_disconnect'}).status_code==409
  from aria.simulation.des.evidence import EvidenceStore
  class EvidenceDetector:
   evidence=EvidenceStore(tmp_path)
  monkeypatch.setattr(r,'inspection',EvidenceDetector())
  assert client.get('/api/live/evidence/nope/not-allowed').status_code==404


def test_interrupted_ng_move_retains_grip_and_fixture_during_self_test(tmp_path,monkeypatch):
 monkeypatch.setenv('CUDA_VISIBLE_DEVICES','')
 r=LiveOps(tmp_path,fixture_detector);r.control('start',1)
 for _ in range(250):
  r.advance(.1);s=r.snapshot()
  p=next((p for p in s['parts'] if p['robot'] and p['robot']['stage']=='MOVE_PLACE'),None)
  if p:break
 assert p['verdict']=='NG' and p['robot']['attached']
 pid=p['id'];r.maintenance.start(r.service.engine,'AI-INSPECTION','gripper_jam');r._observe(0)
 checked=0
 for _ in range(800):
  r.advance(.1);s=r.snapshot();p=next((p for p in s['parts'] if p['id']==pid),None)
  if p and p['robot'] and p['robot']['stage']=='MAINTENANCE_SELF_TEST':
   checked+=1;assert p['robot']['attached'] and p['robot']['gripper']=='CLOSED'
  if r.maintenance.tasks[0]['state']=='RESTORED' and r.service.engine.counts['NG']>0:break
 assert checked and r.maintenance.tasks[0]['state']=='RESTORED'
 assert r.decisions[pid]['verdict']=='NG' and pid in r.releases


def test_inspection_failure_uses_hold_fixture_not_ok(tmp_path,monkeypatch):
 monkeypatch.setenv('CUDA_VISIBLE_DEVICES','')
 r=LiveOps(tmp_path,lambda c,p:dict(verdict='SKIPPED',reason='missing fixture image'))
 r.control('start',1);found=False
 for _ in range(250):
  r.advance(.1)
  for p in r.snapshot()['parts']:
   if p.get('released_tcp'):
    assert p['robot']['placement']=='HOLD'
    assert p['released_tcp']==r.info['fixtures']['hold']
    assert p['released_tcp']!=r.info['fixtures']['place']
    found=True
  if found:break
 assert found
