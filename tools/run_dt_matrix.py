"""Three-class plan: pilot30 -> <=8h gate -> 7020 fixed DES conditions."""
import argparse,json,os,shutil,time,sys,hashlib,multiprocessing
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from benchmark_dt import configurations,trial,sha,write,csvwrite,ROOT
CLASSES=['bottle','screw','carpet']

def prepare(p1,out):
    sources=[ROOT/'configs/line_profile.yaml']+list((ROOT/'aria/simulation/dt').glob('*.py'))+[ROOT/'tools/benchmark_dt.py',Path(__file__),ROOT/'aria/simulation/des/engine.py',ROOT/'aria/simulation/des/latency.py',ROOT/'aria/simulation/des/model.py']
    hashes={str(p.relative_to(ROOT)):sha(p) for p in sources};source_hash=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    profiles={};completions={}
    for cls in CLASSES:
        base=p1/cls;c=json.loads((base/'complete.json').read_text());completions[cls]=sha(base/'complete.json')
        for name,h in c['files'].items():
            if sha(base/name)!=h:raise ValueError('P1 artifact changed: '+str(base/name))
        rel=Path('config/latency_profiles')/out.name/cls; (ROOT/rel).mkdir(parents=True,exist_ok=True)
        for sel in ['coreset','ccifps','random_same_k']:
            src=base/sel/'latency_profile_faiss_gpu.json';dest=ROOT/rel/(sel+'.json')
            if dest.exists() and sha(dest)!=sha(src):raise ValueError('Profile hash mismatch')
            if not dest.exists():shutil.copyfile(src,dest)
            gate=json.loads((base/sel/'search_regression_faiss_gpu.json').read_text())
            if not gate['passed']:raise ValueError('Exact search gate not passed')
        profiles[cls]=str(rel)
    return source_hash,hashes,profiles,completions

def plans(pilot=False):
    result=[]
    for ci,cls in enumerate(CLASSES):
        configs=configurations()
        if pilot:
            subset=[]
            for i,(cell,speed) in enumerate([('robot',.5),('inline',.25),('inline',.5),('inline',.75),('inline',1.)]):
                for pi,policy in enumerate(['A','B']):
                    selector=['coreset','ccifps','random_same_k'][(i+ci)%3];mode=['profile','constant'][i%2]
                    c=next(dict(c) for c in configs if c['scope']=='main' and c['selector']==selector and c['seed']==0 and c['cell']==cell and c['speed']==speed and c['policy']==policy and c['latency_mode']==mode);c['scope']='pilot30';subset.append(c)
            configs=subset
        result.extend([dict(c,class_name=cls) for c in configs])
    assert len(result)==(30 if pilot else 7020)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--p1',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--pilot',action='store_true');p.add_argument('--pilot-results',type=Path);p.add_argument('--workers',type=int,default=2);a=p.parse_args()
    if not a.pilot:raise ValueError('Full 7020 run requires new user confirmation after revised P3 pilot; disabled')
    if a.workers!=2:raise ValueError('Fixed two independent CPU workers for comparable cost estimate')
    a.out.mkdir(parents=True,exist_ok=True);start=time.perf_counter();source_hash,hashes,profiles,complete=prepare(a.p1,a.out)
    configs=plans(a.pilot)
    if not a.pilot:
        gate=json.loads((a.pilot_results/'cost_gate.json').read_text())
        if not gate['time_gate_passed'] or gate['estimated_wall_seconds']>28800:raise ValueError('8-hour gate failed; full run prohibited')
        if gate['source_hash']!=source_hash or gate['p1_completions']!=complete:raise ValueError('Pilot source/input changed')
        if shutil.disk_usage(a.out).free<gate['estimated_storage_bytes']*1.15+2*1024**3:raise ValueError('Insufficient disk with reserve; do not run')
    write(a.out/'protocol.json',dict(classes=CLASSES,bottle_role='control; expected small model differences; fixed before process results',expected_runs=len(configs),main_runs=5400,sensitivity_runs=1620,workers=2,source_hash=source_hash,source_hashes=hashes,p1_completions=complete,warmup_seconds=600,horizon_seconds=3600,plan=configs,sim=1,full_execution_authorized=False,requires_user_confirmation_after_pilot=True,source_defect_rate=0.05,source_defect_rate_provenance='assumed',reinspection='offline unbounded FIFO; no mainline backpressure',events_format='lossless gzip JSONL; event order retained'))
    jobs=[(c,str((a.p1/c['class_name']).resolve()),str(a.out.resolve()),profiles[c['class_name']],source_hash) for c in configs];results=[]
    with ProcessPoolExecutor(max_workers=2,mp_context=multiprocessing.get_context('spawn')) as pool:
        for r in pool.map(trial,jobs,chunksize=1):
            results.append(r)
            if len(results)%30==0:
                csvwrite(a.out/'scenario_results.csv',results);print(f'{len(results)}/{len(configs)} complete, wall {time.perf_counter()-start:.1f}s',flush=True)
    wall=time.perf_counter()-start
    write(a.out/'completion.json',dict(completed=len(results),expected=len(configs),wall_seconds=wall,total_worker_seconds=sum(r['wall_seconds'] for r in results),events_bytes=sum(r['events_bytes'] for r in results)))
    if a.pilot:
        strata={(r['class_name'],r['cell'],r['speed'],r['policy']):r for r in results};seconds=0.;storage=0.
        for c in plans(False):
            r=strata[c['class_name'],c['cell'],c['speed'],c['policy']]
            factor=max(1.,30/c['reinspection_s']) if c['policy']=='B' else 1.
            seconds+=r['wall_seconds']*factor
            folder=a.out/'runs'/r['run_id'];storage+=sum(f.stat().st_size for f in folder.iterdir() if f.is_file())*factor
        estimate=seconds/2*1.25
        write(a.out/'cost_gate.json',dict(time_gate_passed=estimate<=28800,estimated_wall_seconds=estimate,estimated_hours=estimate/3600,estimated_storage_bytes=storage,observed_pilot_wall_seconds=wall,pilot_runs=30,full_runs=7020,workers=2,method='class/cell/speed/policy stratified; B time10 scales by3; 25% time overhead; storage reserve checked before launch',source_hash=source_hash,p1_completions=complete))
if __name__=='__main__':main()
