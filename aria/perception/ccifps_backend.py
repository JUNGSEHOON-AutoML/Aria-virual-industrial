"""ARIA adapter for the actual CCIFPS-AutoML legacy hybrid feature selector.

DINO/768 features + original selector, NOT a WR50 thesis reproduction.
Run training in a fresh process; keep package imports and RNG isolated.
"""
from pathlib import Path
import hashlib,json,os,re
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
BUNDLE_ROOT=ROOT/'banks/ccifps'

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()

def atomic_json(path,value):
    path=Path(path);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)

def load_bundle(run_id):
    if not isinstance(run_id,str) or not re.fullmatch(r'ccifps_[a-f0-9]{32}',run_id):raise ValueError('invalid CCIFPS run ID')
    folder=BUNDLE_ROOT/run_id;m=json.loads((folder/'manifest.json').read_text())
    if m.get('status')!='completed':raise ValueError('CCIFPS bundle is not completed')
    if m.get('feature_contract')!='dino_vit_b8_resize224_D768':raise ValueError('incompatible feature contract')
    bank=folder/'bank.npy'
    if sha(bank)!=m['bank_sha256']:raise ValueError('CCIFPS bank hash mismatch')
    return bank,m

def _build(folder,category,feature_cache=None):
    import csv,sys,random,time,shutil,importlib.util,math
    import torch,timm
    from safetensors.torch import load_file
    from aria.perception.cmdiad_inference import DINOBackbone,preprocess_image
    from aria.perception.scorer.feature_bank import _l2,cosine_patch_scores
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);start=time.perf_counter()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',category):raise ValueError('invalid category')
    source=Path(os.environ.get('ARIA_CCIFPS_SOURCE','/userHome/userhome4/sehoon/CCIFPS-AutoML'))
    cfgpath=source/'experiments/mvtec_golden_recovery_20260914/effective_config.csv'
    config=next(r for r in csv.DictReader(cfgpath.open()) if r['class_name']==category)
    snapshot=folder/'source_snapshot';shutil.copytree(source/'src/patchcore',snapshot/'patchcore',ignore=shutil.ignore_patterns('__pycache__'))
    observer_src=source/'experiments/ccifps_gpu2_followup_20260916_01/selection_observer.py';shutil.copy2(observer_src,snapshot/'selection_observer.py')
    sys.path.insert(0,str(snapshot));import patchcore.sampler as sam
    spec=importlib.util.spec_from_file_location('aria_ccifps_observer',snapshot/'selection_observer.py');obsmod=importlib.util.module_from_spec(spec);spec.loader.exec_module(obsmod)
    # Honor a single explicitly assigned GPU; otherwise CPU, never auto-occupy another user's device.
    device='cuda:0' if os.environ.get('CUDA_VISIBLE_DEVICES','').startswith('GPU-') and torch.cuda.is_available() else 'cpu'
    if os.environ.get('CUDA_VISIBLE_DEVICES','').startswith('GPU-') and device=='cpu':raise RuntimeError('assigned GPU is unavailable; no silent CPU fallback')
    torch.set_num_threads(4)
    images=sorted((ROOT/'data'/category/'train/good').glob('*.png'))
    if len(images)<5:raise ValueError('at least five normal train images required')
    perm=np.random.default_rng(20260916).permutation(len(images));ncal=math.ceil(len(images)*.2);cal=perm[:ncal];fit=perm[ncal:]
    weights=next((Path.home()/'.cache/huggingface/hub/models--timm--vit_base_patch8_224.dino/snapshots').glob('*/model.safetensors'))
    model=timm.create_model('vit_base_patch8_224_dino',pretrained=False);model.load_state_dict(load_file(str(weights)),strict=True)
    feature_seconds=0.0
    if feature_cache is not None:
        # Internal pilot-only cache. Input IDs and hashes are checked by its caller.
        feats=np.asarray(feature_cache,dtype='f');assert feats.shape==(len(images),784,768)
    else:
        eng=DINOBackbone.__new__(DINOBackbone);eng.model=model.eval().to(device);eng.device=device
        t=time.perf_counter();feats=np.stack([eng.extract_features(preprocess_image(str(p))).numpy() for p in images]);feature_seconds=time.perf_counter()-t
    np.save(folder/'train_features.npy',feats)
    train=feats[fit].reshape(-1,768)
    sampler=sam.ClassConditionedIrredundantSampler(device=torch.device(device),tau=float(config['tau']),max_memory_size=int(config['budget']),use_hybrid=True,class_name=category,sampling_type=config['sampler'],dimension_to_project_features_to=128)
    if int(int(config['budget'])*float(config['stage1_fraction']))>=len(train):raise ValueError('dataset too small for preserved class candidate budget; no silent fallback')
    random.seed(0);np.random.seed(0);torch.manual_seed(0)
    if device.startswith('cuda'):torch.cuda.manual_seed_all(0)
    t=time.perf_counter()
    with obsmod.SelectionObserver(sam) as observer:result=sampler.run(train)
    selected,weights_selection=result;observed=observer.materialize();idx=observed['indices']
    np.testing.assert_array_equal(selected,train[idx])
    selection_seconds=time.perf_counter()-t
    bank=_l2(np.asarray(selected,dtype='f'));np.save(folder/'bank.npy',bank);np.save(folder/'selected_indices.npy',idx);np.save(folder/'stage1_indices.npy',observed['stage1_indices']);np.save(folder/'projection.npy',observed['projection']);np.save(folder/'selection_weights.npy',weights_selection)
    scores=np.array([cosine_patch_scores(feats[i],bank).max() for i in cal]);threshold=float(scores.mean()+3*scores.std(ddof=0));np.save(folder/'calibration_scores.npy',scores)
    with (folder/'memory_provenance.csv').open('w') as f:
        writer=csv.writer(f);writer.writerow(['bank_index','fit_feature_id','train_image','grid_row','grid_col'])
        for j,i in enumerate(idx):writer.writerow([j,int(i),str(images[fit[i//784]].relative_to(ROOT/'data')),int(i%784//28),int(i%28)])
    m=dict(status='completed',run_id=folder.name,category=category,selector='ClassConditionedIrredundantSampler',selection_branch='original legacy hybrid; scheduled tau and coupled budget preserved',feature_contract='dino_vit_b8_resize224_D768',feature_layers='DINO last patch tokens; NOT WR50 recovery layers',search='normalized cosine k1; inference density off',threshold=threshold,threshold_source='held-out normal train mean+3 population SD; strict >',fit_ids=[str(images[i].relative_to(ROOT/'data')) for i in fit],calibration_ids=[str(images[i].relative_to(ROOT/'data')) for i in cal],input_hashes={str(p.relative_to(ROOT/'data')):sha(p) for p in images},class_config=config,actual_P=len(observed['stage1_indices']),actual_K=len(bank),D=768,bank_bytes=bank.nbytes,bank_sha256=sha(folder/'bank.npy'),source_import=str(sam.__file__),selector_sha256=sha(snapshot/'patchcore/sampler.py'),observer_sha256=sha(snapshot/'selection_observer.py'),weight_path=str(weights),weight_sha256=sha(weights),feature_sha256=sha(folder/'train_features.npy'),projection_sha256=sha(folder/'projection.npy'),selected_sha256=sha(folder/'selected_indices.npy'),feature_seconds=feature_seconds,feature_cache_reused=feature_cache is not None,selection_seconds=selection_seconds,wall_seconds=time.perf_counter()-start,device=device,gpu_uuid=os.environ.get('CUDA_VISIBLE_DEVICES'),pid=os.getpid(),seed=0,split_seed=20260916)
    atomic_json(folder/'manifest.json',m);return m

def build(folder,category,feature_cache=None):
    import fcntl
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    device=os.environ.get('CUDA_VISIBLE_DEVICES','cpu') or 'cpu'
    if device != 'cpu' and not re.fullmatch(r'GPU-[A-Za-z0-9-]+',device):raise ValueError('assign one GPU UUID per CCIFPS worker')
    lockname=hashlib.sha256(device.encode()).hexdigest()[:16]
    with (folder.parent/('.worker_'+lockname+'.lock')).open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _build(folder,category,feature_cache)

if __name__=='__main__':
    import argparse,traceback
    ap=argparse.ArgumentParser();ap.add_argument('--run-id',required=True);ap.add_argument('--category',required=True);a=ap.parse_args()
    if not re.fullmatch(r'ccifps_[a-f0-9]{32}',a.run_id):raise ValueError('invalid run ID')
    folder=BUNDLE_ROOT/a.run_id
    try:build(folder,a.category)
    except Exception as e:
        atomic_json(folder/'manifest.json',dict(status='failed',error=str(e),traceback=traceback.format_exc()));raise
