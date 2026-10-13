import json
import pytest
from fastapi.testclient import TestClient
from aria.dashboard.server import app
from aria.dashboard import store
from aria.simulation.dt.posthoc import reconstruct_b
client=TestClient(app)
@pytest.fixture(scope='module')
def run_id():
 rows=client.get('/api/dt/runs').json();assert len(rows)>=15
 return next(r['run_id'] for r in rows if r['cell']=='robot')
def test_catalog_policy_a_and_no_paths():
 rows=client.get('/api/dt/runs').json();assert rows and all('_path' not in x and len(x['complete_hash'])==64 for x in rows)
def test_timeline_no_gt_and_real_times(run_id):
 r=client.get(f'/api/dt/runs/{run_id}/timeline');assert r.status_code==200
 data=r.json();assert data['parts'];wire=r.text
 for banned in ['is_defect','image_id','/test/','gt_labels','wall_ns','GPU-']:assert banned not in wire
 raw=store.load(run_id)['parts'];assert data['parts'][0]['born']==raw[0]['born']
 assert data['parts'][0]['exit_time']==raw[0]['exit_time']
def test_time_filter_and_validation(run_id):
 d=client.get(f'/api/dt/runs/{run_id}/timeline?from=300&to=400').json()
 assert all(p['born']<=400 and (p['exit_time'] is None or p['exit_time']>=300) for p in d['parts'])
 assert client.get(f'/api/dt/runs/{run_id}/timeline?from=10&to=2').status_code==422
 assert client.get(f'/api/dt/runs/{run_id}/kpi?t=-1').status_code==422
 assert client.get('/api/dt/runs/not-a-run/timeline').status_code==404
 assert client.post('/api/dt/runs').status_code==405
@pytest.mark.parametrize('t',[0,400,600.5,1800,3600])
def test_evaluator_kpi(run_id,t):
 value=client.get(f'/api/dt/runs/{run_id}/kpi?t={t}').json()
 if not t:assert value['gt_quality'] is None;return
 run=store.load(run_id);_,m,n,_=reconstruct_b(run['parts'],run['gt'],seed=run['config']['seed'],warmup=600 if t>600 else 0,horizon=t)
 assert value['throughput_per_hour']==m['throughput_per_hour']
 assert value['gt_quality']==m['gt_quality']
 assert value['false_positives_per_1000']==n['false_positives_per_1000']
def test_queue_matches_posthoc(run_id):
 run=store.load(run_id);parts,*_=reconstruct_b(run['parts'],run['gt'],seed=run['config']['seed'])
 for t in [0,300,600,1800,3599]:
  expected=sum(p['reinspection_queue_enter'] is not None and p['reinspection_queue_enter']<=t and (p['reinspection_start'] is None or p['reinspection_start']>t) for p in parts)
  assert store.queue_at(run,t)==expected

def test_baseline_requires_matching_conditions():
 result=store.kpi('6e17ce8447426140',1800)
 assert result['delta'] is None # No coreset robot screw 0.5 pilot exists.
 result=store.kpi('8dd8e446a095de96',1800)
 assert result['baseline_run_id']=='8dd8e446a095de96'
 assert all(v==0 for v in result['delta'].values())

def test_summary_pending_and_rejects_unverified(tmp_path,monkeypatch):
 monkeypatch.setattr(store,'FULL',tmp_path)
 assert client.get('/api/dt/results/summary').status_code==404
 for name in ['completion.json','verification.json','run_index.json']:(tmp_path/name).write_text('{}')
 (tmp_path/'REPORT.md').write_text('incomplete');(tmp_path/'summary_ci95.csv').write_text('metric,mean\n')
 assert client.get('/api/dt/results/summary').status_code==404

def test_summary_report_numeric_crosscheck(tmp_path,monkeypatch):
 import csv
 monkeypatch.setattr(store,'FULL',tmp_path)
 (tmp_path/'completion.json').write_text(json.dumps({'completed_DES':2970,'posthoc_views':4320}))
 (tmp_path/'verification.json').write_text(json.dumps({'passed':True,'all_raw_hashes_verified':True,'all_groups_30_unique_seeds':True}))
 (tmp_path/'run_index.json').write_text('[]')
 rows=[{'class_name':'fixture','selector':'ccifps','policy':'B','scope':'main','cell':'inline','speed':.5,'latency_mode':'profile','metric':metric,'mean':value,'ci95_low':low,'ci95_high':high} for metric,value,low,high in [('throughput_per_hour',480,479,481),('hold_ratio',.1,.09,.11),('person_hours_per_1000',.03,.02,.04)]]
 with (tmp_path/'summary_ci95.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
 (tmp_path/'REPORT.md').write_text('|fixture|ccifps|B|480.00|[479.00, 481.00]|0.100000|0.0300|\n')
 r=client.get('/api/dt/results/summary');assert r.status_code==200 and r.json()['report_rows_verified']==1
 (tmp_path/'REPORT.md').write_text('|fixture|ccifps|B|481.00|[479.00, 481.00]|0.100000|0.0300|\n')
 assert client.get('/api/dt/results/summary').status_code==409
