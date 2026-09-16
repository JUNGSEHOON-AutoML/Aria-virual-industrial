"""Reproduce: PYTHONPATH=. python tools/benchmark_factory.py --out /tmp/aria-benchmark-results"""
import argparse,json,time,statistics,platform,tempfile,csv
from pathlib import Path
from aria.simulation.des import Engine,demo_factory
from aria.simulation.des.model import FactoryModel
from aria.simulation.des.patrol import PatrolSupervisor

def stats(xs):
 m=statistics.mean(xs);half=2.045*statistics.stdev(xs)/(len(xs)**.5) if len(xs)>1 else 0
 return dict(n=len(xs),mean=m,min=min(xs),max=max(xs),ci95=[m-half,m+half])

def run(out):
 out.mkdir(parents=True,exist_ok=True);rows=[]
 for seed in range(30):
  for variant in ['baseline','machine_capacity_2','machine_time_2s','buffer_capacity_20']:
   model=demo_factory();model.seed=seed;model.simulation.duration=3600
   for c in model.components:
    if c.id=='MACHINE-01' and variant=='machine_capacity_2':c.capacity=2
    if c.id=='MACHINE-01' and variant=='machine_time_2s':c.processing_time=2
    if c.id=='BUFFER-01' and variant=='buffer_capacity_20':c.capacity=20
   e=Engine(model);t=time.perf_counter();m=e.run_until(3600);wall=time.perf_counter()-t
   assert m['generated']==m['completed']+m['wip']
   assert all(r['occupancy']<=r['capacity'] for r in m['resources'].values())
   rows.append(dict(seed=seed,variant=variant,throughput=m['throughput_per_hour'],good_throughput=m['good_throughput_per_hour'],lead_time=m['lead_time'],final_wip=m['wip'],avg_wip=sum(r['avg_queue'] for r in m['resources'].values()),machine_utilization=m['resources']['MACHINE-01']['utilization'],buffer_wait=m['resources']['BUFFER-01']['waiting_time'],wall_seconds=wall,events=m['events_processed']))
 print("Production runs complete: 120",flush=True)
 summary={}
 for variant in sorted(set(r['variant'] for r in rows)):
  rr=[r for r in rows if r['variant']==variant]
  summary[variant]={k:stats([r[k] for r in rr]) for k in rr[0] if k not in ('seed','variant')}
  changes=[100*(r['throughput']/next(b['throughput'] for b in rows if b['seed']==r['seed'] and b['variant']=='baseline')-1) for r in rr]
  summary[variant]['paired_throughput_change_percent']=stats(changes)
 # Analytic no-failure, no-defect bottleneck checks; empty-start transient included.
 analytic=[]
 for capacity,theory in [(1,1200),(2,1800)]:
  model=demo_factory();model.simulation.duration=3600
  for c in model.components:
   c.mtbf=0;c.defect_rate=0
   if c.id=='MACHINE-01':c.capacity=capacity
  e=Engine(model);a=e.run_until(3600);b=Engine(model).run_until(3600)
  assert a==b
  analytic.append(dict(capacity=capacity,theoretical_steady_rate=theory,observed=a['throughput_per_hour'],relative_error_percent=100*(a['throughput_per_hour']/theory-1),deterministic_replay=True))
 # Fault latency across 30 different initial patrol phases; simulated wall-time tick .25s.
 patrol=[]
 for trial in range(30):
  model=demo_factory()
  for c in model.components:c.mtbf=0
  e=Engine(model)
  with tempfile.TemporaryDirectory() as directory:
   p=PatrolSupervisor(directory)
   snap=lambda:dict(**e.snapshot(),revision=0)
   for _ in range(trial*4):p.tick(snap(),.25)
   false_down=sum(r['kind']=='equipment_down' for r in p.reports)
   e.schedule(0,'failure','MACHINE-01',epoch=60);e.run_until(0)
   detection=None;verify=None;recovery=None;t=0
   while t<61:
    t+=.25;e.run_until(t);state=p.tick(snap(),.25)
    r=next((r for r in state['reports'] if r['kind']=='equipment_down'),None)
    if r and detection is None:detection=t
    if r and r['verified_by'] and verify is None:verify=t
    if r and r['status']=='recovered' and recovery is None:recovery=t-60
   patrol.append(dict(trial=trial,initial_phase_seconds=trial,detection_seconds=detection,verification_seconds=verify,recovery_lag_seconds=recovery,false_down_before_injection=false_down))
 print('Patrol trials complete: 30',flush=True)
 # Scaling: three seeds per size, the service default 10-second budget.
 scaling=[]
 for count in (1,3,10):
  for seed in range(3):
   base=demo_factory().model_dump();components=[];edges=[]
   for line in range(count):
    for c in base['components']:
     c=dict(c);c['id']=f'L{line}-'+c['id'];c['position']=[c['position'][0],0,c['position'][2]+line*12];components.append(c)
    for edge in base['connections']:edges.append(dict(edge,source=f'L{line}-'+edge['source'],target=f'L{line}-'+edge['target']))
   model=FactoryModel.model_validate(dict(base,seed=seed,components=components,connections=edges))
   t=time.perf_counter();e=Engine(model);finished=True
   try:m=e.run_until(3600,deadline=t+10)
   except ValueError as exc:
    if 'wall-time budget' not in str(exc):raise
    finished=False;m=e.metrics()
   wall=time.perf_counter()-t
   assert m['generated']==m['completed']+m['wip']
   scaling.append(dict(components=count*10,seed=seed,completed=finished,simulated_seconds=m['time'],wall_seconds=wall,events=m['events_processed'],simulated_seconds_per_wall_second=m['time']/wall))
   print(f'Scaling {count*10} components seed {seed}: completed={finished}, simulated={m["time"]:.1f}s',flush=True)
 result=dict(base_model=demo_factory().model_dump(),protocol=dict(seeds=list(range(30)),horizon_seconds=3600,warmup_seconds=0,inspection='mock',ci='Student t critical 2.045, 29 df; paired relative changes',patrol_clock='accelerated deterministic .25 s ticks; not measured real wall-clock latency',scaling_deadline_seconds=10,scaling_seeds=[0,1,2],scaling='independent lines, not arbitrary connected factories'),environment=dict(python=platform.python_version(),platform=platform.platform(),cpu=next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),'')),summary=summary,raw=rows,analytic=analytic,patrol=patrol,scaling=scaling)
 (out/'factory_benchmark.json').write_text(json.dumps(result,indent=2))
 with (out/'factory_benchmark.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
 print(json.dumps(dict(summary=summary,analytic=analytic,patrol_verified=sum(r['verification_seconds'] is not None for r in patrol),patrol_verification=stats([r['verification_seconds'] for r in patrol if r['verification_seconds'] is not None]),scaling={n:statistics.median(r['wall_seconds'] for r in scaling if r['components']==n) for n in (10,30,100)}),indent=2))
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=Path('/tmp/aria-benchmark-results'));run(parser.parse_args().out)
