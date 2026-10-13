"""Verified saved-A replay and evaluator-backed B views. No DES execution."""
import csv,gzip,hashlib,json,os,re,time
from functools import lru_cache
from pathlib import Path
from aria.simulation.dt.posthoc import reconstruct_b
from tools.verify_dt_posthoc import readparts
ROOT=Path(__file__).resolve().parents[2]
PILOT=Path(os.environ.get('CNOTTA_PILOT',ROOT/'docs/validation/aria_dt_20261013_03/des_pilot30')).resolve()
P1=Path(os.environ.get('CNOTTA_P1',ROOT/'docs/validation/aria_dt_20261012_02/p1_verified')).resolve()
FULL=Path(os.environ.get('CNOTTA_RESULTS',ROOT/'docs/validation/aria_dt_full_policy_a_20261013')).resolve()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
@lru_cache(maxsize=1)
def _campus_completed(root, bucket):
 # The completion marker is written after the artifacts. Reading it never
 # starts/controls a run and does not advertise the unfinished full study.
 rows=[]
 for done in sorted((root/'runs').glob('*/complete.json')):
  try:
   c=json.loads(done.read_text())['lock']['config']
   if c['policy']=='A' and c['class_name'] in ('bottle','screw','carpet') and c['selector'] in ('coreset','ccifps','random_same_k') and c['seed']==0 and c['cell']=='inline' and c['speed']==.5 and c['latency_mode']=='profile':rows.append(done)
  except (OSError,ValueError,KeyError):continue
 return tuple(rows)
def catalog():
 rows=[]
 sources=[(PILOT,done) for done in sorted((PILOT/'runs').glob('*/complete.json'))]
 if full_ready():sources += [(FULL,Path(entry['path'])/'complete.json') for entry in json.loads((FULL/'run_index.json').read_text())]
 else:sources += [(FULL,done) for done in _campus_completed(FULL,int(time.monotonic()//15))]
 seen=set()
 for root,done in sources:
  if done.parent.name in seen:continue
  seen.add(done.parent.name)
  if True:
   d=json.loads(done.read_text());c=d['lock']['config']
   if c['policy']!='A':continue
   rows.append({'run_id':done.parent.name,**{k:c[k] for k in ['class_name','selector','cell','speed','latency_mode','seed']},'complete_hash':sha(done),'source':'pilot' if root==PILOT else ('full' if full_ready() else 'completed-run'),'_path':done.parent})
 return rows
@lru_cache(maxsize=12)
def load(run_id):
 if not re.fullmatch(r'[a-f0-9]{16}',run_id):raise KeyError('Unknown run')
 row=next((r for r in catalog() if r['run_id']==run_id),None)
 if not row:raise KeyError('Unknown run')
 folder=row['_path'];done=json.loads((folder/'complete.json').read_text());cfg=done['lock']['config']
 for name,digest in done['hashes'].items():
  path=(folder/name).resolve()
  if not path.is_relative_to(folder) or sha(path)!=digest:raise ValueError('Saved artifact integrity failure: '+name)
 gt=P1/cfg['class_name']/'gt_labels.csv';pred=P1/cfg['class_name']/cfg['selector']/'predictions.csv'
 for path in (gt,pred):
  expected=next((v for k,v in done['lock']['inputs'].items() if k.endswith('/'+str(path.relative_to(P1)))),None)
  if expected!=sha(path):raise ValueError('Saved input integrity failure: '+path.name)
 with pred.open() as f:predictions={r['image_id']:{k:r[k] for k in ('score','threshold','verdict','image_sha256')} for r in csv.DictReader(f)}
 parts=readparts(folder/'parts.csv.gz');entries={};transitions=[];latencies={}
 with gzip.open(folder/'events.jsonl.gz','rt') as f:
  for line in f:
   e=json.loads(line);time=e['sim_time'];pid=e.get('part_id')
   if e['type']=='part_move':entries.setdefault(pid,[]).append({'time':time,'component':e['component']})
   elif e['type']=='inspection_result' and e.get('source')!='reinspect_oracle':latencies[pid]=e.get('latency_ms',{}).get('total')
   elif e['type']=='component_state':transitions.append({'time':time,'component':e['component'],'state':e['state']})
 bp,_,_,_=reconstruct_b(parts,gt,seed=cfg['seed']);by_b={p['part_id']:p for p in bp};public=[]
 for p in parts:
  q=predictions[p['image_id']];b=by_b[p['part_id']]
  public.append({'part_id':p['part_id'],'born':p['born'],'inspection_time':p['inspection_time'],'mainline_exit_time':p['mainline_exit_time'],'exit_time':p['exit_time'],'verdict':p['ai_verdict'],'route':p['route'],'score':float(q['score']),'threshold':float(q['threshold']),'latency_ms':latencies.get(p['part_id']),'entries':entries.get(p['part_id'],[]),'reinspection_queue_enter':b['reinspection_queue_enter'],'reinspection_start':b['reinspection_start'],'reinspection_time':b['reinspection_time'],'reinspection_verdict':b['reinspection_verdict']})
 delta={}
 for b in bp:
  start=b['reinspection_start'];arrival=b['reinspection_queue_enter']
  if arrival is not None and (start is None or start>arrival):
   delta[arrival]=delta.get(arrival,0)+1
   if start is not None:delta[start]=delta.get(start,0)-1
 count=0;queue=[{'time':0.,'count':0}]
 for t,d in sorted(delta.items()):count+=d;queue.append({'time':t,'count':count})
 return {'config':cfg,'parts':parts,'public':public,'gt':gt,'transitions':transitions,'queue':queue,'complete_hash':row['complete_hash']}
def queue_at(run,t):
 result=0
 for q in run['queue']:
  if q['time']>t:break
  result=q['count']
 return result
@lru_cache(maxsize=96)
def kpi(run_id,t):
 run=load(run_id)
 if t<=0:return {'time':0.,'throughput_per_hour':None,'gt_quality':None,'false_positives_per_1000':None,'queue_count':0,'resources':[],'delta':None,'assumed':{'human_service_seconds':30,'human_sensitivity':1,'human_specificity':1,'servers':1}}
 warmup=600. if t>600 else 0.
 _,metrics,norm,_=reconstruct_b(run['parts'],run['gt'],seed=run['config']['seed'],warmup=warmup,horizon=t)
 resources=[]
 for component in sorted({e['component'] for e in run['transitions']}):
  events=[e for e in run['transitions'] if e['component']==component and e['time']<=t];busy=0.
  for i,e in enumerate(events):
   end=events[i+1]['time'] if i+1<len(events) else t
   if e['state']=='PROCESSING':busy+=max(0,end-max(warmup,e['time']))
  resources.append({'id':component,'state':events[-1]['state'] if events else None,'utilization':busy/(t-warmup)})
 return {'time':t,'warmup':warmup,'throughput_per_hour':metrics['throughput_per_hour'],'gt_quality':metrics['gt_quality'],'false_positives_per_1000':norm['false_positives_per_1000'],'person_hours_per_1000':norm['person_hours_per_1000'],'required_staff':norm['required_staff_rho_lt1'],'hold_ratio':metrics['hold_ratio'],'queue_count':queue_at(run,t),'resources':resources,'delta':None,'policy':'B posthoc from saved A','assumed':{'human_service_seconds':30,'human_sensitivity':1,'human_specificity':1,'servers':1}}

# A baseline is comparable only with all non-model run conditions matched.
_base_kpi = kpi
@lru_cache(maxsize=96)
def kpi(run_id,t):
 result=dict(_base_kpi(run_id,t));cfg=load(run_id)['config']
 baseline=next((r for r in catalog() if r['selector']=='coreset' and all(r[k]==cfg[k] for k in ('class_name','cell','speed','latency_mode','seed'))),None)
 if baseline:
  reference=_base_kpi(baseline['run_id'],t)
  result['delta']={k:result[k]-reference[k] if result[k] is not None and reference[k] is not None else None for k in ('throughput_per_hour','gt_quality','false_positives_per_1000')}
  result['baseline_run_id']=baseline['run_id']
 return result

def full_ready():
 required=('completion.json','verification.json','summary_ci95.csv','REPORT.md','run_index.json')
 if not all((FULL/f).is_file() for f in required):return False
 try:
  c=json.loads((FULL/'completion.json').read_text());v=json.loads((FULL/'verification.json').read_text())
  return c.get('completed_DES')==2970 and c.get('posthoc_views')==4320 and v.get('passed') is True and v.get('all_raw_hashes_verified') is True and v.get('all_groups_30_unique_seeds') is True
 except (ValueError,OSError):return False

def summary_data():
 if not full_ready():raise FileNotFoundError('실험 진행 중')
 with (FULL/'summary_ci95.csv').open() as f:rows=list(csv.DictReader(f))
 representative=[r for r in rows if r['scope']=='main' and r['cell']=='inline' and float(r['speed'])==.5 and r['latency_mode']=='profile']
 report=(FULL/'REPORT.md').read_text();tables=[line.split('|')[1:-1] for line in report.splitlines() if line.startswith('|') and len(line.split('|'))==9]
 validated=0
 for row in representative:
  if row['metric']!='throughput_per_hour':continue
  key=[row['class_name'],row['selector'],row['policy']];match=next((t for t in tables if t[:3]==key),None)
  others={r['metric']:r for r in representative if [r['class_name'],r['selector'],r['policy']]==key}
  expected=[*key,f"{float(row['mean']):.2f}",f"[{float(row['ci95_low']):.2f}, {float(row['ci95_high']):.2f}]",f"{float(others['hold_ratio']['mean']):.6f}",f"{float(others['person_hours_per_1000']['mean']):.4f}" if others['person_hours_per_1000']['mean'] else '해당 없음']
  if match!=expected:raise ValueError('Summary differs from REPORT table')
  validated+=1
 if not validated:raise ValueError('REPORT has no verified representative rows')
 return {'rows':rows,'report_rows_verified':validated,'report_sha256':sha(FULL/'REPORT.md'),'complete_sha256':sha(FULL/'completion.json')}
