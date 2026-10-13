"""Opt-in ARIA DT experiment preview, isolated from the saved factory runtime."""
import asyncio,csv,hashlib,json,os,threading,time
from collections import deque
from pathlib import Path
from typing import Literal
from fastapi import APIRouter,HTTPException
from fastapi.responses import FileResponse,Response
from pydantic import BaseModel,Field
from aria.simulation.dt.line import load_profile,make_line
from aria.simulation.dt.replay import ReplayCatalog,ReplayEngine
from aria.simulation.dt.reinspect_oracle import ReinspectOracle
from aria.simulation.dt.evaluation import PartLedger,evaluate,build_source_schedule,offline_queue_metrics
ROOT=Path(__file__).resolve().parents[2]
P1=ROOT/'docs/validation/aria_dt_20261012_02/p1_verified'
RESULTS=Path(os.environ.get('ARIA_DT_RESULTS',str(ROOT/'docs/validation/aria_dt_20261013_03/des_pilot30')))
router=APIRouter(prefix='/api/dt',tags=['DT experiments'])
class Start(BaseModel):
    class_name:Literal['bottle','screw','carpet']='bottle'
    selector:Literal['coreset','ccifps','random_same_k']='ccifps'
    policy:Literal['A','B']='A'
    cell:Literal['inline','robot']='inline'
    speed:Literal[.25,.5,.75,1.]=.5
    latency_mode:Literal['profile','constant']='profile'
    seed:int=Field(default=0,ge=0,le=29)
    sensitivity:Literal[.95,.98,1.]=1.
    specificity:Literal[.95,.98,1.]=1.
    reinspection_s:Literal[10,30,60]=30
class Preview:
    def __init__(self):self.lock=threading.RLock();self.engine=None;self.running=False
    def start(self,c):
        with self.lock:
            base=P1/c.class_name;done=json.loads((base/'complete.json').read_text())
            paths=[base/c.selector/'predictions.csv',base/c.selector/'latency_profile_faiss_gpu.json',base/'gt_labels.csv']
            for p in paths:
                if hashlib.sha256(p.read_bytes()).hexdigest()!=done['files'][str(p.relative_to(base))]:raise ValueError('P1 hash mismatch')
            self.gt=paths[-1];self.ledger=PartLedger();self.events=deque(maxlen=300);self.config=c.model_dump()
            relative=Path('config/latency_profiles/dt_hmi')/c.class_name/(c.selector+'.json');target=ROOT/relative;target.parent.mkdir(parents=True,exist_ok=True)
            raw=paths[1].read_bytes()
            if target.exists() and target.read_bytes()!=raw:raise ValueError('Existing preview profile differs')
            if not target.exists():target.write_bytes(raw)
            params,_=load_profile(ROOT/'configs/line_profile.yaml')
            model=make_line(params,str(relative),hashlib.sha256(raw).hexdigest(),seed=c.seed,cell=c.cell,speed=c.speed,policy=c.policy,reinspection_s=c.reinspection_s)
            catalog=ReplayCatalog(paths[0],c.seed)
            import math
            itinerary=build_source_schedule(self.gt,[r['image_id'] for r in catalog.rows],seed=c.seed,defect_rate=params['defect_rate'],count=math.ceil(3600*c.speed/params['pitch_m'])+2)
            catalog=ReplayCatalog(paths[0],c.seed,schedule=itinerary['image_ids'])
            self.config['defect_rate']=params['defect_rate']
            oracle=ReinspectOracle(self.gt,seed=c.seed,sensitivity=c.sensitivity,specificity=c.specificity) if c.policy=='B' else None
            def record(e):self.ledger.add(e);self.events.append(e)
            self.engine=ReplayEngine(model,catalog,event_sink=record,constant_median=c.latency_mode=='constant',oracle=oracle)
            self.running=True;self.engine.status='running';return self.snapshot()
    def advance(self,dt):
        with self.lock:
            if self.engine and self.running:
                self.engine.run_until(min(3600,self.engine.now+min(dt,.25)))
                if self.engine.now>=3600:self.running=False;self.engine.status='completed'
    def snapshot(self):
        with self.lock:
            if not self.engine:return dict(ready=False,sim=1)
            state=self.engine.snapshot();quality=evaluate(self.ledger.rows(),self.gt,warmup=0,horizon=max(self.engine.now,1e-9))
            quality.update(offline_queue_metrics(self.ledger.rows(),warmup=0,horizon=max(self.engine.now,1e-9),service_seconds=self.config['reinspection_s']))
            return dict(ready=True,sim=1,config=self.config,running=self.running,**state,quality=quality,
                        dt_events=list(self.events),tracked_parts=self.ledger.rows()[-60:],kpi_scope='preview since time0, not final warmup-excluded experiment',human_model='assumed oracle; not measured human accuracy')
preview=Preview()
@router.post('/run')
def run(c:Start):
    try:return preview.start(c)
    except (ValueError,FileNotFoundError,KeyError) as e:raise HTTPException(409,str(e))
@router.post('/pause')
def pause():
    with preview.lock:
        preview.running=False
        if preview.engine:preview.engine.status='paused'
        return preview.snapshot()
@router.get('/snapshot')
def snapshot():return preview.snapshot()
@router.get('/results')
def results():
    p=RESULTS/'scenario_results.csv';completion=RESULTS/'completion.json'
    if not p.is_file():return dict(complete=False,rows=[])
    with p.open() as f:rows=list(csv.DictReader(f))
    return dict(complete=completion.is_file(),rows=rows,scope='sim=1; 600s warmup excluded; paired seeds')
@router.get('/cad/{part}/{name}')
def cad(part:str,name:str):
    if part not in ('conveyor','inspection_booth','diverter') or name not in ('model.glb','dims.json'):raise HTTPException(404)
    return FileResponse(ROOT/'assets/cad'/part/'dt_v1'/name)
@router.get('/evidence/{part_id}')
def evidence(part_id:str,heatmap:bool=False):
    import io
    import numpy as np
    from PIL import Image
    with preview.lock:
        if not preview.engine or part_id not in preview.engine.part_metadata:raise HTTPException(404)
        iid=preview.engine.part_metadata[part_id]['image_id'];rows=preview.engine.catalog.rows;idx=next(i for i,r in enumerate(rows) if r['image_id']==iid)
        data=(ROOT/'data').resolve();image_path=(data/iid).resolve()
        if not image_path.is_relative_to(data):raise HTTPException(400)
        im=Image.open(image_path).convert('RGB');w,h=im.size
        scale=256/min(w,h);im=im.resize((int(w*scale),int(h*scale)),Image.Resampling.BILINEAR);w,h=im.size;im=im.crop(((w-224)//2,(h-224)//2,(w+224)//2,(h+224)//2))
        if heatmap:
            maps=np.load(P1/preview.config['class_name']/preview.config['selector']/'common_maps.npy',mmap_mode='r');m=np.asarray(maps[idx]);z=(m-m.min())/max(float(m.max()-m.min()),1e-12)
            rgb=np.zeros((224,224,3),dtype=np.uint8);rgb[:,:,0]=(255*z).astype('uint8');rgb[:,:,2]=(255*(1-z)).astype('uint8');im=Image.blend(im,Image.fromarray(rgb),.45)
        b=io.BytesIO();im.save(b,format='PNG');return Response(b.getvalue(),media_type='image/png')
async def loop():
    last=time.monotonic()
    while True:
        await asyncio.sleep(.05);now=time.monotonic();dt=now-last;last=now
        await asyncio.to_thread(preview.advance,dt)
