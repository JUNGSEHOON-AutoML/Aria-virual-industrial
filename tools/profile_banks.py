"""ARIA DT P1: a NEW WR50 comparison, not reconstruction of thesis numbers.

Run in a fresh process with one GPU UUID and the research Python environment.
Original caches/sources are read-only; every output belongs to --out/class_name.
"""
import argparse,csv,hashlib,importlib.util,json,math,os,random,sys,time,shutil,fcntl,platform
from pathlib import Path

RESEARCH=Path(os.environ.get('ARIA_CCIFPS_SOURCE','/userHome/userhome4/sehoon/CCIFPS-AutoML'))
REFERENCE=RESEARCH/'experiments/official_patchcore_15class_20260916_01'
ARIA=Path(__file__).resolve().parents[1]

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()

def write(p,x):
    p=Path(p);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(x,indent=2,allow_nan=False));tmp.replace(p)

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def csvwrite(p,rows):
    with Path(p).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def run(a):
    import numpy as np
    import torch,faiss
    torch.set_num_threads(4);faiss.omp_set_num_threads(4)
    gpu=os.environ.get('CUDA_VISIBLE_DEVICES','')
    if not gpu.startswith('GPU-') or ',' in gpu:raise ValueError('Assign exactly one GPU UUID')
    if not torch.cuda.is_available() or not hasattr(faiss,'StandardGpuResources'):raise RuntimeError('FAISS GPU required; no CPU substitution')
    out=a.out/a.class_name;out.mkdir(parents=True,exist_ok=False)
    # Lock across profiler jobs, not other users. Never terminate other GPU processes.
    lock=(a.out/('gpu-'+hashlib.sha256(gpu.encode()).hexdigest()[:16]+'.lock')).open('w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    started=time.perf_counter()
    try:
        source_check=json.loads((REFERENCE/'official_source_check.json').read_text())
        for row in source_check['files'].values():
            if sha(row['path'])!=row['expected_snapshot_sha256']:raise ValueError('Official source hash drift: '+row['path'])
        w=module('aria_dt_official_reference',REFERENCE/'official_worker.py')
        cm=json.loads((REFERENCE/'features'/a.class_name/'cache_manifest.json').read_text())
        im=json.loads((REFERENCE/'features'/a.class_name/'input_manifest.json').read_text())
        cp=REFERENCE/'features'/a.class_name
        for file,key in [('train_features.npy','feature_cache_sha256'),('query_features.npy','query_cache_sha256')]:
            if sha(cp/file)!=cm[key]:raise ValueError('Cache hash mismatch: '+file)
        if cm['layers']!=['layer2','layer3'] or cm['dtype']!='float32' or cm['target_embed_dimension']!=1024:raise ValueError('Feature contract mismatch')
        for key,hashkey in [('train_ids','train_image_sha256'),('test_ids','test_image_sha256')]:
            if len(im[key])!=len(im[hashkey]):raise ValueError('Input hash count mismatch')
            for iid,h in zip(im[key],im[hashkey]):
                if sha(w.DATA/iid)!=h:raise ValueError('Image hash mismatch: '+iid)
        for iid,h in zip(im['test_mask_ids'],im['mask_sha256']):
            if iid is not None and sha(w.DATA/iid)!=h:raise ValueError('GT hash mismatch')
        tr=np.load(cp/'train_features.npy',mmap_mode='r');q=np.load(cp/'query_features.npy',mmap_mode='r')
        if tr.shape!=(len(im['train_ids'])*784,1024) or q.shape!=(len(im['test_ids'])*784,1024):raise ValueError('Cache shape mismatch')
        # Split BEFORE selecting any bank, by image rather than patch. Fixed without test feedback.
        perm=np.random.default_rng(20260916).permutation(len(im['train_ids']));ncal=math.ceil(.2*len(perm));cal=perm[:ncal];fit=perm[ncal:]
        np.save(out/'fit_image_indices.npy',fit);np.save(out/'calibration_image_indices.npy',cal)
        cfg=next(x for x in csv.DictReader((RESEARCH/'experiments/mvtec_golden_recovery_20260914/effective_config.csv').open()) if x['class_name']==a.class_name)
        src=out/'source_snapshot';src.mkdir()
        for name,path in [('ccifps_sampler.py',RESEARCH/'src/patchcore/sampler.py'),('selection_observer.py',RESEARCH/'experiments/ccifps_gpu2_followup_20260916_01/selection_observer.py'),('official_worker.py',REFERENCE/'official_worker.py'),('evaluator.py',RESEARCH/'src/patchcore/metrics.py')]:
            shutil.copyfile(path,src/name)
        lockeval=json.loads((REFERENCE/'EVALUATOR_LOCK.json').read_text())
        if sha(src/'evaluator.py')!=lockeval['evaluator_sha256']:raise ValueError('Evaluator hash mismatch')
        write(out/'protocol.json',dict(series='aria_dt_wr50_new_comparison',thesis_reproduction=False,class_name=a.class_name,bank_seed=0,split_seed=20260916,
            fit_ids=[im['train_ids'][i] for i in fit],calibration_ids=[im['train_ids'][i] for i in cal],test_ids=im['test_ids'],
            features=cm,selection_config=cfg,all_methods_layers=['layer2','layer3'],carpet_layer_override='controlled common L2+3; not recovery L1+2+3',
            search='raw squared L2 k1; inference density off',sigma=2,threshold='normal holdout mean + 3 * population SD; strict >',
            official_percentage=.1,random_same_k='same actual K as CCIFPS; without replacement',
            source_hashes={p.name:sha(p) for p in src.iterdir()},official_source_check_sha256=sha(REFERENCE/'official_source_check.json'),
            profile=dict(warmup=50,samples=1000,input='normal holdout round-robin; image bytes preloaded, includes decode/transform, H2D/embed/D2H, search, sigma2 map',numpy_query_chunk=256,numpy_bank_chunk=4096,threads=4),
            comparison='whole-method with common scoring; random is same-K only to CCIFPS',sim=1))
        write(out/'environment.json',dict(python=sys.version,executable=sys.executable,torch=torch.__version__,numpy=np.__version__,faiss=faiss.__version__,faiss_import=faiss.__file__,gpu_uuid=gpu,gpu_name=torch.cuda.get_device_name(0),pid=os.getpid(),threads=4,platform=platform.platform(),official_import=w.pc.__file__))
        # Initialize GPU before sampling and verify cache against actual extraction.
        resources=faiss.StandardGpuResources();resources.setTempMemory(128*1024*1024)
        tiny=faiss.GpuIndexFlatL2(resources,3);tiny.add(np.eye(3,dtype='float32'));assert np.max(tiny.search(np.eye(3,dtype='float32'),1)[0])==0
        model=w.make_model()
        if w.tensor_hash(model.backbone)!=cm['weight_sha256']:raise ValueError('Weight tensor hash mismatch')
        train_ds=w.dataset(a.class_name,w.mvtec.DatasetSplit.TRAIN);test_ds=w.dataset(a.class_name,w.mvtec.DatasetSplit.TEST)
        if w.ids(train_ds)!=im['train_ids'] or w.ids(test_ds)!=im['test_ids']:raise ValueError('Dataset order mismatch')
        errors=[]
        with torch.no_grad():
            for idx in [int(fit[0]),int(cal[0])]:
                x=train_ds[idx]['image'].unsqueeze(0).to(w.DEVICE);live=np.asarray(model._embed(x),dtype='float32');cached=np.asarray(tr[idx*784:(idx+1)*784])
                errors.append(float(np.max(np.abs(live-cached))))
                if not np.allclose(live,cached,rtol=1e-4,atol=1e-4):raise ValueError('Live feature/cache mismatch')
        write(out/'preflight.json',dict(status='passed',cache_live_max_absolute_errors=errors,cache_tolerance=dict(atol=1e-4,rtol=1e-4),elapsed_s=time.perf_counter()-started))
        if a.preflight_only:return
        sam=module('aria_dt_ccifps_sampler',src/'ccifps_sampler.py');obs=module('aria_dt_selection_observer',src/'selection_observer.py')
        features=np.asarray(tr).reshape(-1,784,1024)[fit].reshape(-1,1024)
        cals=np.asarray(tr).reshape(-1,784,1024)[cal]
        def seeds():
            random.seed(0);np.random.seed(0);torch.manual_seed(0);torch.cuda.manual_seed_all(0)
        banks={};summaries=[]
        for name in ['ccifps','coreset','random_same_k']:
            d=out/name;d.mkdir();seeds();t=time.perf_counter();w.sync()
            if name=='ccifps':
                s=sam.ClassConditionedIrredundantSampler(device=w.DEVICE,tau=float(cfg['tau']),max_memory_size=int(cfg['budget']),use_hybrid=True,class_name=a.class_name,sampling_type=cfg['sampler'],dimension_to_project_features_to=128)
                if int(int(cfg['budget'])*float(cfg['stage1_fraction']))>=len(features):raise ValueError('Insufficient fit features for original candidate budget')
                with obs.SelectionObserver(sam) as observer:bank,_=s.run(features)
                o=observer.materialize();indices=o['indices'];projection=o['projection'];stage1=o['stage1_indices']
            elif name=='coreset':
                s=w.sam.ApproximateGreedyCoresetSampler(.1,w.DEVICE)
                with obs.SelectionObserver(w.sam) as observer:bank=s.run(features)
                o=observer.materialize();indices=o['indices'];projection=o['projection'];stage1=o['stage1_indices']
            else:
                indices=np.random.default_rng(0).choice(len(features),len(banks['ccifps']),replace=False);bank=features[indices];projection=np.empty((0,0),dtype='float32');stage1=indices
            w.sync();selection_s=time.perf_counter()-t;bank=np.asarray(bank,dtype='float32')
            if not np.array_equal(bank,features[indices]):raise ValueError('Selected index observer mismatch')
            banks[name]=bank
            for file,value in [('bank',bank),('selected_fit_indices',indices),('stage1_indices',stage1),('projection',projection)]:np.save(d/(file+'.npy'),value)
            csvwrite(d/'memory_provenance.csv',[dict(bank_index=j,image_id=im['train_ids'][fit[int(i)//784]],grid_row=int(i)%784//28,grid_col=int(i)%28) for j,i in enumerate(indices)])
            summary=dict(selector=name,K=len(bank),D=1024,dtype='float32',bank_bytes=bank.nbytes,selection_s=selection_s,bank_sha256=sha(d/'bank.npy'));summaries.append(summary)
            write(d/'bank_manifest.json',summary)
        csvwrite(out/'bank_summary.csv',summaries)
        gt,gtids,_=w.common_gt(test_ds);np.save(out/'evaluation_gt.npy',gt)
        csvwrite(out/'gt_labels.csv',[dict(image_id=iid,is_defect=int(test_ds.data_to_iterate[i][1]!='good'),defect_type=test_ds.data_to_iterate[i][1]) for i,iid in enumerate(gtids)])
        from PIL import Image
        import io
        image_bytes=[(w.DATA/im['train_ids'][i]).read_bytes() for i in cal]
        # All image tensors use precisely the reference dataset transform.
        transform=train_ds.transform_img
        seg=w.common.RescaleSegmentor(w.DEVICE,224);seg.smoothing=2
        metrics=module('aria_dt_locked_evaluator',src/'evaluator.py')
        totals=[]
        for name,bank in banks.items():
            d=out/name;bn=np.sum(bank*bank,axis=1)
            index=faiss.GpuIndexFlatL2(resources,1024);index.add(bank)
            def numpy_search(x):
                ds=[];nn=[]
                for start in range(0,len(x),256):
                    a=np.ascontiguousarray(x[start:start+256]);best=np.full(len(a),np.inf,dtype='float32');ix=np.zeros(len(a),dtype='int64');an=np.sum(a*a,axis=1)[:,None]
                    for b in range(0,len(bank),4096):
                        distances=np.maximum(an+bn[None,b:b+4096]-2*(a@bank[b:b+4096].T),0);local=distances.argmin(1);v=distances[np.arange(len(a)),local];take=v<best;best[take]=v[take];ix[take]=b+local[take]
                    ds.append(best);nn.append(ix)
                return np.concatenate(ds),np.concatenate(nn)
            def gpu_search(x):
                distances,idx=index.search(np.ascontiguousarray(x,dtype='float32'),1);return distances[:,0],idx[:,0]
            a0,b0=gpu_search(cals[0]);a1,b1=numpy_search(cals[0])
            if not np.allclose(a0,a1,atol=1e-3,rtol=1e-4):raise ValueError('GPU/NumPy squared L2 mismatch')
            write(d/'search_regression.json',dict(max_distance_error=float(np.max(np.abs(a0-a1))),nearest_index_disagreements=int(np.sum(b0!=b1)),atol=1e-3,rtol=1e-4))
            cal_scores=np.asarray([gpu_search(x)[0].max() for x in cals]);threshold=float(cal_scores.mean()+3*cal_scores.std(ddof=0));np.save(d/'calibration_scores.npy',cal_scores)
            rows=[];maps=[];raw=[];nearest=[]
            for i,iid in enumerate(im['test_ids']):
                ds,nn=gpu_search(np.asarray(q[i*784:(i+1)*784]));score=float(ds.max());pm=seg.convert_to_segmentation(ds.reshape(1,28,28))[0]
                maps.append(pm);raw.append(ds);nearest.append(nn)
                rows.append(dict(image_id=iid,image_sha256=im['test_image_sha256'][i],bundle_id=f'{a.class_name}_{name}_{sha(d/"bank.npy")[:12]}',selector=name,bank_k=len(bank),score=score,threshold=threshold,verdict='NG' if score>threshold else 'OK'))
            csvwrite(d/'predictions.csv',rows) # Engine input: intentionally no GT columns.
            csvwrite(d/'per_image.csv',[dict(row,is_defect=int(test_ds.data_to_iterate[i][1]!='good')) for i,row in enumerate(rows)])
            np.save(d/'raw_patch_scores.npy',raw);np.save(d/'nearest_bank_indices.npy',nearest);np.save(d/'common_maps.npy',np.asarray(maps,dtype='float32'))
            pm=metrics.compute_pixelwise_retrieval_metrics(np.asarray(maps),gt)
            write(d/'pixel_metrics.json',{k:float(v) if np.isscalar(v) else v for k,v in pm.items()})
            for backend,search in [('faiss_gpu',gpu_search),('numpy_chunk',numpy_search)]:
                stages={k:[] for k in ['pre','feat','search','post']};total=[]
                with torch.no_grad():
                    for rep in range(1050):
                        w.sync();start=time.perf_counter();imx=Image.open(io.BytesIO(image_bytes[rep%len(image_bytes)])).convert('RGB');x=transform(imx).unsqueeze(0);t1=time.perf_counter()
                        feats=np.asarray(model._embed(x.to(w.DEVICE)),dtype='float32');w.sync();t2=time.perf_counter()
                        ds,_=search(feats);w.sync();t3=time.perf_counter()
                        seg.convert_to_segmentation(ds.reshape(1,28,28));w.sync();t4=time.perf_counter()
                        if rep>=50:
                            for k,v in zip(stages,[(t1-start)*1000,(t2-t1)*1000,(t3-t2)*1000,(t4-t3)*1000]):stages[k].append(v)
                            total.append((t4-start)*1000)
                        if rep in (49,549,1049):print(a.class_name,name,backend,'sample',rep+1,flush=True)
                profile=dict(schema_version=1,source='measured',bundle_id=rows[0]['bundle_id'],selector=name,bank_k=len(bank),hardware=f'{torch.cuda.get_device_name(0)} {gpu}; {backend}; CPU threads=4',warmup=50,total_ms=total,stages_ms=stages)
                write(d/f'latency_profile_{backend}.json',profile)
                totals.append(dict(selector=name,backend=backend,samples=len(total),p50_ms=float(np.percentile(total,50)),p95_ms=float(np.percentile(total,95)),p99_ms=float(np.percentile(total,99)),threshold=threshold))
            print(a.class_name,name,'completed',flush=True)
        csvwrite(out/'latency_summary.csv',totals)
        write(out/'complete.json',dict(status='completed',wall_seconds=time.perf_counter()-started,files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}))
    except Exception as exc:
        import traceback
        write(out/'failure.json',dict(status='failed',error=str(exc),traceback=traceback.format_exc(),wall_seconds=time.perf_counter()-started));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--class-name',choices=['bottle','screw','carpet'],required=True);p.add_argument('--preflight-only',action='store_true');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);run(a)
