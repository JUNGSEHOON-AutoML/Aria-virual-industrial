"""Policy-A trial implementation. Legacy A/B CLI archived; execution is not authorized."""
import argparse,csv,gzip,hashlib,json,os,platform,shutil,time,sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from aria.simulation.dt.line import load_profile,make_line
from aria.simulation.dt.replay import ReplayCatalog,ReplayEngine
from aria.simulation.dt.reinspect_oracle import ReinspectOracle
from aria.simulation.dt.evaluation import PartLedger,evaluate,build_source_schedule,offline_queue_metrics


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):
    p=Path(p);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(x,indent=2,allow_nan=False));tmp.replace(p)
def csvwrite(p,rows):
    if not rows:return
    opener=gzip.open(p,'wt',compresslevel=6) if str(p).endswith('.gz') else Path(p).open('w')
    with opener as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def configurations(class_name='bottle'):
    """Current single-class baseline: policy A only (900 conditions)."""
    from aria.simulation.dt.plan import baseline
    return baseline(class_name)


def trial(job):
    c,base,out,profile_root,source_hash=job
    if c['policy'] != 'A':
        raise ValueError('Policy B is posthoc only; new B DES execution is disabled')
    base=Path(base);out=Path(out)
    identity=hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()[:16];target=out/'runs'/identity;target.mkdir(parents=True,exist_ok=True)
    pred=base/c['selector']/'predictions.csv';profile=base/c['selector']/'latency_profile_faiss_gpu.json';gt=base/'gt_labels.csv'
    inputs={str(x):sha(x) for x in [pred,profile,gt,ROOT/'configs/line_profile.yaml']}
    lock=dict(config=c,inputs=inputs,source_hash=source_hash)
    if (target/'complete.json').exists():
        done=json.loads((target/'complete.json').read_text())
        if done['lock']!=lock:raise ValueError('Cannot reuse changed run conditions')
        for name,h in done['hashes'].items():
            if sha(target/name)!=h:raise ValueError('Completed run artifact hash mismatch')
        return json.loads((target/'result.json').read_text())
    if (target/'events.jsonl.gz').exists():raise ValueError('Incomplete existing run preserved; use a new execution ID')
    t=time.perf_counter();params,tagged=load_profile(ROOT/'configs/line_profile.yaml')
    rel=Path(profile_root)/f"{c['selector']}.json"
    model=make_line(params,str(rel),sha(ROOT/rel),seed=c['seed'],cell=c['cell'],speed=c['speed'],policy=c['policy'],reinspection_s=c['reinspection_s'])
    catalog=ReplayCatalog(pred,c['seed'])
    import math
    if c['defect_rate']!=params['defect_rate']:raise ValueError('Run defect rate disagrees with tagged profile')
    schedule=build_source_schedule(gt,[r['image_id'] for r in catalog.rows],seed=c['seed'],defect_rate=c['defect_rate'],count=math.ceil(3600*c['speed']/params['pitch_m'])+2)
    write(target/'source_schedule.json',schedule)
    catalog=ReplayCatalog(pred,c['seed'],schedule=schedule['image_ids'])
    oracle=ReinspectOracle(gt,seed=c['seed'],sensitivity=c['sensitivity'],specificity=c['specificity']) if c['policy']=='B' else None
    ledger=PartLedger();seq=0;peak=0;holder=[]
    with gzip.open(target/'events.jsonl.gz','xt',compresslevel=6) as f:
        def sink(e):
            nonlocal seq,peak
            seq+=1;assert e['event_seq']==seq
            ledger.add(e)
            if holder and e['sim_time']>=600 and 'REINSPECTION_BUFFER' in holder[0].nodes:peak=max(peak,len(holder[0].nodes['REINSPECTION_BUFFER']['jobs']))
            f.write(json.dumps(e,separators=(',',':'),allow_nan=False)+'\n')
        engine=ReplayEngine(model,catalog,event_sink=sink,constant_median=c['latency_mode']=='constant',oracle=oracle);holder.append(engine)
        engine.run_until(600,max_events=2000000)
        before={k:{z:n[z] for z in ('area','busy','total')} for k,n in engine.nodes.items()}
        metrics=engine.run_until(3600,max_events=2000000)
    assert metrics['generated']==metrics['completed']+metrics['wip']
    assert len(ledger.parts)==metrics['generated']
    rows=ledger.rows();result=evaluate(rows,gt)
    result.update(offline_queue_metrics(rows,warmup=600,horizon=3600,service_seconds=c['reinspection_s']))
    result.update(c,run_id=identity,class_name=base.name,generated=metrics['generated'],completed=metrics['completed'],wip=metrics['wip'],events=seq,wall_seconds=time.perf_counter()-t,events_bytes=(target/'events.jsonl.gz').stat().st_size)
    result.update(reinspection_queue_mean=(engine.nodes['REINSPECTION_BUFFER']['area']-before['REINSPECTION_BUFFER']['area'])/3000 if c['policy']=='B' else 0.,
                  reinspection_queue_max=peak,reinspection_utilization=(engine.nodes['REINSPECTION']['busy']-before['REINSPECTION']['busy'])/3000 if c['policy']=='B' else 0.,
                  ai_utilization=(engine.nodes['AI-INSPECTION']['busy']-before['AI-INSPECTION']['busy'])/3000)
    for node,key in [('SOURCE','source_blocking_s'),('AI-INSPECTION','inspection_blocking_s'),('DIVERTER','diverter_blocking_s')]:result[key]=metrics['resources'][node]['blocking_time']
    write(target/'resource_metrics.json',metrics)
    csvwrite(target/'parts.csv.gz',rows);write(target/'result.json',result);write(target/'model.json',model.model_dump());write(target/'parameters.json',tagged)
    write(target/'complete.json',dict(lock=lock,hashes={name:sha(target/name) for name in ['events.jsonl.gz','parts.csv.gz','result.json','model.json','parameters.json','source_schedule.json','resource_metrics.json']}))
    return result

def main():
    raise SystemExit('Legacy benchmark CLI is INVALID for the current plan. Use tools/run_dt_matrix.py to prepare the policy-A plan; full execution awaits user confirmation.')

if __name__=='__main__':main()
