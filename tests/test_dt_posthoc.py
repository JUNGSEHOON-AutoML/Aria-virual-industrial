import csv
import pytest
from tools.dt_posthoc_reinspection import reconstruct_b

def inputs(tmp_path):
    gt=tmp_path/'gt.csv';gt.write_text('image_id,is_defect\nn,0\nd,1\n')
    parts=[dict(part_id=f'p{i}',image_id=image,born=0.,mainline_exit_time=0.,inspection_time=0.,ai_verdict='NG',reinspection_queue_enter=None,reinspection_start=None,reinspection_time=None,reinspection_verdict=None,exit_time=0.,route='NG') for i,image in enumerate(['n','d'])]
    return parts,gt

def test_two_servers_reduce_completion_time_without_changing_oracle(tmp_path):
    parts,gt=inputs(tmp_path)
    one,m1,n1,_=reconstruct_b(parts,gt,seed=4,service_seconds=10,servers=1,warmup=0,horizon=15)
    two,m2,n2,_=reconstruct_b(parts,gt,seed=4,service_seconds=10,servers=2,warmup=0,horizon=15)
    assert [p['reinspection_time'] for p in one]==[10,None]
    assert [p['reinspection_time'] for p in two]==[10,10]
    assert m1['completed']==1 and m1['wip']==1 and m2['completed']==2 and m2['wip']==0
    assert two[0]['route']=='OK' and two[1]['route']=='NG'
    assert n1['ng_per_1000']==n2['ng_per_1000']==1000
    assert n1['false_positives_per_1000']==500
    assert n1['person_hours_per_1000']==pytest.approx(1000*10/3600)
    assert n1['required_staff_rho_lt1']==2
    assert parts[0]['route']=='NG' # input is preserved

def test_warmup_keeps_prior_arrivals_and_busy_work(tmp_path):
    parts,gt=inputs(tmp_path)
    _,m,n,_=reconstruct_b(parts,gt,seed=4,service_seconds=10,servers=1,warmup=5,horizon=15)
    assert m['reinspection_utilization']==1
    assert m['false_positive_recovered']==1
    assert n['parts_denominator']==0 and n['person_hours_per_1000'] is None
    with pytest.raises(ValueError):reconstruct_b(parts,gt,seed=4,servers=0)
    with pytest.raises(ValueError,match='requires'):reconstruct_b(parts,None,seed=4)
