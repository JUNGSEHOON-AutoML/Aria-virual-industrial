"""Explicit CCIFPS bundles: train -> inspect status -> infer. No legacy bank overwrite."""
import os,subprocess,sys,uuid,re,json,asyncio,threading
from pathlib import Path
from fastapi import APIRouter,Body,HTTPException
from starlette.concurrency import run_in_threadpool
from aria.perception.ccifps_backend import BUNDLE_ROOT,ROOT,atomic_json,load_bundle
router=APIRouter(prefix='/api/ccifps',tags=['ccifps'])

@router.post('/train')
async def train(payload:dict=Body(...)):
    category=payload.get('category','bottle')
    if not isinstance(category,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',category):raise HTTPException(422,'invalid category')
    if not (ROOT/'data'/category/'train/good').is_dir():raise HTTPException(422,'normal train split missing')
    run_id='ccifps_'+uuid.uuid4().hex;folder=BUNDLE_ROOT/run_id;folder.mkdir(parents=True)
    atomic_json(folder/'manifest.json',{'status':'running','category':category,'run_id':run_id})
    env=dict(os.environ,HF_HUB_OFFLINE='1',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4')
    env['PYTHONPATH']=str(ROOT);env['CUDA_VISIBLE_DEVICES']=os.environ.get('ARIA_CCIFPS_GPU_UUID','')
    with (folder/'worker.log').open('wb') as log:
        worker=subprocess.Popen([sys.executable,'-m','aria.perception.ccifps_backend','--run-id',run_id,'--category',category],cwd=folder,env=env,stdout=log,stderr=subprocess.STDOUT)
    from server.ws import broadcast_threadsafe
    loop=asyncio.get_running_loop()
    broadcast_threadsafe(loop,{'type':'training','status':'running','run_id':run_id,'category':category,'selector':'ccifps'})
    def finish():
        code=worker.wait()
        try: state=json.loads((folder/'manifest.json').read_text()).get('status')
        except (ValueError,OSError): state='failed'
        if code and state=='running':
            atomic_json(folder/'manifest.json',{'status':'failed','run_id':run_id,'error':f'worker exit {code}'})
        broadcast_threadsafe(loop,{'type':'training','status':'done' if code==0 and state=='completed' else 'error','run_id':run_id,'category':category,'selector':'ccifps'})
    threading.Thread(target=finish,daemon=True).start()
    return {'ok':True,'run_id':run_id,'pid':worker.pid,'status':'running'}

@router.get('/runs/{run_id}')
def status(run_id:str):
    if not re.fullmatch(r'ccifps_[a-f0-9]{32}',run_id):raise HTTPException(422,'invalid run ID')
    path=BUNDLE_ROOT/run_id/'manifest.json'
    if not path.exists():raise HTTPException(404,'run not found')
    return json.loads(path.read_text())

@router.post('/analyze')
async def analyze(payload:dict=Body(...)):
    from aria.inspection.detectors import CCIFPSDetector
    try:
        detector=await run_in_threadpool(CCIFPSDetector,payload.get('run_id'))
        path=Path(payload.get('path','')).resolve();roots=[(ROOT/'data').resolve(),(ROOT/'uploads').resolve()]
        if not path.is_file() or not any(r in path.parents for r in roots):raise ValueError('image outside data/uploads')
    except (ValueError,TypeError,FileNotFoundError) as e:raise HTTPException(422,str(e))
    result=await run_in_threadpool(detector.infer,str(path))
    from aria.inspection.result_encode import enrich_result
    encoded=await run_in_threadpool(enrich_result,str(path),result['heatmap'])
    return {'ok':True,'run_id':detector.manifest['run_id'],'selector':detector.manifest['selector'],'score':result['score'],'threshold':detector.tau,'verdict':result['verdict_hint'],'actual_K':len(detector.bank),**encoded}

@router.get('/runs')
def runs():
    rows=[]
    for path in sorted(BUNDLE_ROOT.glob('ccifps_*/manifest.json')):
        try:
            m=json.loads(path.read_text())
            rows.append({k:m.get(k) for k in ('run_id','category','status','actual_K','threshold')})
        except (ValueError,OSError):continue
    return {'runs':rows}
