import json
import math
import pytest
from aria.simulation.des import FactoryModel, Engine, demo_factory
from aria.simulation.des.model import Component, Connection
from aria.simulation.des.service import FactoryService
from aria.simulation.des.agent import IndustrialAgent


def simple(processing=1, arrival=2, capacity=1, **machine):
    return FactoryModel(components=[Component(id='S', kind='Source', interarrival=arrival),
        Component(id='M', kind='Machine', processing_time=processing, capacity=capacity, **machine),
        Component(id='Z', kind='Sink')], connections=[Connection(source='S', target='M'), Connection(source='M', target='Z')])


def test_reproducibility_and_conservation():
    a, b = Engine(demo_factory()), Engine(demo_factory())
    for t in range(1, 601):
        a.run_until(t)
        assert a.serial == sum(a.counts.values()) + sum(len(n['jobs']) for n in a.nodes.values())
        assert all(len(n['jobs']) <= n['c'].capacity for n in a.nodes.values())
    b.run_until(600)
    assert a.snapshot()['parts'] == b.snapshot()['parts']
    assert a.metrics()['counts'] == b.metrics()['counts']
    assert a.metrics()['lead_time'] == pytest.approx(b.metrics()['lead_time'])
    assert a.bottlenecks()[0]['component'] == 'MACHINE-01'


def test_exact_metrics_and_starvation():
    e = Engine(simple())
    m = e.run_until(10)
    assert m['completed'] == 5
    assert m['throughput_per_hour'] == 1800
    assert m['lead_time'] == 1
    assert m['cycle_time'] == 2
    assert m['resources']['M']['utilization'] == .5
    assert m['resources']['M']['starvation_time'] == 5
    assert m['counts']['UNINSPECTED'] == 5
    assert m['oee'] == 0  # uninspected production is not certified OK


def test_failure_interrupts_then_resumes_remaining_work():
    e = Engine(simple(processing=4, arrival=20))
    e.schedule(1., 'failure', 'M')
    e.nodes['M']['c'].mttr = 2
    e.run_until(5)
    assert e.metrics()['completed'] == 0
    e.run_until(6)
    assert e.metrics()['completed'] == 1
    assert e.metrics()['lead_time'] == 6
    assert e.metrics()['resources']['M']['downtime'] == 2
    assert e.metrics()['resources']['M']['utilization'] == pytest.approx(4/6)


def test_setup_time_is_not_processing():
    e = Engine(simple(processing=2, arrival=20, setup_time=3))
    e.run_until(5)
    r = e.metrics()['resources']['M']
    assert e.metrics()['completed'] == 1
    assert r['state_times']['SETUP'] == 3
    assert r['utilization'] == .4


def test_blocking_buffer_capacity_and_waiting():
    model = simple(processing=10, arrival=1)
    data = model.model_dump()
    data['components'].insert(1, Component(id='B', kind='Buffer', capacity=2).model_dump())
    data['connections'] = [dict(source='S', target='B'), dict(source='B', target='M'), dict(source='M', target='Z')]
    e = Engine(data)
    e.run_until(25)
    assert len(e.nodes['B']['jobs']) == 2
    assert e.metrics()['resources']['S']['blocking_time'] > 0
    assert e.metrics()['resources']['B']['waiting_time'] > 0
    assert e.metrics()['wip'] == e.serial - e.metrics()['completed']


def test_downstream_blocking_retains_finished_part():
    data = simple().model_dump()
    data['components'][-1]['maintenance'] = True
    e = Engine(data)
    e.run_until(10)
    assert e.nodes['M']['state'] == 'BLOCKED'
    assert e.metrics()['resources']['M']['blocking_time'] == 9
    assert e.metrics()['completed'] == 0


@pytest.mark.parametrize('rate,verdict,sink', [(0,'OK','GOOD-SINK'), (1,'NG','REJECT-SINK')])
def test_inspection_routes(rate, verdict, sink):
    model = demo_factory().model_dump()
    next(c for c in model['components'] if c['kind'] == 'Inspection')['defect_rate'] = rate
    e = Engine(model);e.run_until(100)
    assert e.counts[verdict] > 0
    assert e.nodes[sink]['total'] == e.metrics()['completed']


def test_actual_inspection_adapter_and_missing_assets_are_not_mocked():
    model = demo_factory().model_dump()
    next(c for c in model['components'] if c['kind'] == 'Inspection')['inspection_mode'] = 'ccifps'
    calls = []
    def inspect(c,p):
        calls.append(p['id']);return dict(verdict='NG',score=.9)
    e = Engine(model, inspect);e.run_until(100)
    assert calls and e.counts['NG'] == len(calls)
    unavailable = Engine(model);unavailable.run_until(100)
    assert unavailable.counts['SKIPPED'] > 0
    assert unavailable.nodes['HOLD-SINK']['total'] == unavailable.metrics()['completed']
    assert any(x.get('reason') == 'Detector adapter unavailable' for x in unavailable.history)


@pytest.mark.parametrize('change', [
    lambda m: m['components'][0].update(interarrival=0),
    lambda m: m['components'][1].update(processing_time=float('nan')),
    lambda m: m['components'][1].update(capacity=0),
    lambda m: m['connections'].append(dict(source='M',target='S')),
    lambda m: m['connections'].append(dict(source='missing',target='M')),
])
def test_invalid_models_rejected(change):
    m = simple().model_dump();change(m)
    with pytest.raises(ValueError):FactoryModel.model_validate(m)


def test_controls_and_reset(tmp_path):
    s = FactoryService(tmp_path)
    assert s.tick(1) is None
    s.call('start_simulation',dict(speed='20'));s.tick(.5)
    assert s.engine.now == 10
    s.call('pause_simulation');t=s.engine.now
    assert s.tick(1) is None
    assert s.engine.now == t
    s.call('step_simulation');assert s.engine.events_processed > 0
    s.call('reset_simulation');assert s.engine.now == 0 and s.engine.serial == 0


def test_proposal_approval_revision_undo_and_persistence(tmp_path):
    s = FactoryService(tmp_path)
    p = s.call('update_component',dict(id='MACHINE-01',changes=dict(capacity=2)))
    stale = s.call('update_component',dict(id='MACHINE-01',changes=dict(capacity=3)))
    assert s.engine.nodes['MACHINE-01']['c'].capacity == 1
    with pytest.raises(PermissionError):s.call('apply_factory_change',dict(id=p['id']))
    s.call('apply_factory_change',dict(id=p['id']),human=True)
    assert FactoryService(tmp_path).engine.nodes['MACHINE-01']['c'].capacity == 2
    with pytest.raises(ValueError):s.call('apply_factory_change',dict(id=stale['id']),human=True)
    p = s.call('undo_factory_change');s.call('apply_factory_change',dict(id=p['id']),human=True)
    assert s.engine.nodes['MACHINE-01']['c'].capacity == 1


def test_agent_uses_measured_experiments_and_only_proposes(tmp_path):
    s = FactoryService(tmp_path)
    result = IndustrialAgent(s).run('throughput을 최소 10% 개선해줘')
    assert 'error' not in result
    assert result['proposal']['status'] == 'pending'
    evidence = result['evidence']
    gain = evidence['candidates'][0]['improvement_percent']
    assert gain >= 10
    assert result['proposal']['expected']['improvement_percent'] == gain
    assert s.engine.now == 0
    assert s.engine.nodes['MACHINE-01']['c'].capacity == 1
    assert len(result['trace']) <= 8
    assert 'run_parameter_sweep' in [t['tool'] for t in result['trace']]
    json.dumps(result,allow_nan=False)


def test_agent_observes_bottleneck(tmp_path):
    s=FactoryService(tmp_path)
    result=IndustrialAgent(s).run('현재 병목이 어디야?')
    assert 'MACHINE-01' in result['answer']
    assert '600초' in result['answer']
    assert result['evidence']['metrics']['time'] == 600


def test_sweep_budget_and_scenarios(tmp_path):
    s=FactoryService(tmp_path)
    scenario=s.call('create_scenario',dict(name='baseline'))
    again=FactoryService(tmp_path)
    assert again.call('list_scenarios')[0]['id'] == scenario['id']
    with pytest.raises(ValueError):s.call('run_parameter_sweep',dict(component='MACHINE-01',parameters={'capacity':list(range(1,15))}))
    with pytest.raises(ValueError):s.call('run_scenario',dict(id=scenario['id'],duration=float('inf')))


def test_offline_language_edits_remain_proposals(tmp_path):
    s=FactoryService(tmp_path)
    result=IndustrialAgent(s).run('MACHINE-01 처리 시간을 2.5초로 변경해줘')
    assert result['proposal']['status']=='pending'
    assert next(c for c in result['proposal']['after']['components'] if c['id']=='MACHINE-01')['processing_time']==2.5
    assert s.engine.nodes['MACHINE-01']['c'].processing_time==3


def test_runtime_budget_does_not_invent_metrics():
    e=Engine(demo_factory())
    with pytest.raises(ValueError, match='wall-time budget'):
        e.run_until(600,deadline=0.0001)
    assert e.metrics()['completed']==0
