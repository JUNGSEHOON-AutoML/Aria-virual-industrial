import json
import pytest
from aria.simulation.des import Engine, demo_factory
from aria.simulation.des.patrol import FloorPlanner, PatrolSupervisor


def snapshot(e,revision=0):
    return dict(**e.snapshot(),revision=revision)


def test_continuous_patrol_and_footprint_routes(tmp_path):
    e=Engine(demo_factory());s=PatrolSupervisor(tmp_path);s.tick(snapshot(e),.1)
    start=[r['position'][:] for r in s.robots]
    for _ in range(120):
        state=s.tick(snapshot(e),.25)
        for r in state['robots']:
            assert s.planner.free((r['position'][0],r['position'][2]))
    assert any(r['visits']>0 for r in s.robots)
    assert any(r['position']!=p for r,p in zip(s.robots,start))
    assert e.now==0  # independent observation while production is paused
    assert state['reports']==[]
    s.enabled=False
    before=[r['position'][:] for r in s.robots]
    s.tick(snapshot(e),.5)
    assert before==[r['position'] for r in s.robots]


def test_fault_report_verification_recovery_and_persistence(tmp_path):
    e=Engine(demo_factory());s=PatrolSupervisor(tmp_path)
    e.schedule(0,'failure','MACHINE-01',epoch=60);e.run_until(0)
    for _ in range(180):s.tick(snapshot(e),.25)
    reports=[r for r in s.reports if r['kind']=='equipment_down']
    assert len(reports)==1
    report=reports[0]
    assert report['verified_by'] in ('ARIA-01','ARIA-02')
    assert report['evidence']['state']=='DOWN'
    assert report['status']=='open'
    assert report['visits']
    e.run_until(60);s.tick(snapshot(e),.25)
    assert report['status']=='recovered'
    assert 'physical repair is not inferred' in report['outcome']
    saved=json.loads((tmp_path/'patrol_reports.json').read_text())
    assert any(r['id']==report['id'] for r in saved)
    assert 'MACHINE-01' in s.markdown()


def test_reset_is_not_reported_as_repair(tmp_path):
    e=Engine(demo_factory());s=PatrolSupervisor(tmp_path)
    e.schedule(0,'failure','MACHINE-01',epoch=60);e.run_until(2)
    s.tick(snapshot(e),.1);r=s.reports[0]
    e.reset();s.tick(snapshot(e),.1)
    assert r['status']=='interrupted'
    assert not s.active


def test_real_inspection_error_dedup_and_recovery(tmp_path):
    e=Engine(demo_factory());s=PatrolSupervisor(tmp_path)
    snap=snapshot(e)
    snap['events']=[dict(type='inspection_result',part='P1',time=1,component='AI-INSPECTION',verdict='SKIPPED',reason='model missing')]
    for _ in range(5):s.tick(snap,.1)
    assert len(s.reports)==1
    assert s.reports[0]['evidence']['reason']=='model missing'
    snap['events'].append(dict(type='inspection_result',part='P2',time=2,component='AI-INSPECTION',verdict='OK'))
    for _ in range(5):s.tick(snap,.1)
    assert len(s.reports)==1
    assert s.reports[0]['status']=='recovered'


def test_fault_duration_does_not_mutate_factory_config():
    e=Engine(demo_factory())
    e.schedule(0,'failure','MACHINE-01',epoch=45);e.run_until(20)
    assert e.nodes['MACHINE-01']['down']
    assert e.nodes['MACHINE-01']['c'].mttr==20
    e.run_until(45)
    assert not e.nodes['MACHINE-01']['down']
