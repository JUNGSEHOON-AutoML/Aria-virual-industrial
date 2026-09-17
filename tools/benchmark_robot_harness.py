import json,time,tempfile,statistics
from pathlib import Path
from aria.simulation.des import Engine,demo_factory
from aria.simulation.des.patrol import PatrolSupervisor
from aria.simulation.des.maintenance import MaintenanceHarness
from aria.simulation.des.robot import program,sample,JOINTS
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--output',default='outputs/robot_harness_benchmark.json');output=Path(parser.parse_args().output)
results=[]
for seed in range(10):
 m=demo_factory();m.seed=seed
 c=next(c for c in m.components if c.id=='MACHINE-01');c.robot_model='m0609';c.mtbf=0
 e=Engine(m);e.run_until(12+seed*.11)
 with tempfile.TemporaryDirectory() as d:
  p=PatrolSupervisor(d);h=MaintenanceHarness();h.start(e,'MACHINE-01','gripper_jam')
  baseline=e.nodes['MACHINE-01']['total']
  for _ in range(520):
   e.run_until(e.now+.25)
   p.tick(dict(**e.snapshot(),revision=0),.25);h.tick(e,p,.25)
   t=h.tasks[-1]
   if t['state'] in ('RESTORED','ESCALATED'):break
   assert e.nodes['MACHINE-01']['total']==baseline
  restored_at=e.now;e.run_until(e.now+20)
  results.append(dict(seed=seed,state=t['state'],active_wall_tick_seconds=t['elapsed'],robot=t['robot'],production_resumed=e.nodes['MACHINE-01']['total']>baseline,trace=t['trace']))
rows,total=program(3);peak=0.
for i in range(2001):
 s=sample(3,total*i/2000)
 peak=max(peak,max(abs(v)/j['velocity'] for v,j in zip(s['velocity'],JOINTS)))
report=dict(scope='Deterministic virtual controller/harness checks; not physical robot validation',trials=results,
 summary=dict(n=len(results),restored=sum(r['state']=='RESTORED' for r in results),production_resumed=sum(r['production_resumed'] for r in results),median_active_tick_seconds=statistics.median(r['active_wall_tick_seconds'] for r in results),program_duration_seconds=total,max_sampled_velocity_fraction_of_urdf=peak,sampled_joint_states=2001))
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(report,indent=2));print(json.dumps(report['summary']))
