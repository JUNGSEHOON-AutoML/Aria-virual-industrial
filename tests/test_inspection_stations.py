"""New downstream contracts; existing DES/robot tests stay byte-for-byte intact."""
import copy
import math
import pytest
from aria.dashboard import stations, transfer
from aria.simulation.des import robot


def test_transfer_has_seven_stages_and_does_not_mutate_original():
    before=copy.deepcopy(robot.POSES);original=robot.program(.5)
    rows,total=transfer.program()
    assert [r['stage'] for r in rows]==['MOVE_PICK','GRIP','MOVE_TRANSFER','TRANSFER','MOVE_PLACE','RELEASE','RETURN_HOME']
    assert rows[3]['target']!=robot.POSES['inspect']
    assert robot.POSES==before and robot.program(.5)==original and total>0


def test_transfer_id_gripper_limits_and_open_object_stays_at_fixture():
    rows,total=transfer.program();last={};seen=set()
    for n in range(2001):
        s=transfer.sample(total*n/2000,object_id='BOX:real-source-id')
        seen.add(s['stage'])
        assert all(abs(v)<=j['velocity']+1e-9 for v,j in zip(s['velocity'],robot.JOINTS))
        robot.validate(s['joints'])
        if s['attached']:
            assert s['gripper']=='CLOSED' and s['attached_object_id']==s['object_id'] and s['object_tcp']==s['tcp']
        else:
            assert s['gripper']=='OPEN' and s['attached_object_id'] is None
            side='after' if s['stage'] in ('RELEASE','RETURN_HOME') else 'before'
            assert side not in last or last[side]==s['object_tcp']
            last[side]=s['object_tcp']
    assert len(seen)==7
    frozen=transfer.sample(3,object_id='BOX:real-source-id',stopped=True)
    assert frozen['velocity']==[0]*6


@pytest.mark.parametrize('value',[0,-1,math.nan,math.inf])
def test_transfer_rejects_invalid_duration(value):
    with pytest.raises(ValueError):transfer.program(value)


def test_tasks_conserve_events_and_serialize_each_actor_without_backpressure():
    events=[dict(id=f'evt:{i}',time=.2*i,object_id=f'box:{i}',kind='box',actor='arm') for i in range(5)]
    original=copy.deepcopy(events);tasks=transfer.schedule(events)
    assert len(tasks)==len(events) and len({t['source_event'] for t in tasks})==len(events)
    assert all(t['object_id']==events[i]['object_id'] for i,t in enumerate(tasks))
    assert all(a['end']<=b['start'] for a,b in zip(tasks,tasks[1:]))
    assert events==original and tasks[-1]['wait']>0
    with pytest.raises(ValueError):transfer.schedule(events+[events[0]])


def test_equipment_distance_is_integral_of_des_state_speed():
    transitions=[dict(component='AI-INSPECTION',time=t,state=s) for t,s in [(0,'STARVED'),(2,'PROCESSING'),(5,'DOWN'),(8,'PROCESSING'),(9,'BLOCKED')]]
    rows=stations.equipment_intervals(transitions,.5,10)
    assert [r['distance'] for r in rows]==[0,0,1.5,1.5,2]
    assert [r['lamp'] for r in rows]==['STOP','RUN','FAULT','RUN','STOP']
    assert sum((r['end']-r['start'])*r['speed'] for r in rows)==2


def test_carpet_keeps_all_segments_and_uses_only_on_time_ng_labels():
    _,values,_=stations.configuration();values={**values,'segments_per_roll':4,'grade_a_max_labels':0,'grade_b_max_labels':1}
    parts=[dict(id=f'p{i}',born=i,arrival=i+1,decision=i+.2,verdict=v,route=route) for i,(v,route) in enumerate([('OK','OK'),('NG','NG'),('NG','HOLD'),('OK','OK'),('NG','NG')])]
    parts[2]['decision']=4 # Too late to label segment p2 at t=3.
    before=copy.deepcopy(parts);products=stations.derive_products(parts,'carpet',values,'run')
    assert products[0]['parts']==['p0','p1','p2','p3'] and products[0]['labels']==['p1']
    assert products[0]['grade']=='B' and products[0]['unresolved']==1
    assert products[1]['ready'] is None and products[1]['grade'] is None
    assert sum(len(p['parts']) for p in products)==len(parts) and parts==before


def test_screw_bins_require_capacity_and_only_original_ok_routes():
    _,values,_=stations.configuration();values={**values,'ok_bin_capacity':2}
    parts=[dict(id=f'p{i}',born=i,arrival=i+1,route=v) for i,v in enumerate(['NG','OK','HOLD','OK','OK'])]
    bins=stations.derive_products(parts,'screw',values,'run')
    assert bins[0]['parts']==['p1','p3'] and bins[0]['ready']==4
    assert bins[1]['parts']==['p4'] and bins[1]['ready'] is None


def test_reinspection_tasks_use_arrival_and_do_not_change_oracle_time():
    parts=[dict(part_id='NG1',reinspection_queue_enter=4,reinspection_start=4,reinspection_time=34)]
    before=copy.deepcopy(parts)
    events=stations.source_events([],{'boxes':[]},parts,'bottle','run')
    tasks=transfer.schedule(events)
    assert tasks[0]['source_time']==4 and tasks[0]['object_id']=='NG1' and parts==before


def test_camera_contract_is_vertical_and_no_side_data():
    c,_,raw=stations.configuration()
    assert c['camera']['direction']==[0,-1,0] and c['camera']['side_camera_enabled'] is False
    assert all(v['tag']=='assumed' for v in raw.values())


def test_carpet_grades_do_not_depend_on_ground_truth(tmp_path):
    import csv
    original=[dict(part_id='p0',image_id='i0',ai_verdict='OK'),dict(part_id='p1',image_id='i1',ai_verdict='NG')]
    products=[dict(id='roll',parts=['p0','p1'],labels=['p1'],grade='B')];before=copy.deepcopy(products)
    path=tmp_path/'gt.csv'
    with path.open('w') as f:
        w=csv.writer(f);w.writerow(['image_id','is_defect']);w.writerows([['i0',1],['i1',1]])
    evaluation=stations.product_evaluation(products,original,path)
    assert evaluation['roll']==dict(unlabelled_defects_evaluated=1,false_negatives_evaluated=1)
    assert products==before


def test_grade_transfers_have_distinct_release_fixtures():
    fixtures=[]
    for grade in ('A','B','C'):
        rows,total=transfer.grade_program(grade)
        for row in rows:robot.validate(row['target'])
        fixtures.append(robot.tool_point(robot.fk(rows[4]['target'])[1]))
        tasks=transfer.schedule([dict(id=grade,time=0,object_id='roll',actor='production',kind='roll',grade=grade)])
        assert tasks[0]['end']==total and tasks[0]['grade']==grade
    assert len({tuple(x) for x in fixtures})==3


def test_live_projection_preserves_engine_and_uses_recorded_sources(tmp_path,monkeypatch):
    from aria.dashboard.live import LiveOps
    monkeypatch.setenv('CUDA_VISIBLE_DEVICES','')
    r=LiveOps(tmp_path,lambda c,p:dict(verdict='OK',score=.1,threshold=.4))
    r.control('start',20)
    for _ in range(18):r.advance(.1)
    raw=r.service.snapshot();before=copy.deepcopy(raw)
    r.station_view.observe(raw,r.events);projected=r.station_view.snapshot(raw)
    assert raw==before
    assert projected['equipment'][0]['distance']==raw['metrics']['resources']['CONVEYOR-02']['state_times']['PROCESSING']*.5
    for p in projected['parts']:
        if p['arrival'] is not None:assert any(e['part']==p['id'] and e['target']=='DIVERTER' and e['time']==p['arrival'] for e in raw['moves'])
    assert projected['parts'] and projected['recent']
    assert projected['latency_ms']['p95']>=projected['latency_ms']['p50']>=0
    r.control('pause');a=r.snapshot()['station'];r.advance(.2);assert r.snapshot()['station']==a


def test_baseline_is_scoped_to_the_same_source_collection(monkeypatch,tmp_path):
    from aria.dashboard import store
    cfg=dict(class_name='screw',cell='robot',speed=.5,latency_mode='profile',seed=0)
    values=dict(throughput_per_hour=10.,gt_quality=.9,false_positives_per_1000=2.,delta=None)
    pilot=tmp_path/'pilot';full=tmp_path/'full'
    monkeypatch.setattr(store,'load',lambda _:dict(config=cfg,source_root=pilot))
    monkeypatch.setattr(store,'_base_kpi',lambda *_:values)
    monkeypatch.setattr(store,'catalog',lambda:[dict(cfg,run_id='full-core',selector='coreset',_path=full/'runs/full-core')])
    store.kpi.cache_clear()
    try:
        assert store.kpi('pilot-run',17)['delta'] is None
        monkeypatch.setattr(store,'catalog',lambda:[dict(cfg,run_id='pilot-core',selector='coreset',_path=pilot/'runs/pilot-core')])
        store.kpi.cache_clear();result=store.kpi('pilot-run',17)
        assert result['baseline_run_id']=='pilot-core' and all(v==0 for v in result['delta'].values())
    finally:store.kpi.cache_clear()
