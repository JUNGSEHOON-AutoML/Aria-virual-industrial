"""Authorized policy-A matrix, gated by nine measured cap runs, then offline B views."""
import argparse
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED

from aria.simulation.dt.plan import condition_key, des_plan, posthoc_variants
from aria.simulation.dt.posthoc import reconstruct_b
from tools.benchmark_dt import write, csvwrite
from tools.measure_dt_cap import gate_decision, measured_trial
from tools.postprocess_dt import load_run
from tools.run_dt_matrix import ROOT, reusable_runs, sha


def verify_saved(folder, expected=None):
    done=json.loads((folder/'complete.json').read_text())
    if expected is not None and condition_key(done['lock']['config'])!=condition_key(expected):
        raise ValueError('Saved run condition mismatch')
    for name,digest in done['hashes'].items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha(path)!=digest:
            raise ValueError('Saved artifact mismatch: '+str(path))
    result=json.loads((folder/'result.json').read_text())
    if result['generated']!=result['completed']+result['wip']:
        raise ValueError('Part conservation failed')
    return result


def posthoc_job(job):
    config,folder,p1,out=job
    start=time.perf_counter()
    original,parts,gt=load_run(Path(folder),Path(p1))
    if condition_key(original)!=condition_key(config):raise ValueError('Posthoc source changed')
    rows=[]
    for variant in posthoc_variants(config):
        _,metrics,normalized,events=reconstruct_b(parts,gt,seed=config['seed'],
            service_seconds=variant['reinspection_s'],sensitivity=variant['sensitivity'],
            specificity=variant['specificity'])
        identity=hashlib.sha256(json.dumps(variant,sort_keys=True).encode()).hexdigest()[:16]
        target=Path(out)/'posthoc'/identity
        target.mkdir(parents=True,exist_ok=False)
        row={**variant,**metrics,**normalized,'view_id':identity,'source_A_run':str(folder),
             'simulation_policy':'A','evaluation_policy':'B_posthoc'}
        write(target/'result.json',row)
        write(target/'events.json',events)
        write(target/'complete.json',dict(config=variant,source_A_run=str(folder),
              source_complete_sha256=sha(Path(folder)/'complete.json'),
              implementation_sha256=sha(ROOT/'aria/simulation/dt/posthoc.py'),new_DES_runs=0,
              hashes={name:sha(target/name) for name in ('result.json','events.json')}))
        rows.append(row)
    return dict(rows=rows,wall_seconds=time.perf_counter()-start)


def authorize_budget(cap,free_bytes):
    prior=json.loads((cap/'cost_gate.json').read_text())
    completed=json.loads((cap/'completion.json').read_text())
    if completed['completed']!=9 or completed['new_DES_runs']!=9:
        raise ValueError('Nine cap seed0 measurements are required')
    decision=gate_decision(prior['estimated_total_seconds'],prior['estimated_remaining_bytes'],free_bytes)
    decision.update(source_gate_sha256=sha(cap/'cost_gate.json'),
                    reserve_policy='remaining bytes *1.15 +2GiB; after cleanup',
                    user_authorized='2026-10-13 explicit conditional main execution approval')
    return decision


def bounded_jobs(function,jobs,check):
    """Keep at most two jobs in flight, so a failed budget stops new submissions."""
    iterator=iter(jobs)
    with ProcessPoolExecutor(max_workers=2,mp_context=multiprocessing.get_context('spawn')) as pool:
        pending={}
        def submit():
            try:job=next(iterator)
            except StopIteration:return
            check()
            pending[pool.submit(function,job)]=job
        submit();submit()
        while pending:
            done,_=wait(pending,return_when=FIRST_COMPLETED)
            for future in done:
                job=pending.pop(future)
                yield job,future.result()
                submit()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--p1',type=Path,required=True)
    parser.add_argument('--pilot',type=Path,required=True)
    parser.add_argument('--cap-probe',type=Path,required=True)
    parser.add_argument('--posthoc-gate',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    a=parser.parse_args()
    if not a.execute:parser.error('Use --execute only for the user-authorized run')
    for k in ('p1','pilot','cap_probe','posthoc_gate','out'):setattr(a,k,getattr(a,k).resolve())
    if a.out.exists():parser.error('Output exists; preserve it and use a fresh run ID')
    pg=json.loads(a.posthoc_gate.read_text())
    if not pg['passed'] or pg['pairs']!=15:raise ValueError('15-pair posthoc verification required')
    cap_protocol=json.loads((a.cap_probe/'protocol.json').read_text())
    for name,digest in cap_protocol['source_hashes'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Measured source changed: '+name)
    for cls,digest in cap_protocol['p1_completions'].items():
        if sha(a.p1/cls/'complete.json')!=digest:raise ValueError('P1 manifest changed')
    for cls in cap_protocol['p1_completions']:
        for selector in ('coreset','ccifps','random_same_k'):
            copied=ROOT/'config/latency_profiles'/a.cap_probe.name/cls/(selector+'.json')
            if sha(copied)!=sha(a.p1/cls/selector/'latency_profile_faiss_gpu.json'):
                raise ValueError('Pinned latency copy changed')
    reuse=reusable_runs(a.pilot,a.p1)
    for c in cap_protocol['plan']:
        rid=hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()[:16]
        folder=a.cap_probe/'runs'/rid
        verify_saved(folder,c)
        reuse[condition_key(c)]={'path':str(folder),'complete_sha256':sha(folder/'complete.json')}
    if len(reuse)!=24:raise ValueError('Expected 15 historical A plus 9 current cap runs')
    conditions=des_plan()
    remaining=[c for c in conditions if condition_key(c) not in reuse]
    if len(remaining)!=2946:raise ValueError('Wrong pending DES count')
    budget=authorize_budget(a.cap_probe,shutil.disk_usage(a.out.parent).free)
    if not budget['passed']:
        print(json.dumps(dict(status='stopped_before_full_execution',**budget)),flush=True)
        return 2
    a.out.mkdir(parents=True,exist_ok=False)
    write(a.out/'cost_gate_recheck.json',budget)
    sources={**cap_protocol['source_hashes'],str(Path(__file__).relative_to(ROOT)):sha(Path(__file__)),
             'tools/postprocess_dt.py':sha(ROOT/'tools/postprocess_dt.py'),
             'tools/summarize_policy_a.py':sha(ROOT/'tools/summarize_policy_a.py')}
    source_hash=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()
    write(a.out/'protocol.json',dict(schema_version=3,sim=1,plan=conditions,workers=2,
          threads_per_worker_max=4,source_hash=source_hash,source_hashes=sources,
          full_execution_authorized=True,expected_unique_DES=2970,new_DES_total_including_probe=2955,
          expected_new_DES_here=2946,historical_A_reuse=15,cap_probe_reuse=9,
          cap_probe=str(a.cap_probe),pilot=str(a.pilot),p1=str(a.p1),expected_posthoc_views=4320,
          posthoc_parity_sha256=sha(a.posthoc_gate),horizon_s=3600,warmup_s=600))
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='4'
    index=[];results=[]
    for c in conditions:
        old=reuse.get(condition_key(c))
        if old:
            folder=Path(old['path']);r=json.loads((folder/'result.json').read_text())
            index.append(dict(config=c,path=str(folder),reused=True,complete_sha256=old['complete_sha256']))
            results.append({**r,**c,'source_run':str(folder),'reused':True})
    jobs=[(c,str(a.p1/c['class_name']),str(a.out),str(Path('config/latency_profiles')/a.cap_probe.name/c['class_name']),source_hash) for c in remaining]
    start=time.perf_counter();measurements=[]
    def progress(stage,**details):
        write(a.out/'progress.json',dict(stage=stage,elapsed_wall_seconds=time.perf_counter()-start,
              completed_DES=len(results),expected_DES=2970,**details))
    def resource_check():
        elapsed=time.perf_counter()-start
        probe_elapsed=json.loads((a.cap_probe/'completion.json').read_text())['wall_seconds']
        if elapsed+probe_elapsed>8*3600:raise RuntimeError('8-hour runtime limit reached')
        if shutil.disk_usage(a.out).free<2*1024**3:raise RuntimeError('Disk reserve fell below 2 GiB')
    try:
        progress('DES_A')
        for job,measurement in bounded_jobs(measured_trial,jobs,resource_check):
            c=job[0]
            r=measurement['result'];folder=a.out/'runs'/r['run_id']
            index.append(dict(config=c,path=str(folder),reused=False,complete_sha256=sha(folder/'complete.json')))
            results.append({**r,'source_run':str(folder),'reused':False})
            measurements.append({k:v for k,v in measurement.items() if k!='result'})
            if len(measurements)%15==0 or len(results)==2970:
                write(a.out/'run_index.json',index);csvwrite(a.out/'scenario_results.csv',results)
                write(a.out/'worker_measurements.json',measurements)
                progress('DES_A',new_DES_here=len(measurements))
                print(f'A DES {len(results)}/2970; new {len(measurements)}/2946; elapsed {time.perf_counter()-start:.1f}s',flush=True)
        if len(results)!=2970:raise ValueError('Incomplete A inventory')
        des_wall=time.perf_counter()-start
        postjobs=[(r['config'],r['path'],str(a.p1),str(a.out)) for r in index if r['config']['scope']=='main']
        postrows=[];poststart=time.perf_counter()
        for n,(_,batch) in enumerate(bounded_jobs(posthoc_job,postjobs,resource_check),1):
            postrows.extend(batch['rows'])
            if n%30==0 or n==len(postjobs):
                csvwrite(a.out/'posthoc_results.csv',postrows)
                progress('posthoc_B',completed_posthoc_views=len(postrows),expected_posthoc_views=4320)
                print(f'B posthoc {len(postrows)}/4320',flush=True)
        if len(postrows)!=4320:raise ValueError('Incomplete B inventory')
        write(a.out/'completion.json',dict(completed_DES=2970,new_DES_here=2946,
              new_DES_including_cap_probe=2955,historical_A_reuse=15,posthoc_views=4320,actual_B_DES=0,
              des_wall_seconds=des_wall,posthoc_wall_seconds=time.perf_counter()-poststart,
              wall_seconds=time.perf_counter()-start,full_matrix_complete=True))
        from tools.summarize_policy_a import summarize
        summarize(a.out)
        progress('complete',completed_posthoc_views=4320)
        print('COMPLETE: A inventory 2970, new A 2955 including probe, B posthoc 4320; REPORT.md written',flush=True)
    except BaseException as exc:
        progress('failed',error=repr(exc))
        raise
    return 0


if __name__=='__main__':raise SystemExit(main())
