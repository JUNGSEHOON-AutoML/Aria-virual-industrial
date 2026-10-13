"""Validate posthoc B against 15 saved actual-B runs; do not launch any DES."""
import argparse,csv,gzip,hashlib,json,sys,time
from pathlib import Path
from dt_posthoc_reinspection import reconstruct_b
ROOT=Path(__file__).resolve().parents[1]
NUMERIC_PART_FIELDS=['born','inspection_time','reinspection_time','exit_time','mainline_exit_time','reinspection_queue_enter','reinspection_start']
def readparts(p):
    with gzip.open(p,'rt') as f:rows=list(csv.DictReader(f))
    for r in rows:
        for k in NUMERIC_PART_FIELDS:r[k]=float(r[k]) if r[k] else None
        for k in ('ai_verdict','reinspection_verdict','route'):r[k]=r[k] or None
    return rows
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def csvwrite(p,rows):
    with p.open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
    p=argparse.ArgumentParser();p.add_argument('--pilot',type=Path,required=True);p.add_argument('--p1',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    protocol=json.loads((a.pilot/'protocol.json').read_text());pairs={}
    for c in protocol['plan']:
        rid=hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()[:16];folder=a.pilot/'runs'/rid
        key=tuple(c[k] for k in ('class_name','selector','cell','speed','latency_mode','seed'));pairs.setdefault(key,{})[c['policy']]=(folder,c)
    assert len(pairs)==15
    comparisons=[];normalized=[];runchecks=[];start=time.perf_counter()
    for key,pair in pairs.items():
        af,c=pair['A'];bf,_=pair['B']
        for folder in (af,bf):
            complete=json.loads((folder/'complete.json').read_text())
            for name in ('parts.csv.gz','result.json','resource_metrics.json','source_schedule.json'):assert sha(folder/name)==complete['hashes'][name]
        t=time.perf_counter();parts=readparts(af/'parts.csv.gz');read_s=time.perf_counter()-t
        t=time.perf_counter();bp,metrics,norm,events=reconstruct_b(parts,a.p1/c['class_name']/'gt_labels.csv',seed=c['seed']);compute_s=time.perf_counter()-t
        actual=json.loads((bf/'result.json').read_text());saved=readparts(bf/'parts.csv.gz');byid={p['part_id']:p for p in saved};identity=dict(zip(('class_name','selector','cell','speed','latency_mode','seed'),key))
        bad=[];max_part_time_error=0.
        for p in bp:
            q=byid[p['part_id']]
            for k in NUMERIC_PART_FIELDS+['ai_verdict','reinspection_verdict','route']:
                x,y=p[k],q[k]
                if isinstance(x,(int,float)) and isinstance(y,(int,float)):
                    err=abs(x-y);max_part_time_error=max(max_part_time_error,err)
                    if err>2e-6:bad.append((p['part_id'],k,x,y))
                elif x!=y:bad.append((p['part_id'],k,x,y))
        for metric,x in metrics.items():
            if metric not in actual or isinstance(x,str):continue
            y=actual[metric];err=abs(x-y) if isinstance(x,(int,float)) and isinstance(y,(int,float)) else None
            tol=2e-6 if isinstance(x,float) else 0
            passed=(err<=tol) if err is not None else x==y
            comparisons.append(dict(**identity,metric=metric,posthoc=x,actual_B=y,absolute_error=err,tolerance=tol,passed=passed))
        normalized.append(dict(**identity,**norm))
        f=a.out/('posthoc_'+af.name+'.json');f.write_text(json.dumps(dict(inputs=dict(A_run=str(af),B_reference=str(bf)),parameters=dict(servers=1,service_seconds=30,sensitivity=1,specificity=1,source='assumed'),metrics=metrics,normalized=norm,events=events),indent=2,allow_nan=False))
        runchecks.append(dict(**identity,A_run=af.name,B_run=bf.name,part_count=len(parts),read_seconds=read_s,compute_seconds=compute_s,posthoc_output_bytes=f.stat().st_size,part_comparison_passed=not bad,part_mismatches=bad[:10],max_part_time_error_s=max_part_time_error))
    csvwrite(a.out/'metric_comparisons.csv',comparisons);csvwrite(a.out/'normalized_reinspection.csv',normalized)
    result=dict(passed=all(r['passed'] for r in comparisons) and all(r['part_comparison_passed'] for r in runchecks),pairs=15,metric_checks=len(comparisons),failed_metrics=[r for r in comparisons if not r['passed']],part_checks=runchecks,wall_seconds=time.perf_counter()-start,timestamp_precision_s=1e-6,float_tolerance=2e-6,new_DES_runs=0)
    (a.out/'gate.json').write_text(json.dumps(result,indent=2,allow_nan=False));print(json.dumps({k:v for k,v in result.items() if k!='part_checks'}))
    raise SystemExit(0 if result['passed'] else 1)
if __name__=='__main__':main()
