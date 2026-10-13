"""M7 geometry/readability/replay gates. No simulation, image inference or GPU."""
import csv,gzip,hashlib,json,math
from pathlib import Path
import numpy as np
from PIL import Image
from tools.gates.common import ROOT,emit
from aria.dashboard import store


def overlap(a,b):return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
def inside(b,w=1440,h=900):return 0<=b[0]<b[2]<=w and 64<=b[1]<b[3]<=h

def main():
 evidence=json.loads((ROOT/'docs/autopilot/local/campus-browser.json').read_text())
 c=evidence['campus'];h=evidence['hall'];checks={}
 checks['viewport']={'pass':c['viewport']==[1440,900],'measured':c['viewport']}
 heights=[s['glyph_height_px'] for s in c['halls']]
 checks['roof_wordmark']={'pass':len(heights)==3 and min(heights)>=24 and all(s['geometry']=='ExtrudeGeometry' and .5<=s['brand_width_ratio']<=.6 for s in c['halls']),'glyph_heights_px':heights,'width_ratios':[s['brand_width_ratio'] for s in c['halls']]}
 checks['wordmark_not_obscured']={'pass':all(not overlap(s['logo_bounds'],p) for s in c['halls'] for p in c['panels']),'logo_bounds':[s['logo_bounds'] for s in c['halls']]}
 checks['halls_in_frame']={'pass':len(c['halls'])==3 and all(inside(s['bounds']) for s in c['halls']),'bounds':[s['bounds'] for s in c['halls']]}
 names=c['names'];checks['names_readable']={'pass':len(names)==3 and all(inside(n['bounds']) for n in names) and not any(overlap(a['bounds'],b['bounds']) for i,a in enumerate(names) for b in names[i+1:]),'names':names}
 checks['roof_fade']={'pass':h['focus']=='hall-bottle' and next(s for s in h['halls'] if s['id']==h['focus'])['roof_opacity']==0 and all(s['roof_opacity']==1 for s in evidence['return']['halls']),'entered':h['focus'],'opacity':[s['roof_opacity'] for s in h['halls']]}
 checks['minimap']={'pass':evidence['minimap']['focus']=='hall-screw' and evidence['minimap']['target'][:1]==[40],'target':evidence['minimap']['target']}
 checks['deterministic_props']={'pass':c['foliage']==evidence['reload_foliage'],'seed':7,'instances':len(c['foliage']),'sha256':hashlib.sha256(json.dumps(c['foliage']).encode()).hexdigest()}
 checks['decorations_not_clickable']={'pass':c['decorative_handlers']==0,'handlers':c['decorative_handlers']}
 checks['draw_calls']={'pass':max(c['draw_calls'],h['draw_calls'],evidence['playing']['draw_calls'])<=300,'campus':c['draw_calls'],'hall':h['draw_calls'],'hall_playing':evidence['playing']['draw_calls'],'campus_triangles':c['triangles'],'hall_triangles':h['triangles']}
 pixels=np.asarray(Image.open(ROOT/'docs/autopilot/local/m7-campus.png').convert('HSV'))/255
 # Primary hue is blue-violet; require saturation >.3 to exclude pale tints.
 mask=(pixels[:,:,0]>=.62)&(pixels[:,:,0]<=.73)&(pixels[:,:,1]>.3)&(pixels[:,:,2]>.4)
 fraction=float(mask.mean());checks['primary_area']={'pass':fraction<=.15,'fraction':fraction,'limit':.15,'method':'HSV hue .62–.73, saturation >.3, value >.4; full screenshot'}
 snapshots=evidence['replay']['snapshots'];expected={s['run_id']:s for s in evidence['replay']['expected'] if s.get('run_id')}
 ready=[s for s in snapshots if s.get('run_id')];focus=[s for s in ready if s['site']==h['focus']]
 checks['saved_replay']={'pass':all(s['active_ids']==expected[s['run_id']]['active_ids'] and s['ng_count']==expected[s['run_id']]['ng_count'] for s in ready) and evidence['replay']['rendered_parts']==sum(len(s['active_ids']) for s in focus) and evidence['replay']['rendered_queue']==sum(s['queue'] for s in focus) and evidence['paused_positions_equal'],'time':evidence['replay']['time'],'rendered_parts':evidence['replay']['rendered_parts'],'rendered_queue':evidence['replay']['rendered_queue'],'paused_positions_equal':evidence['paused_positions_equal']}
 checks['motion']={'pass':evidence['replay']['positions']!=evidence['next_positions'] and evidence['playing']['time']>1801,'playing_time':evidence['playing']['time'],'single_clock':all(abs(s['time']-evidence['playing']['time'])<1e-8 for s in evidence['playing']['snapshots'])}
 checks['console']={'pass':not evidence['errors'] and not evidence['http_errors'],'errors':evidence['errors'],'http_errors':evidence['http_errors']}
 # Compare opaque input sequence hashes off-screen, including image IDs. No GT is sent to UI.
 raw=[];catalog={r['run_id']:r for r in store.catalog()}
 for site in evidence['data']:
  streams=[];ng=[]
  for run in site['parts']:
   folder=catalog[run['run_id']]['_path']
   with gzip.open(folder/'parts.csv.gz','rt') as f:parts=list(csv.DictReader(f))
   streams.append(hashlib.sha256(json.dumps([(p['part_id'],p['image_id']) for p in parts]).encode()).hexdigest())
   count=sum(p['ai_verdict']=='NG' and p['inspection_time'] and float(p['inspection_time'])<=evidence['replay']['time'] for p in parts)
   shown=next(s['ng_count'] for s in ready if s['run_id']==run['run_id'])
   ng.append({'run_id':run['run_id'],'raw':count,'screen':shown})
  raw.append({'site':site['site'],'available':len(streams),'input_sequences_equal':len(set(streams))==1,'ng':ng,'max_born_delta_seconds':site['max_born_delta_seconds']})
 checks['available_run_comparison']={'pass':all(s['input_sequences_equal'] and all(n['raw']==n['screen'] for n in s['ng']) for s in raw),'sites':raw,'note':'Recorded birth timestamps are preserved; only ID/image order is required to match.'}
 scene=emit('m7-scene',checks,renderer=evidence['renderer'],actual_gpu='미확인')
 all_checks={**checks,'nine_lanes':{'pass':len(ready)==9,'ready':len(ready),'required':9,'missing':[s['site']+':'+s['selector'] for s in snapshots if not s.get('run_id')]}}
 emit('m7',all_checks,status='complete_cpu' if scene['pass'] and len(ready)==9 else 'pending_data' if scene['pass'] else 'failed',actual_gpu='미확인',next='G1',screenshots=['docs/autopilot/local/m7-campus.png','docs/autopilot/local/m7-hall-bottle.png','docs/autopilot/local/m7-hall-screw.png'])
if __name__=='__main__':main()
