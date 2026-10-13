import json
import pytest
from fastapi.testclient import TestClient
from aria.dashboard import store
from aria.dashboard.campus import select_lanes
from aria.dashboard.server import app

CLIENT=TestClient(app)
LAYOUT={'sites':[{'kind':'inspection_hall','id':'test','name':'1공장 BOTTLE','class':'bottle','lanes':['coreset','ccifps','random_same_k'],'run_selector':{'seed':0,'cell':'inline','speed':.5,'latency_mode':'profile'}}]}

def row(**changes):
 return {'run_id':'a'*16,'class_name':'bottle','selector':'ccifps','seed':0,'cell':'inline','speed':.5,'latency_mode':'profile','_path':'private',**changes}

@pytest.mark.parametrize('change',[{'class_name':'screw'},{'seed':1},{'speed':1.},{'cell':'robot'},{'latency_mode':'sampled'}])
def test_campus_never_substitutes_incomparable_runs(change):
 result=select_lanes(LAYOUT,[row(**change)])[0]['lanes']
 assert all(lane['status']=='pending' and lane['run'] is None for lane in result)

def test_campus_missing_lane_explicit_and_no_internal_path():
 lanes=select_lanes(LAYOUT,[row()])[0]['lanes']
 assert [l['status'] for l in lanes]==['pending','ready','pending']
 assert '_path' not in lanes[1]['run']

def test_completed_partial_run_exposed_without_releasing_summary(tmp_path,monkeypatch):
 monkeypatch.setattr(store,'FULL',tmp_path)
 folder=tmp_path/'runs'/('b'*16);folder.mkdir(parents=True)
 config={k:v for k,v in row().items() if k not in ('run_id','_path')};config['policy']='A'
 # A partial directory without a completion marker must not enter the catalog.
 (folder/'parts.csv.gz').write_bytes(b'fixture')
 store._campus_completed.cache_clear()
 assert not any(r['run_id']==folder.name for r in store.catalog())
 (folder/'complete.json').write_text(json.dumps({'lock':{'config':config},'hashes':{'parts.csv.gz':'tampered'}}))
 store._campus_completed.cache_clear()
 selected=next(r for r in store.catalog() if r['run_id']==folder.name)
 assert selected['source']=='completed-run'
 assert CLIENT.get('/api/dt/results/summary').status_code==404
 # The existing artifact verification is still mandatory for new sources.
 assert CLIENT.get(f'/api/dt/runs/{folder.name}/timeline').status_code==409
 assert (folder/'parts.csv.gz').read_bytes()==b'fixture'
 store._campus_completed.cache_clear()

def test_campus_endpoint_read_only_exact_nine_slots():
 r=CLIENT.get('/api/dt/campus');assert r.status_code==200
 d=r.json();assert len(d['sites'])==3
 assert [s['name'] for s in d['sites']]==['1공장 BOTTLE','2공장 SCREW','3공장 CARPET']
 assert all(len(s['lanes'])==3 for s in d['sites'])
 assert d['ready_lanes']==sum(l['status']=='ready' for s in d['sites'] for l in s['lanes'])
 assert '_path' not in r.text and 'is_defect' not in r.text
 assert CLIENT.post('/api/dt/campus').status_code==405
