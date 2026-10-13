import csv,hashlib,json
from pathlib import Path
import pytest
from aria.simulation.dt.replay import ReplayCatalog,ReplayEngine
from aria.simulation.dt.reinspect_oracle import ReinspectOracle
from aria.simulation.dt.line import load_profile,make_line
from aria.simulation.dt.evaluation import PartLedger,evaluate
from aria.simulation.des import latency

@pytest.fixture
def inputs(tmp_path,monkeypatch):
    rows=[dict(image_id='normal',image_sha256='a',bundle_id='fixture',selector='ccifps',bank_k=1,score=.8,threshold=.5,verdict='NG',is_defect=0),
          dict(image_id='defect',image_sha256='b',bundle_id='fixture',selector='ccifps',bank_k=1,score=.8,threshold=.5,verdict='NG',is_defect=1)]
    def save(path,data):
        with path.open('w') as f:w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    pred=tmp_path/'pred.csv';save(pred,rows);gt=tmp_path/'gt.csv';save(gt,[dict(image_id=r['image_id'],is_defect=r['is_defect']) for r in rows])
    profile=tmp_path/'profile.json';profile.write_text(json.dumps(dict(source='synthetic_test',selector='synthetic_test',bundle_id='fixture',bank_k=1,hardware='test',warmup=0,total_ms=[10])))
    monkeypatch.setattr(latency,'PROFILE_ROOT',tmp_path)
    p,_=load_profile(Path(__file__).parents[1]/'configs/line_profile.yaml');p.update(mtbf_s=0,pitch_m=100,buffer_capacity=5)
    def model(policy):return make_line(p,'config/latency_profiles/profile.json',hashlib.sha256(profile.read_bytes()).hexdigest(),seed=0,cell='inline',speed=1,policy=policy,reinspection_s=10)
    return pred,gt,model,save,rows

def run(pred,model,oracle=None):
    ledger=PartLedger();events=[]
    def sink(e):ledger.add(e);events.append(e)
    engine=ReplayEngine(model,ReplayCatalog(pred,0),oracle=oracle,event_sink=sink);metrics=engine.run_until(150)
    assert metrics['generated']==metrics['completed']+metrics['wip']
    return ledger.rows(),events,metrics

def test_ai_is_unchanged_when_gt_columns_removed_or_changed(inputs):
    pred,gt,model,save,rows=inputs;a=ReplayCatalog(pred,0).rows
    save(pred,[{k:v for k,v in r.items() if k!='is_defect'} for r in rows]);assert a==ReplayCatalog(pred,0).rows
    save(pred,[dict(r,is_defect=1-r['is_defect']) for r in rows]);assert a==ReplayCatalog(pred,0).rows

def test_policy_a_scraps_fp_while_b_recovers_with_explicit_oracle(inputs):
    pred,gt,model,*_=inputs
    a,_,_=run(pred,model('A'));b,events,_=run(pred,model('B'),ReinspectOracle(gt,seed=0))
    av=evaluate(a,gt,warmup=0,horizon=150);bv=evaluate(b,gt,warmup=0,horizon=150)
    assert av['wrongly_discarded']==1 and bv['wrongly_discarded']==0 and bv['false_positive_recovered']==1
    assert av['FP']==bv['FP']==1 and av['TP']==bv['TP']==1
    oracle=[e for e in events if e.get('source')=='reinspect_oracle'];assert len(oracle)==2
    assert all('score' not in e for e in oracle)

def test_policy_b_fails_without_gt_or_missing_labels(inputs):
    pred,gt,model,*_=inputs
    with pytest.raises(ValueError,match='requires'):ReinspectOracle(None,seed=0)
    with pytest.raises(ValueError,match='requires'):ReplayEngine(model('B'),ReplayCatalog(pred,0))
    gt.write_text('image_id,is_defect\nother,0\n')
    with pytest.raises(ValueError,match='Missing'):ReplayEngine(model('B'),ReplayCatalog(pred,0),oracle=ReinspectOracle(gt,seed=0))

def test_oracle_seed_reproducible_and_can_make_errors(inputs):
    _,gt,*_=inputs;o=ReinspectOracle(gt,seed=0,sensitivity=0,specificity=0)
    assert o.inspect(image_id='normal',part_id='p')['verdict']=='NG'
    assert o.inspect(image_id='defect',part_id='p')['verdict']=='OK'
    assert o.inspect(image_id='normal',part_id='p')==o.inspect(image_id='normal',part_id='p')

def test_parameter_source_is_required(tmp_path):
    import yaml
    p=Path(__file__).parents[1]/'configs/line_profile.yaml';data=yaml.safe_load(p.read_text());del data['parameters']['pitch_m']['source']
    q=tmp_path/'bad.yaml';q.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError,match='source'):load_profile(q)


def test_offline_queue_never_backpressures_mainline(inputs):
    pred,gt,model,save,rows=inputs
    from aria.simulation.dt.evaluation import offline_queue_metrics
    def execute(policy):
        m=model(policy)
        for c in m.components:
            if c.id=='SOURCE':c.interarrival=.1
            if c.id=='REINSPECTION':c.processing_time=60
        ledger=PartLedger();events=[]
        def sink(e):ledger.add(e);events.append(e)
        engine=ReplayEngine(m,ReplayCatalog(pred,0),oracle=ReinspectOracle(gt,seed=0) if policy=='B' else None,event_sink=sink)
        result=engine.run_until(120)
        assert result['generated']==result['completed']+result['wip']
        return engine,ledger,events,result
    a,al,ae,am=execute('A');b,bl,be,bm=execute('B')
    def ai(events):return [(e['part_id'],e['sim_time'],e['verdict']) for e in events if e.get('source')=='ai_replay' and e['type']=='inspection_result']
    assert ai(ae)==ai(be) and am['generated']==bm['generated']
    assert len(b.nodes['REINSPECTION_BUFFER']['jobs'])>1000 # exceeds old hard capacity 100
    assert bm['resources']['DIVERTER']['blocking_time']==0
    assert bm['resources']['REINSPECTION_BUFFER']['capacity'] is None
    assert bm['resources']['REINSPECTION_BUFFER']['state']=='WAITING'
    q=offline_queue_metrics(bl.rows(),warmup=0,horizon=120,service_seconds=60)
    assert q['reinspection_waiting_at_end']>1000 and q['reinspection_required_staff_rho_lt1']>500
    assert q['reinspection_unfinished_wait_age_max_s']>100


def test_source_rate_replacement_prefix_and_gt_independence(inputs):
    from aria.simulation.dt.evaluation import build_source_schedule
    pred,gt,model,save,rows=inputs
    ids=[r['image_id'] for r in rows]
    plan=build_source_schedule(gt,ids,seed=13,defect_rate=.05,count=10000)
    assert .04<plan['image_ids'].count('defect')/10000<.06
    assert plan['image_ids']==build_source_schedule(gt,list(reversed(ids)),seed=13,defect_rate=.05,count=10000)['image_ids']
    assert plan['image_ids'][:100]==build_source_schedule(gt,ids,seed=13,defect_rate=.05,count=100)['image_ids']
    assert build_source_schedule(gt,ids,seed=0,defect_rate=0,count=10)['image_ids']==['normal']*10
    assert build_source_schedule(gt,ids,seed=0,defect_rate=1,count=10)['image_ids']==['defect']*10
    c=ReplayCatalog(pred,13,schedule=plan['image_ids']);before=[c.row(i) for i in range(1,101)]
    original_events=[];original=ReplayEngine(model('A'),c,event_sink=original_events.append);original.run_until(150)
    save(pred,[{k:v for k,v in r.items() if k!='is_defect'} for r in rows]);gt.unlink()
    after=ReplayCatalog(pred,13,schedule=plan['image_ids']);assert before==[after.row(i) for i in range(1,101)]
    # Run AI after labels were removed entirely, using the already-fixed source itinerary.
    events=[];e=ReplayEngine(model('A'),after,event_sink=events.append);e.run_until(150)
    assert any(r.get('source')=='ai_replay' for r in events)
    def decisions(es):return [{k:r.get(k) for k in ['type','part_id','image_id','sim_time','score','threshold','verdict','source']} for r in es if r.get('source')=='ai_replay']
    assert decisions(original_events)==decisions(events)
