import csv,hashlib,json,time
from pathlib import Path
from aria.simulation.site.runtime import SiteRuntime
from aria.simulation.des.inspection import InspectionAdapter
root=Path.cwd();out=root/'docs/validation/aria_site_scale';source=root/'outputs/factory/factory.json'
payload=json.loads(source.read_text());model=payload.get('model',payload)
if any(c.get('inspection_mode','mock')!='mock' for c in model['components'] if c['kind']=='Inspection'):
 raise SystemExit('This bounded recorder expects the approved mock demo; real inference requires a separate explicit run.')
s=SiteRuntime(model,InspectionAdapter(root),payload.get('revision',0))
start=time.perf_counter();s.control('run')
for _ in range(18001):
 s.tick(.1)
 if s.status!='running':break
elapsed=time.perf_counter()-start
snapshot=s.snapshot();assert s.status=='completed' and not s.error
(out/'full_lifecycle_actual_model.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
(out/'static_twin_definition.json').write_text(json.dumps(s.definition.model_dump(),ensure_ascii=False,indent=2))
events=list(s.events)
with (out/'event_trace.csv').open('w',newline='') as f:
 fields=['id','sequence','time','type','component','shipment_id','truck_id','pallet_id','part','state','previous','verdict','purpose','payload']
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
 for e in events:w.writerow({**{k:e.get(k,'') for k in fields[:-1]},'payload':json.dumps(e,ensure_ascii=False)})
summary={'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_revision':s.revision,'components':len(s.model.components),'inspection_modes':{c.id:c.inspection_mode for c in s.model.components if c.kind=='Inspection'},'sim_time':s.time,'offline_wall_s':elapsed,'event_count':len(events),'metrics':snapshot['metrics'],'production_metrics':snapshot['production']['metrics'],'shipments':[]}
for sh in snapshot['shipments']:
 rows=[e for e in events if e.get('shipment_id')==sh['id']]
 stages={k:next((e['time'] for e in rows if e['type']==k),None) for k in ['gate_passed','dock_assigned','pallet_unloaded','production_external_material_admitted','production_inspection_result','finished_goods_staged','shipment_departed']}
 summary['shipments'].append({'id':sh['id'],'state':sh['state'],'good':len(sh['good_ids']),'ng':len(sh['reject_ids']),'held':len(sh['hold_ids']),**stages})
(out/'lifecycle_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False))
