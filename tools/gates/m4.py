import json,math
from aria.dashboard import store
from aria.simulation.dt.posthoc import reconstruct_b
from .common import ROOT,emit
b=json.loads((ROOT/'docs/autopilot/local/browser.json').read_text());p=b['panels'];k=p['kpi'];r=store.load(p['run_id']);_,metrics,norm,_=reconstruct_b(r['parts'],r['gt'],seed=r['config']['seed'],warmup=600,horizon=k['time'])
offline={**metrics,**norm};comparisons=[]
for d in p['display']:
 key=d['metric'];value=None if d['value']=='' else float(d['value']);comparisons.append({'metric':key,'display_raw':value,'API':k[key],'offline':offline[key],'pass':value==k[key]==offline[key],'rendered_text':d['text']})
cases=[{**q,'posthoc':store.queue_at(store.load(q['run_id']),q['time'])} for q in b['queue_cases']]
out=emit('m4',{'queue_nonzero_and_overflow':{'pass':all(q['mesh_count']==q['rack_count']==q['posthoc'] for q in cases) and max(q['posthoc'] for q in cases)>18,'cases':cases},**{'kpi':{'pass':all(v['pass'] for v in comparisons),'values':comparisons,'time':k['time']},'rack_queue':{'pass':p['rack_count']==store.queue_at(r,k['time']),'rendered':p['rack_count'],'posthoc':store.queue_at(r,k['time'])},'panel_occlusion':{'pass':p['coverage']['equipment_pixels']>0 and p['coverage']['ratio']<=.15,**p['coverage']},'console':{'pass':not b['errors'],'errors':b['errors']}}})
raise SystemExit(0 if out['pass'] else 1)
