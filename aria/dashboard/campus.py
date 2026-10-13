"""Read-only, exactly matched saved runs. Missing lanes stay pending."""
import json
from fastapi import APIRouter
from . import store

router=APIRouter()
LAYOUT=store.ROOT/'frontend/src/campus/campus.layout.json'

def select_lanes(layout, catalog):
 sites=[]
 for site in layout['sites']:
  if site['kind']!='inspection_hall':continue
  lanes=[]
  for model in site['lanes']:
   match=next((r for r in catalog if r['class_name']==site['class'] and r['selector']==model and all(r.get(k)==v for k,v in site['run_selector'].items())),None)
   lanes.append({'selector':model,'status':'ready' if match else 'pending','run':{k:v for k,v in match.items() if not k.startswith('_')} if match else None})
  sites.append({'id':site['id'],'name':site['name'],'lanes':lanes})
 return sites

@router.get('/api/dt/campus')
def campus():
 sites=select_lanes(json.loads(LAYOUT.read_text()),store.catalog())
 return {'sites':sites,'full_study_ready':store.full_ready(),'ready_lanes':sum(l['status']=='ready' for s in sites for l in s['lanes']),'clock':'shared saved-run time','missing_lane_policy':'pending; never substitute other conditions'}
