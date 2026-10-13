"""Read-only, deterministic downstream logistics; never feeds DES or posthoc B."""
import csv
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Literal
import yaml
from fastapi import APIRouter, Query
from . import store
from aria.simulation.dt.posthoc import reconstruct_b

CONFIG = store.ROOT / 'configs/logistics.yaml'
router = APIRouter(prefix='/api/dt/runs')
COUNTS = {'parts_per_box', 'boxes_per_pallet', 'pallets_per_truck', 'forklift_count',
          'outbound_truck_count', 'inbound_parts_per_pallet', 'inbound_pallets_per_truck',
          'initial_raw_material_pallets', 'scrap_bin_capacity', 'scrap_cart_count'}

def configuration(path=CONFIG):
    config = yaml.safe_load(Path(path).read_text())
    if not config.get('enabled') or config.get('mode') != 'downstream_only' or config.get('write_back_to_des') or config.get('write_back_to_posthoc_b'):
        raise ValueError('Logistics must be enabled and downstream only')
    values = {}
    for key, item in config['parameters'].items():
        value = item['value']
        if item.get('tag') != 'assumed' or isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value):
            raise ValueError(f'Unset/invalid assumed logistics parameter: {key}')
        if value < 0 or (value == 0 and key != 'initial_raw_material_pallets') or (key in COUNTS and int(value) != value):
            raise ValueError(f'Invalid logistics parameter: {key}')
        values[key] = int(value) if key in COUNTS else value
    return config, values

def distance(points):
    return sum(math.dist(a,b) for a,b in zip(points,points[1:]))

def groups(rows, size, partial=False):
    for start in range(0,len(rows),size):
        group = rows[start:start+size]
        if partial or len(group)==size:
            yield group

def derive(parts, values, *, run_id, policy, seed, layout):
    """Inputs are final-policy records, without any evaluation labels."""
    if policy not in ('A','B'): raise ValueError('Choose one final policy')
    ids = [p['part_id'] for p in parts]
    if len(ids)!=len(set(ids)): raise ValueError('Duplicate source part ID')
    p = values
    ok = sorted((x for x in parts if x['route']=='OK' and x['exit_time'] is not None),key=lambda x:(x['exit_time'],x['part_id']))
    ng = sorted((x for x in parts if x['route']=='NG' and x['exit_time'] is not None),key=lambda x:(x['exit_time'],x['part_id']))
    staging, dock, gate = layout['staging'], layout['dock'], layout['gate']
    def route(a,b):return [a,[a[0],0,layout['road_z']],[b[0],0,layout['road_z']],b]
    boxes=[];pallets=[];jobs=[];trucks=[];inbound=[];scrap=[];packing_free=0;pallet_free=0
    def key(kind,i):return f'{run_id}:{policy}:{kind}{i:05d}'
    for i,group in enumerate(groups(ok,p['parts_per_box'])):
        start=max(group[-1]['exit_time'],packing_free);packing_free=start+p['packing_seconds_per_box']
        boxes.append(dict(id=key('BOX',i),start=start,ready=packing_free,parts=[x['part_id'] for x in group]))
    forklifts=[dict(id=f'FL-{i+1}',available=0.,position=staging) for i in range(p['forklift_count'])]
    for i,group in enumerate(groups(boxes,p['boxes_per_pallet'])):
        start=max(group[-1]['ready'],pallet_free);pallet_free=start+p['palletizing_seconds_per_pallet']
        idle=[f for f in forklifts if f['available']<=pallet_free]
        f=min(idle,key=lambda f:(distance(route(f['position'],staging)),f['id'])) if idle else min(forklifts,key=lambda f:(f['available'],f['id']))
        begin=max(pallet_free,f['available']);pickup=begin+distance(route(f['position'],staging))/p['forklift_speed_mps']
        loaded=pickup+p['forklift_load_seconds'];arrived=loaded+distance(route(staging,dock))/p['forklift_speed_mps'];end=arrived+p['forklift_unload_seconds']
        pallet=dict(id=key('PAL',i),start=start,ready=pallet_free,delivered=end,boxes=[x['id'] for x in group],parts=[pid for box in group for pid in box['parts']])
        pallets.append(pallet)
        jobs.append(dict(id=key('JOB',i),actor=f['id'],pallet=pallet['id'],start=begin,pickup=pickup,loaded=loaded,arrived=arrived,end=end,approach=route(f['position'],staging),path=route(staging,dock)))
        f.update(available=end,position=dock)
    fleet=[dict(id=f'TRK-{i+1}',available=0.) for i in range(p['outbound_truck_count'])]
    for i,group in enumerate(groups(pallets,p['pallets_per_truck'],partial=True)):
        actor=min(fleet,key=lambda f:(f['available'],f['id']))
        start=max(group[0]['delivered'],actor['available']);arrival=start+distance(route(gate,dock))/p['truck_speed_mps'];loaded=arrival;loads=[]
        for pallet in group:
            loaded=max(loaded,pallet['delivered'])+p['truck_load_seconds_per_pallet'];loads.append(dict(pallet=pallet['id'],time=loaded,parts=pallet['parts']))
        complete=len(group)==p['pallets_per_truck'];exit_time=loaded+distance(route(dock,gate))/p['truck_speed_mps'] if complete else None
        trucks.append(dict(id=key('TRUCK',i),actor=actor['id'],start=start,load_start=arrival,departure=loaded if complete else None,gate_exit=exit_time,pallets=[x['id'] for x in group],parts=[pid for x in group for pid in x['parts']],capacity=p['pallets_per_truck'],loads=loads,verdict='OK',inbound_path=route(gate,dock),path=route(dock,gate)))
        actor['available']=exit_time if complete else math.inf
    born=sorted((x for x in parts if x.get('born') is not None),key=lambda x:(x['born'],x['part_id']))
    initial=p['initial_raw_material_pallets']*p['inbound_parts_per_pallet'];batch=p['inbound_pallets_per_truck']*p['inbound_parts_per_pallet']
    for i,group in enumerate(groups(born[initial:],batch,partial=True)):
        start=group[0]['born'];arrival=start+distance(route(gate,staging))/p['truck_speed_mps'];end=arrival+p['inbound_pallets_per_truck']*p['inbound_unload_seconds_per_pallet']
        inbound.append(dict(id=key('IN',i),start=start,arrival=arrival,end=end,pallets=p['inbound_pallets_per_truck'],path=route(gate,staging),trigger='source consumption; replenishment does not block DES'))
    carts=[dict(id=f'CART-{i+1}',available=0.) for i in range(p['scrap_cart_count'])]
    for i,group in enumerate(groups(ng,p['scrap_bin_capacity'])):
        cart=min(carts,key=lambda c:(c['available'],c['id']));start=max(group[-1]['exit_time'],cart['available']);end=start+p['scrap_collection_seconds']+distance(route(staging,gate))/p['scrap_cart_speed_mps']
        scrap.append(dict(id=key('SCRAP',i),actor=cart['id'],start=start,end=end,parts=[x['part_id'] for x in group],path=route(staging,gate)));cart['available']=end
    return dict(version=1,run_id=run_id,policy=policy,seed=seed,tag='assumed',layout=layout,
                exits=[dict(id=x['part_id'],time=x['exit_time']) for x in ok],boxes=boxes,pallets=pallets,forklifts=jobs,trucks=trucks,inbound=inbound,scrap=scrap,
                reinspection=[dict(id=x['part_id'],start=x['reinspection_start'],end=x.get('reinspection_time'),verdict=x.get('reinspection_verdict')) for x in parts if policy=='B' and x.get('reinspection_start') is not None])

def evaluate_trucks(result, parts, gt_path):
    """Evaluation-only join AFTER assignments/routes; GT never enters derive()."""
    with Path(gt_path).open() as f:gt={r['image_id']:int(r['is_defect']) for r in csv.DictReader(f)}
    by_id={p['part_id']:p for p in parts}
    return {truck['id']:sum(gt[by_id[pid]['image_id']]==1 for pid in truck['parts']) for truck in result['trucks']}

def inventory(result, t):
    available={x['id'] for x in result['exits'] if x['time']<=t}
    shipped=[pid for truck in result['trucks'] if truck['gate_exit'] is not None and truck['gate_exit']<=t for pid in truck['parts']]
    if len(shipped)!=len(set(shipped)) or not set(shipped)<=available:raise ValueError('Shipment conservation failed')
    return dict(time=t,ok_exit_count=len(available),shipped_count=len(shipped),unshipped_count=len(available-set(shipped)),conserved=True,source='derived: final-policy exits = gate departures + all unshipped WIP')

@lru_cache(maxsize=6)
def load(run_id,policy,config_hash):
    config,values=configuration();run=store.load(run_id);parts=run['parts']
    if policy=='B':parts,_,_,_=reconstruct_b(parts,run['gt'],seed=run['config']['seed'])
    campus=json.loads((store.ROOT/'frontend/src/campus/campus.layout.json').read_text())
    site=next(s for s in campus['sites'] if s.get('class')==run['config']['class_name'])
    ox,oz=site['origin'];offset=config['layout']['staging_offset']['value'];road_z=campus['roads'][0][0][1];yard=next(s for s in campus['sites'] if s['kind']=='logistics_yard')
    layout=dict(staging=[ox+offset[0],offset[1],oz+offset[2]],dock=[yard['origin'][0],0,yard['origin'][1]],gate=[campus['bounds']['min'][0],0,road_z],road_z=road_z,tag='assumed')
    result=derive(parts,values,run_id=run_id,policy=policy,seed=run['config']['seed'],layout=layout)
    fn=evaluate_trucks(result,parts,run['gt'])
    for truck in result['trucks']:truck['escaped_defects']=fn[truck['id']]
    result.update(config_hash=config_hash,parameters=config['parameters'],motion=config['motion'],input_hash=run['complete_hash'])
    return result

@router.get('/{run_id}/logistics')
def logistics(run_id:str,policy:Literal['A','B']='B',t:float=Query(0,ge=0,le=3600)):
    digest=hashlib.sha256(CONFIG.read_bytes()).hexdigest();result=load(run_id,policy,digest)
    return {**result,'inventory':inventory(result,t)}

@router.get('/{run_id}/logistics/state')
def logistics_state(run_id:str,policy:Literal['A','B']='B',t:float=Query(0,ge=0,le=3600)):
    result=load(run_id,policy,hashlib.sha256(CONFIG.read_bytes()).hexdigest())
    trucks=[]
    for truck in result['trucks']:
        if truck['start']>t:continue
        departed=truck['departure'] is not None and truck['departure']<=t
        shipped=truck['gate_exit'] is not None and truck['gate_exit']<=t
        loads=[row for row in truck['loads'] if row['time']<=t]
        trucks.append(dict(id=truck['id'],actor=truck['actor'],state='출하 완료' if shipped else '출발' if departed else '적재' if truck['load_start']<=t else '도크 진입',loaded_pallets=len(loads),capacity=truck['capacity'],loaded_parts=sum(len(row['parts']) for row in loads),escaped_defects=truck['escaped_defects'] if departed else None,load_start=truck['load_start'],departure=truck['departure'],gate_exit=truck['gate_exit']))
    return dict(**inventory(result,t),trucks=trucks,policy=policy,config_hash=result['config_hash'],tag='derived',parameters_tag='assumed')
