import hashlib
import json
from pathlib import Path
import pytest
from aria.simulation.des import Engine, FactoryModel
from aria.simulation.des.model import Component, Connection
from aria.simulation.des import latency

@pytest.fixture
def profile(tmp_path, monkeypatch):
    monkeypatch.setattr(latency, 'PROFILE_ROOT', tmp_path)
    def create(values=(100., 300., 600.), **overrides):
        p=tmp_path/'fixture.json'
        data=dict(schema_version=1,source='synthetic_test',selector='synthetic_test',bank_k=1,
                  bundle_id='NOT_A_MEASURED_BANK',hardware='synthetic test',warmup=0,total_ms=list(values))
        data.update(overrides);p.write_text(json.dumps(data))
        return dict(latency_mode='profile',latency_profile='config/latency_profiles/fixture.json',
                    latency_profile_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    return create

def line(options, robot=False, **changes):
    c=dict(id='I',kind='Inspection',processing_time=.7,defect_rate=0,
           robot_model='m0609' if robot else '',**options);c.update(changes)
    return FactoryModel(seed=7,components=[Component(id='S',kind='Source',interarrival=20),
        Component(**c),Component(id='G',kind='Sink'),Component(id='H',kind='Sink')],
        connections=[Connection(source='S',target='I'),Connection(source='I',target='G',condition='OK'),
                     Connection(source='I',target='H',condition='SKIPPED')])

def simulate(model, horizon=10):
    rows=[];e=Engine(model,event_sink=rows.append);metrics=e.run_until(horizon)
    assert metrics['generated']==metrics['completed']+metrics['wip']
    return e,rows

def normalized(rows):
    return [{k:v for k,v in row.items() if k not in ('wall_ns','run_id')} for row in rows]

def test_profile_units_handling_and_no_wall_time_coupling(profile):
    e,rows=simulate(line(profile([200]),handling_time_s=.1))
    result=next(x for x in rows if x['type']=='inspection_result')
    assert result['time']==pytest.approx(.3)
    assert result['latency_ms']['total']==200
    assert result['profile_source']=='synthetic_test'
    assert result['route']=='OK' and result['deadline_met'] is None
    assert e.metrics()['resources']['I']['performance']==pytest.approx(.3/10)
    assert all(x['sim']==1 for x in rows)
    assert [x['event_seq'] for x in rows]==list(range(1,len(rows)+1))
    assert [x['wall_ns'] for x in rows]==sorted(x['wall_ns'] for x in rows)

@pytest.mark.parametrize('latency_ms,passed',[(199,True),(200,True),(201,False),(2000,False)])
def test_deadline_decision_once_and_late_result_cannot_reroute(profile,latency_ms,passed):
    model=line(profile([latency_ms]),inspection_deadline_s=.2,inspection_mode='ccifps')
    calls=[];rows=[]
    def inspect(c,p):calls.append(p['id']);return dict(verdict='OK',score=.1)
    e=Engine(model,inspect,event_sink=rows.append);e.run_until(3)
    results=[x for x in rows if x['type']=='inspection_result']
    assert len(results)==1 and results[0]['deadline_met']==passed
    assert results[0]['route']==('OK' if passed else 'HOLD')
    assert results[0]['time']==pytest.approx(min(latency_ms/1000,.2))
    assert len(calls)==int(passed)
    assert e.counts['OK']==int(passed) and e.counts['SKIPPED']==int(not passed)


def test_failure_time_counts_toward_deadline(profile):
    m=line(profile([100]),inspection_deadline_s=.2,mttr=1)
    rows=[];e=Engine(m,event_sink=rows.append);e.schedule(.05,'failure','I');e.run_until(3)
    result=next(x for x in rows if x['type']=='inspection_result')
    assert result['time']==.2 and result['route']=='HOLD'
    assert e.metrics()['completed']==1 and e.nodes['H']['total']==1


def test_setup_counts_toward_deadline(profile):
    e,rows=simulate(line(profile([100]),inspection_deadline_s=.2,setup_time=.2))
    assert e.counts['SKIPPED']==1
    assert next(x for x in rows if x['type']=='inspection_result')['time']==.2


def test_sampler_stream_reset_pins_bytes_and_does_not_advance_failure_rng(profile):
    options=profile();m=line(options)
    a,ra=simulate(m,200);b,rb=simulate(m,200)
    assert a.metrics()==b.metrics() and normalized(ra)==normalized(rb)
    (latency.PROFILE_ROOT/'fixture.json').write_text('{}')
    ra.clear();a.reset();a.run_until(200)
    assert normalized(ra)==normalized(rb)
    with pytest.raises(ValueError,match='SHA-256'):Engine(m)
    old=Engine(line({}))
    assert a.nodes['I']['rng'].getstate()==b.nodes['I']['rng'].getstate()
    # Reading profile samples itself must not consume mock or failure RNG.
    state=a.nodes['I']['rng'].getstate()
    for _ in range(50):a.latency_samplers['I'].sample()
    assert a.nodes['I']['rng'].getstate()==state


def test_profile_robot_uses_sample_in_motion_and_completes_all_acknowledgements(profile):
    e,rows=simulate(line(profile([200]),robot=True))
    result=next(x for x in rows if x['type']=='inspection_result')
    assert result['time']==pytest.approx(7.4)
    assert len([x for x in rows if x['type']=='robot_ack'])==7
    e=Engine(line(profile([200]),robot=True));e.run_until(3.7)
    assert e.robot_state(e.nodes['I'])['duration']==pytest.approx(7.4)


def test_backpressure_keeps_timeout_decision_without_duplicate(profile):
    m=line(profile([2000]),inspection_deadline_s=.2);m.components[-1].maintenance=True
    e,rows=simulate(m,4)
    assert e.metrics()['wip']==1 and e.metrics()['completed']==0
    assert len([x for x in rows if x['type']=='inspection_result'])==1
    e.nodes['H']['c'].maintenance=False;e._settle()
    assert e.counts['SKIPPED']==1

@pytest.mark.parametrize('values',[[],[0],[-1],[float('nan')],[float('inf')]])
def test_invalid_samples_rejected(profile,values):
    with pytest.raises(ValueError):Engine(line(profile(values)))


def test_path_escape_and_missing_hash_rejected(profile):
    options=profile();options['latency_profile']='config/latency_profiles/../../README.md'
    with pytest.raises(ValueError,match='escaped'):Engine(line(options))
    options['latency_profile']='/etc/passwd'
    with pytest.raises(ValueError,match='under'):Engine(line(options))
    with pytest.raises(ValueError):line(dict(latency_mode='profile'))


def test_measured_profile_cannot_use_small_or_unaligned_samples(profile):
    with pytest.raises(ValueError,match='1000'):Engine(line(profile([100],source='measured',selector='ccifps')))
    with pytest.raises(ValueError,match='aligned'):Engine(line(profile([100,200],stages_ms={'pre':[1]})))
