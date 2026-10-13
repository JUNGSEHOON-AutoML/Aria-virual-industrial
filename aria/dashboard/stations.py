"""S1–S3 read-only station projections. No DES or oracle write-back."""
import csv
import hashlib
import io
import json
import math
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image
import yaml
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from . import store, logistics, transfer

router=APIRouter(prefix='/api/dt/runs')
CONFIG=store.ROOT/'configs/inspection_stations.json'


def configuration():
    c=json.loads(CONFIG.read_text())
    if c['mode']!='downstream_only' or c['write_back_to_des'] or c['write_back_to_posthoc_b']:
        raise ValueError('Station layer must be read-only')
    raw=yaml.safe_load(logistics.CONFIG.read_text())['inspection_stations']
    values={}
    for key,item in raw.items():
        v=item['value']
        if item['tag']!='assumed' or isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0:
            raise ValueError('Invalid station assumption '+key)
        values[key]=v
    if any(values[k]<=0 for k in ('segment_length_m','segments_per_roll','ok_bin_capacity','transfer_seconds')) or any(int(values[k])!=values[k] for k in ('segments_per_roll','ok_bin_capacity','grade_a_max_labels','grade_b_max_labels')) or values['grade_a_max_labels']>values['grade_b_max_labels']:
        raise ValueError('Invalid station capacities or grades')
    return c,values,raw


def equipment_intervals(transitions,speed,horizon=3600):
    if not math.isfinite(speed) or speed<0:raise ValueError('Invalid belt speed')
    events=sorted((dict(e) for e in transitions if e['component']=='AI-INSPECTION'),key=lambda e:e['time'])
    rows=[];distance=0.
    for i,e in enumerate(events):
        end=events[i+1]['time'] if i+1<len(events) else horizon
        velocity=speed if e['state']=='PROCESSING' else 0.
        rows.append(dict(start=e['time'],end=end,state=e['state'],speed=velocity,distance=distance,
                         lamp='FAULT' if e['state']=='DOWN' else 'RUN' if e['state']=='PROCESSING' else 'STOP'))
        distance+=max(0,end-e['time'])*velocity
    return rows


def station_parts(parts,cls):
    rows=[]
    for p in parts:
        trigger=next((e['time'] for e in p['entries'] if e['component']=='AI-INSPECTION'),None)
        arrival=p['mainline_exit_time']
        if trigger is None:continue
        # Arrival is the recorded sink/deadline boundary, not decision time.
        # Keep decision/arrival separate for late HOLD results.
        rows.append(dict(id=p['part_id'],trigger=trigger,decision=p['inspection_time'],arrival=arrival,
                         verdict=p['verdict'],route=p['route'],born=p['born'],exit=p['exit_time'],
                         score=p['score'],threshold=p['threshold'],latency_ms=p['latency_ms']))
    return sorted(rows,key=lambda p:(p['trigger'],p['id']))


def derive_products(parts,cls,values,run_id):
    """Original AI decisions only. No GT input, no filtering carpet to OK only."""
    ready=sorted((p for p in parts if p['arrival'] is not None),key=lambda p:(p['born'],p['id']))
    products=[]
    if cls=='carpet':
        n=int(values['segments_per_roll'])
        for i,start in enumerate(range(0,len(ready),n)):
            rows=ready[start:start+n];complete=len(rows)==n
            labels=[p['id'] for p in rows if p['verdict']=='NG' and p['decision'] is not None and p['decision']<=p['arrival']]
            grade='A' if len(labels)<=values['grade_a_max_labels'] else 'B' if len(labels)<=values['grade_b_max_labels'] else 'C'
            products.append(dict(id=f'{run_id}:ROLL:{i:05d}',kind='roll',parts=[p['id'] for p in rows],
                ready=max(p['arrival'] for p in rows) if complete else None,complete=complete,
                labels=labels,grade=grade if complete else None,length_m=len(rows)*values['segment_length_m'],
                unresolved=sum(p['route']=='HOLD' or p['decision'] is None or p['decision']>p['arrival'] for p in rows),
                tag='assumed',grade_source='on-time NG label count, not ground truth'))
    elif cls=='screw':
        rows=sorted((p for p in ready if p['route']=='OK'),key=lambda p:(p['arrival'],p['id']))
        n=int(values['ok_bin_capacity'])
        for i,start in enumerate(range(0,len(rows),n)):
            batch=rows[start:start+n]
            products.append(dict(id=f'{run_id}:BIN:{i:05d}',kind='bin',parts=[p['id'] for p in batch],
                                 ready=batch[-1]['arrival'] if len(batch)==n else None,complete=len(batch)==n,tag='assumed'))
    return products


def product_evaluation(products,original,gt_path):
    """Evaluation-only join AFTER label assignment/grading; no feedback."""
    with Path(gt_path).open() as f:gt={r['image_id']:int(r['is_defect']) for r in csv.DictReader(f)}
    ids={p['part_id']:p['image_id'] for p in original}
    verdict={p['part_id']:p['ai_verdict'] for p in original}
    return {p['id']:dict(unlabelled_defects_evaluated=sum(gt[ids[pid]]==1 and pid not in p.get('labels',[]) for pid in p['parts']),
                        false_negatives_evaluated=sum(gt[ids[pid]]==1 and verdict[pid]=='OK' for pid in p['parts'])) for p in products}


def source_events(products,logistic,parts,cls,run_id):
    events=[]
    if cls=='bottle':
        for box in logistic['boxes']:
            events.append(dict(id='box-ready:'+box['id'],time=box['ready'],object_id=box['id'],kind='box',actor='production'))
    else:
        for item in products:
            if item['ready'] is not None:
                events.append(dict(id=item['kind']+'-ready:'+item['id'],time=item['ready'],object_id=item['id'],kind=item['kind'],actor='production',**({'grade':item['grade']} if cls=='carpet' else {})))
    for p in parts:
        at=p.get('reinspection_queue_enter')
        if at is not None:
            events.append(dict(id=f'{run_id}:B-NG-arrival:{p["part_id"]}',time=at,object_id=p['part_id'],kind='reinspection',actor='reinspection'))
    return events


@lru_cache(maxsize=9)
def load(run_id,config_hash):
    c,values,raw=configuration();r=store.load(run_id);cls=r['config']['class_name']
    parts=station_parts(r['public'],cls);products=derive_products(parts,cls,values,run_id)
    if cls=='carpet':
        evaluated=product_evaluation(products,r['parts'],r['gt'])
        for product in products:product.update(evaluated[product['id']])
    # Reuse the existing box-completion calculation; never synthesize a second one.
    existing=logistics.load(run_id,'A',hashlib.sha256(logistics.CONFIG.read_bytes()).hexdigest()) if cls=='bottle' else {'boxes':[]}
    events=source_events(products,existing,r['public'],cls,run_id)
    rows,total=transfer.program(values['transfer_seconds'])
    from aria.simulation.des.robot import JOINTS
    return dict(version=1,run_id=run_id,class_name=cls,selector=r['config']['selector'],
                geometry=c,parameters=raw,parts=parts,products=products,visual_feed_speed_mps=r['config']['speed'],
                equipment=equipment_intervals(r['transitions'],r['config']['speed']),
                trigger_source='recorded AI-INSPECTION part_move',arrival_source='recorded mainline_exit_time',
                source_events=events,transfer_tasks=transfer.schedule(events,values['transfer_seconds']),
                transfer_program=rows,transfer_duration=total,robot_joints=JOINTS,
                grade_programs={g:transfer.grade_program(g,values['transfer_seconds'])[0] for g in ('A','B','C')},
                original_complete_hash=r['complete_hash'],config_hash=config_hash,
                role='fixed camera inspection; downstream robot handling; not mechanical validation')


def key():return hashlib.sha256(CONFIG.read_bytes()+logistics.CONFIG.read_bytes()).hexdigest()


@router.get('/{run_id}/stations')
def stations(run_id:str):return load(run_id,key())


@router.get('/{run_id}/stations/detail')
def detail(run_id:str,t:float=Query(0,ge=0,le=3600)):
    r=store.load(run_id);projection=load(run_id,key())
    inspected=sorted((p for p in r['public'] if p['inspection_time'] is not None and p['inspection_time']<=t),key=lambda p:(p['inspection_time'],p['part_id']))
    recent=[dict(part_id=p['part_id'],time=p['inspection_time'],verdict=p['verdict'],score=p['score'],threshold=p['threshold'],
                 original=f'/api/dt/runs/{run_id}/stations/evidence/{p["part_id"]}/original',overlay=f'/api/dt/runs/{run_id}/stations/evidence/{p["part_id"]}/overlay') for p in inspected[-10:][::-1]]
    latencies=[p['latency_ms'] for p in inspected if p['latency_ms'] is not None]
    # Resolution is observed from the actual dataset, not a camera datasheet.
    first=r['parts'][0]['image_id']
    with Image.open(store.ROOT/'data'/first) as im:resolution=list(im.size)
    products=[p for p in projection['products'] if p['ready'] is not None and p['ready']<=t]
    return dict(time=t,run_id=run_id,model=r['config']['selector'],class_name=r['config']['class_name'],
                camera=dict(direction=[0,-1,0],view='dataset top-down',image_resolution=resolution,inference_resolution=[224,224],side_camera='inactive; no dataset'),
                threshold=inspected[-1]['threshold'] if inspected else None,recent=recent,
                latency_ms={q:float(np.percentile(latencies,n)) if latencies else None for q,n in [('p50',50),('p95',95)]},
                products=products[-10:],parameters=projection['parameters'])


@lru_cache(maxsize=9)
def evidence_inputs(cls,model):
    folder=store.P1/cls;lock=json.loads((folder/'complete.json').read_text())
    for name in ('protocol.json',model+'/common_maps.npy',model+'/predictions.csv'):
        if store.sha(folder/name)!=lock['files'][name]:raise ValueError('Saved heatmap integrity failure')
    order=json.loads((folder/'protocol.json').read_text())['test_ids']
    with (folder/model/'predictions.csv').open() as f:pred={r['image_id']:r for r in csv.DictReader(f)}
    return {x:i for i,x in enumerate(order)},pred,np.load(folder/model/'common_maps.npy',mmap_mode='r')


@router.get('/{run_id}/stations/evidence/{part_id}/{kind}')
def evidence(run_id:str,part_id:str,kind:str):
    if kind not in ('original','overlay'):raise HTTPException(404,'Unknown evidence')
    r=store.load(run_id);p=next((p for p in r['parts'] if p['part_id']==part_id),None)
    if p is None:raise HTTPException(404,'Unknown part')
    indices,pred,maps=evidence_inputs(r['config']['class_name'],r['config']['selector'])
    source=store.ROOT/'data'/p['image_id']
    if store.sha(source)!=pred[p['image_id']]['image_sha256']:raise ValueError('Source image hash mismatch')
    # Match the existing P1 256-short-edge / 224-center-crop input view.
    from tools.build_vision_audit import crop
    image=crop(source).convert('RGB')
    if kind=='overlay':
        raw=np.asarray(maps[indices[p['image_id']]],dtype=np.float32)
        heat=(raw-raw.min())/max(float(raw.max()-raw.min()),1e-9)
        heat=np.asarray(Image.fromarray(heat).resize(image.size,Image.Resampling.BILINEAR))
        color=np.zeros((*heat.shape,3),dtype=np.float32);color[:,:,0]=255;color[:,:,1]=160*(1-heat)
        alpha=heat[:,:,None]*.65;image=Image.fromarray(np.uint8((np.asarray(image)*(1-alpha)+color*alpha).clip(0,255)))
    out=io.BytesIO();image.save(out,format='PNG')
    return Response(out.getvalue(),media_type='image/png',headers={'Cache-Control':'private, max-age=3600'})
