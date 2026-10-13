"""Audit revised P3 pilot artifacts without running any additional simulation."""
import argparse,csv,gzip,hashlib,json,math
from collections import defaultdict
from pathlib import Path
from aria.simulation.dt.evaluation import evaluate
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def ai_trace(p):
 h=hashlib.sha256();n=0
 with gzip.open(p,'rt') as f:
  for line in f:
   e=json.loads(line)
   if e['type']=='inspection_result' and e.get('source')=='ai_replay':
    h.update(json.dumps({k:e.get(k) for k in ['part_id','image_id','sim_time','verdict','score','threshold']},sort_keys=True).encode());n+=1
 return dict(count=n,sha256=h.hexdigest())
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--p1',type=Path,required=True);a=p.parse_args();out=a.out
 protocol=json.loads((out/'protocol.json').read_text());assert len(protocol['plan'])==30
 for name,h in protocol['source_hashes'].items():assert sha(ROOT/name)==h,'Changed runtime source '+name
 results=[];pairs=defaultdict(dict);sourcefiles={}
 for c in protocol['plan']:
  rid=hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()[:16];folder=out/'runs'/rid;complete=json.loads((folder/'complete.json').read_text())
  assert complete['lock']['config']==c
  for name,h in complete['hashes'].items():assert sha(folder/name)==h,(rid,name)
  r=json.loads((folder/'result.json').read_text());assert r['generated']==r['completed']+r['wip'];assert r['diverter_blocking_s']==0
  with gzip.open(folder/'parts.csv.gz','rt') as f:parts=list(csv.DictReader(f))
  for row in parts:
   for k in ['born','inspection_time','reinspection_time','exit_time','mainline_exit_time','reinspection_queue_enter','reinspection_start']:row[k]=float(row[k]) if row[k] else None
  pred={r['image_id']:r for r in csv.DictReader((a.p1/c['class_name']/c['selector']/'predictions.csv').open())}
  expected=[]
  for row in parts:
   if row['ai_verdict'] in ('OK','NG'):assert row['ai_verdict']==pred[row['image_id']]['verdict']
   expected.append(dict(row,ai_verdict=pred[row['image_id']]['verdict'] if row['ai_verdict'] in ('OK','NG') else row['ai_verdict']))
  recalc=evaluate(expected,a.p1/c['class_name']/'gt_labels.csv')
  assert all(recalc[k]==r[k] for k in ['TP','TN','FP','FN','mainline_departures'])
  trace=ai_trace(folder/'events.jsonl.gz');key=tuple(c[k] for k in ['class_name','selector','cell','speed','latency_mode','seed'])
  pairs[key][c['policy']]=(r,trace,sha(folder/'source_schedule.json'));results.append(r)
 checks=[]
 for key,pair in pairs.items():
  ar,at,asrc=pair['A'];br,bt,bsrc=pair['B'];assert at==bt and asrc==bsrc
  assert ar['generated']==br['generated'] and ar['mainline_departures']==br['mainline_departures']
  for k in ['source_blocking_s','inspection_blocking_s']:assert abs(ar[k]-br[k])<1e-6
  checks.append(dict(zip(['class_name','selector','cell','speed','latency_mode','seed'],key),ai_event_count=at['count'],ai_trace_sha256=at['sha256'],source_schedule_sha256=asrc,mainline_throughput_A=ar['mainline_throughput_per_hour'],mainline_throughput_B=br['mainline_throughput_per_hour'],diverter_blocking_A=ar['diverter_blocking_s'],diverter_blocking_B=br['diverter_blocking_s'],B_queue_end=br['reinspection_waiting_at_end'],B_queue_mean=br['reinspection_queue_mean'],B_residence_completed_mean_s=br['reinspection_residence_completed_mean_s'],B_unfinished_wait_age_mean_s=br['reinspection_unfinished_wait_age_mean_s'],B_utilization=br['reinspection_utilization'],B_required_staff=br['reinspection_required_staff_rho_lt1'],observed_defect_rate=br['source_defect_fraction_observed']))
 with (out/'paired_nonblocking_checks.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(checks[0]));w.writeheader();w.writerows(checks)
 result=dict(passed=True,verified_runs=len(results),paired_checks=len(checks),identical_AI_traces=True,identical_source_schedules=True,no_additional_mainline_blocking=True,all_diverter_blocking_seconds=0,confusion_matches_saved_predictions=True,conservation=True,source_hashes_unchanged=True,assumed_defect_rate=.05,observed_defect_rate_min=min(r['source_defect_fraction_observed'] for r in results),observed_defect_rate_max=max(r['source_defect_fraction_observed'] for r in results),full_execution_authorized=False)
 (out/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
