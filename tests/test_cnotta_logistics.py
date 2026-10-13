import copy,json
import pytest
from aria.dashboard.logistics import configuration,derive,inventory,evaluate_trucks

LAYOUT={'staging':[0,0,0],'dock':[20,0,10],'gate':[-20,0,0],'road_z':5,'tag':'assumed'}
def parts(n=259):
 return [dict(part_id=f'P{i:04}',image_id=f'im{i}',born=i*.2,route='OK' if i%5 else 'NG',exit_time=i*.2+1,ai_verdict='OK' if i%5 else 'NG',reinspection_start=None,reinspection_time=None,reinspection_verdict=None) for i in range(n)]
def result(rows):
 _,p=configuration();return derive(rows,p,run_id='fixture',policy='A',seed=0,layout=LAYOUT)

def test_determinism_source_immutable_and_full_time_conservation():
 source=parts();before=copy.deepcopy(source);a=result(source);b=result(source)
 assert a==b and source==before
 for t in range(0,10000,7):
  x=inventory(a,t);assert x['ok_exit_count']==x['shipped_count']+x['unshipped_count']
 manifests=[pid for truck in a['trucks'] for pid in truck['parts']]
 assert len(manifests)==len(set(manifests))
 assert set(manifests)<={p['part_id'] for p in source if p['route']=='OK'}
 assert inventory(a,99999)['unshipped_count']>0  # partial boxes/pallets/trucks remain accounted for

def test_gate_crossing_is_shipment_boundary():
 a=result(parts(601));truck=next(t for t in a['trucks'] if t['gate_exit'] is not None)
 assert inventory(a,truck['departure'])['shipped_count']==0
 assert inventory(a,truck['gate_exit'])['shipped_count']==len(truck['parts'])

def test_recovered_b_part_cannot_ship_before_reinspection():
 rows=parts(100);rows[1].update(ai_verdict='NG',exit_time=400,reinspection_start=370,reinspection_time=400,reinspection_verdict='OK')
 _,p=configuration();a=derive(rows,p,run_id='fixture',policy='B',seed=0,layout=LAYOUT)
 box=next(b for b in a['boxes'] if rows[1]['part_id'] in b['parts']) if any(rows[1]['part_id'] in b['parts'] for b in a['boxes']) else None
 assert box is None or box['start']>=400
 assert any(x['id']==rows[1]['part_id'] and x['time']==400 for x in a['exits'])

def test_gt_is_evaluation_only(tmp_path):
 rows=parts(601);a=result(rows);before=copy.deepcopy(a)
 gt=tmp_path/'gt.csv';gt.write_text('image_id,is_defect\n'+''.join(f'{p["image_id"]},{int(i%3==0)}\n' for i,p in enumerate(rows)))
 fn=evaluate_trucks(a,rows,gt);assert a==before
 labels={p['part_id']:int(i%3==0) for i,p in enumerate(rows)}
 assert all(fn[t['id']]==sum(labels[x] for x in t['parts']) for t in a['trucks'])

@pytest.mark.parametrize('bad',[None,True,-1,float('nan'),1.5])
def test_unset_invalid_parameters_rejected(tmp_path,bad):
 import yaml
 c,_=configuration();c['parameters']['parts_per_box']['value']=bad;p=tmp_path/'config.yaml';p.write_text(yaml.safe_dump(c))
 with pytest.raises(ValueError):configuration(p)

def test_no_actor_double_booking():
 a=result(parts(6001))
 for key in ('forklifts','scrap'):
  actors={x['actor'] for x in a[key]}
  for actor in actors:
   rows=[x for x in a[key] if x['actor']==actor]
   assert all(a['end']<=b['start'] for a,b in zip(rows,rows[1:]))
