"""S1-S3 evidence checks over verified saved runs and CPU browser capture."""
import copy,hashlib,json,math
from pathlib import Path
from aria.dashboard import stations,store,transfer
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'docs/autopilot/local/stations'
def main():
 browser=json.loads((OUT/'browser.json').read_text());runs=[]
 for r in store.catalog():
  if not(r['cell']=='inline' and r['speed']==.5 and r['latency_mode']=='profile' and r['seed']==0):continue
  data=stations.load(r['run_id'],stations.key());original=store.load(r['run_id']);events=data['source_events'];tasks=data['transfer_tasks']
  by_id={e['id']:e for e in events};assert len(events)==len(tasks)==len({t['source_event'] for t in tasks})
  assert all(t['object_id']==by_id[t['source_event']]['object_id'] and t['source_time']==by_id[t['source_event']]['time'] for t in tasks)
  assert all(t['start']>=t['source_time'] for t in tasks)
  cumulative=0
  for row in data['equipment']:
   assert abs(row['distance']-cumulative)<1e-8
   assert row['lamp']==('FAULT' if row['state']=='DOWN' else 'RUN' if row['state']=='PROCESSING' else 'STOP')
   cumulative+=max(0,row['end']-row['start'])*row['speed']
  metric=dict(run_id=r['run_id'],class_name=r['class_name'],selector=r['selector'],source_events=len(events),transfer_tasks=len(tasks),belt_distance_m=cumulative)
  if r['class_name']=='screw':
   parts=[p for p in data['parts'] if p['arrival'] is not None];overlap=0;minimum=None;concurrent_pairs=0
   # Check all concurrently active angular intervals. Trajectories are affine
   # in angle, so a crossing or an endpoint minimizes angular separation.
   for i,a in enumerate(parts):
    for b in parts[i+1:]:
     if b['trigger']>a['arrival']:break
     lo=max(a['trigger'],b['trigger']);hi=min(a['arrival'],b['arrival'])
     if hi<=lo:continue
     concurrent_pairs+=1
     f=lambda p,t:(t-p['trigger'])/(p['arrival']-p['trigger'])
     dl=f(a,lo)-f(b,lo);dh=f(a,hi)-f(b,hi)
     sep=0 if dl*dh<=0 else 2*data['geometry']['screw']['radius_m']*math.sin(math.pi*min(abs(dl),abs(dh))/2)
     minimum=sep if minimum is None else min(minimum,sep)
     overlap+=sep<data['geometry']['screw']['product_diameter_m']
   assert overlap==0
   metric.update(overlap_pairs=overlap,concurrent_pairs=concurrent_pairs,min_separation_m=minimum)
  if r['class_name']=='carpet':
   parameters={k:v['value'] for k,v in data['parameters'].items()}
   regenerated=stations.derive_products(data['parts'],'carpet',parameters,r['run_id'])
   assert sum(len(p['parts']) for p in data['products'])==sum(p['arrival'] is not None for p in data['parts'])
   assert [(p['id'],p['labels'],p['grade']) for p in regenerated]==[(p['id'],p['labels'],p['grade']) for p in data['products']]
   metric.update(segments=sum(len(p['parts']) for p in data['products']),rolls=len(data['products']),completed_rolls=sum(p['complete'] for p in data['products']))
  runs.append(metric)
 assert len(runs)==9
 assert not browser['errors'] and not browser['http_errors']
 for cls,h in browser['halls'].items():
  cameras=[c for c in h['cameras'] if cls in c['name']]
  assert len(cameras)==3 and all(c['contains'] and c['angle_deg']<=10 for c in cameras)
  assert h['paused'] and h['trigger']['sensor'] and h['trigger']['flash']
  assert h['trigger']['lightIntensity']==2 and h['trigger']['sensorIntensity']==2
  assert h['arrival']['mark' if cls=='carpet' else 'eject']
  assert h['arrival']['actuatorZ']==.32
  assert h['draw_calls']<300
  arm=h['arm'];assert len({a['objectId'] for a in arm})==1
  for phase in ('MOVE_PICK','RETURN_HOME'):
   group=[a for a in arm if a['stage']==phase];assert len(group)==2 and group[0]['objectPosition']==group[1]['objectPosition']
  assert all(a['gripper']=='CLOSED' and a['objectPosition']==a['tcp'] for a in arm if a['attached'])
 report=dict(passed=True,runs=runs,renderer=browser['renderer'],actual_gpu_verified=False,cameras=9,max_camera_angle_deg=max(c['angle_deg'] for h in browser['halls'].values() for c in h['cameras']),max_draw_calls=max(h['draw_calls'] for h in browser['halls'].values()),browser_errors=0,http_errors=0,source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'configs/inspection_stations.json',ROOT/'configs/logistics.yaml',ROOT/'configs/ambient_motion.json',ROOT/'aria/simulation/des/robot.py']})
 (OUT/'verified.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('runs','source_hashes')}))
if __name__=='__main__':main()
