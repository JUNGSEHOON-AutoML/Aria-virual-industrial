"""L1 CPU-only report adapter: reuse verified P1 maps, EvidenceStore and posthoc.
GT is consumed only by this offline audit/evaluation; never detector input.
"""
import csv,json,os,tempfile,shutil
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/tmp/cnotta-matplotlib')
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from aria.dashboard import store
from aria.simulation.des.evidence import EvidenceStore
from aria.simulation.dt.posthoc import reconstruct_b
ROOT=store.ROOT;OUT=ROOT/'docs/reports/vision_audit';DATA=ROOT/'data'
CLASSES=('bottle','screw','carpet');MODELS=('coreset','ccifps','random_same_k')
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def crop(path):
 im=Image.open(path).convert('RGB');w,h=im.size
 size=(256,int(256*h/w)) if w<=h else (int(256*w/h),256)
 im=im.resize(size,Image.Resampling.BILINEAR);left=round((size[0]-224)/2);top=round((size[1]-224)/2)
 return im.crop((left,top,left+224,top+224))
def fit_mask(normal_ids):
 # A fixed foreground proxy fitted exclusively on normal fit images, not test/GT.
 arrays=[np.asarray(crop(DATA/iid)) for iid in normal_ids]
 borders=np.concatenate([np.concatenate([a[0],a[-1],a[:,0],a[:,-1]]) for a in arrays])
 background=np.median(borders,axis=0);hist=np.zeros(443,dtype=np.int64)
 for a in arrays:hist+=np.bincount(np.linalg.norm(a.astype(float)-background,axis=2).astype(int).ravel(),minlength=443)[:443]
 probability=hist/hist.sum();omega=np.cumsum(probability);mu=np.cumsum(probability*np.arange(443));variance=(mu[-1]*omega-mu)**2/np.maximum(omega*(1-omega),1e-15);threshold=int(np.argmax(variance))
 return background,threshold

def build():
 OUT.mkdir(parents=True,exist_ok=True);catalog=store.catalog();summary=[]
 for cls in CLASSES:
  source=store.P1/cls;target=OUT/cls;target.mkdir(exist_ok=True)
  lock=json.loads((source/'complete.json').read_text());protocol=json.loads((source/'protocol.json').read_text());verified={}
  def check(relative):
   digest=store.sha(source/relative)
   if lock['files'].get(relative)!=digest:raise ValueError('P1 integrity failure '+relative)
   verified[relative]=digest
  for f in ('protocol.json','evaluation_gt.npy','gt_labels.csv'):check(f)
  gt=np.load(source/'evaluation_gt.npy',mmap_mode='r');background,mask_threshold=fit_mask(protocol['fit_ids'])
  reports={};lookups={}
  for model in MODELS:
   folder=source/model;dest=target/model;dest.mkdir(exist_ok=True)
   for f in ('per_image.csv','predictions.csv','common_maps.npy','raw_patch_scores.npy'):check(model+'/'+f)
   raw=list(csv.DictReader((folder/'per_image.csv').open()));rows=[dict(image_id=r['image_id'],image_sha256=r['image_sha256'],score=float(r['score']),threshold=float(r['threshold']),verdict=r['verdict'],is_defect=int(r['is_defect']),defect_type=r['image_id'].split('/')[2]) for r in raw]
   assert [r['image_id'] for r in rows]==protocol['test_ids']
   maps=np.load(folder/'common_maps.npy',mmap_mode='r');patches=np.load(folder/'raw_patch_scores.npy',mmap_mode='r');assert maps.shape==(len(rows),224,224)
   assert all(r['verdict']==('NG' if r['score']>r['threshold'] else 'OK') for r in rows)
   normal=[r['score'] for r in rows if not r['is_defect']];defect=[r['score'] for r in rows if r['is_defect']];threshold=rows[0]['threshold'];assert all(r['threshold']==threshold for r in rows)
   bins=np.linspace(min(normal+defect),max(normal+defect),31);nh,_=np.histogram(normal,bins);dh,_=np.histogram(defect,bins)
   lo=max(min(normal),min(defect));hi=min(max(normal),max(defect));overlap={'definition':'intersection of empirical normal/defect score ranges (inclusive)','range':[lo,hi] if lo<=hi else None,'normal_count':sum(lo<=v<=hi for v in normal),'defect_count':sum(lo<=v<=hi for v in defect)}
   fp=[i for i,r in enumerate(rows) if not r['is_defect'] and r['verdict']=='NG'];fn=[i for i,r in enumerate(rows) if r['is_defect'] and r['verdict']=='OK'];fp=sorted(fp,key=lambda i:(-rows[i]['score'],rows[i]['image_id']))
   counts={name:sum(bool(r['is_defect'])==defective and (r['verdict']=='NG')==ng for r in rows) for name,defective,ng in [('TP',True,True),('FN',True,False),('FP',False,True),('TN',False,False)]}
   types=[]
   for name in sorted({r['defect_type'] for r in rows}):
    subset=[r for r in rows if r['defect_type']==name];types.append({'type':name,'images':len(subset),'ng_count':sum(r['verdict']=='NG' for r in subset),'detection_rate':sum(r['verdict']=='NG' for r in subset)/len(subset),'mean_score':float(np.mean([r['score'] for r in subset]))})
   response=[]
   for i in fp:
    image=np.asarray(crop(DATA/rows[i]['image_id']));mask=np.linalg.norm(image.astype(float)-background,axis=2)>mask_threshold;y,x=np.unravel_index(int(np.argmax(patches[i])),(28,28));py,px=int((y+.5)*8),int((x+.5)*8)
    response.append({'image_id':rows[i]['image_id'],'peak_patch':[int(x),int(y)],'peak_on_background_proxy':not bool(mask[py,px]),'foreground_fraction':float(mask.mean())})
   chosen=fp[:8]+fn;assert len(chosen)<200 # Existing EvidenceStore retention is not reached.
   evidence=EvidenceStore(dest);gallery=[]
   with tempfile.TemporaryDirectory(prefix='cnotta-audit-crop-') as temp:
    for i in chosen:
     row=rows[i];original=DATA/row['image_id'];assert store.sha(original)==row['image_sha256'];path=Path(temp)/'view.png';crop(original).save(path)
     meta=evidence.save(path,{'heatmap':maps[i]},{'image_id':row['image_id'],'score':row['score'],'threshold':row['threshold'],'verdict':row['verdict'],'selector':model})
     asset=evidence.directory/meta['id'];shutil.copyfile(original,asset/'source.png');Image.fromarray(np.uint8(np.squeeze(gt[i])>0)*255).save(asset/'gt_mask.png')
     fg=np.linalg.norm(np.asarray(crop(original)).astype(float)-background,axis=2)>mask_threshold;Image.fromarray(np.uint8(fg)*255).save(asset/'object_proxy.png')
     x,y=np.unravel_index(int(np.argmax(patches[i])),(28,28))[::-1];prefix=f'/api/dt/vision/{cls}/{model}/assets/{meta["id"]}'
     item={**row,'kind':'FP' if i in fp else 'FN','evidence_id':meta['id'],'peak_patch':[int(x),int(y)],'smoothed_peak_uv':meta['peak_uv'],'source_url':prefix+'/source.png','original_url':prefix+'/original.png','overlay_url':prefix+'/overlay.png','mask_url':prefix+'/gt_mask.png','object_proxy_url':prefix+'/object_proxy.png'};gallery.append(item)
   impact=[]
   for run in catalog:
    if run['source']!='pilot' or run['class_name']!=cls or run['selector']!=model:continue
    loaded=store.load(run['run_id']);_,m,n,_=reconstruct_b(loaded['parts'],loaded['gt'],seed=loaded['config']['seed']);den=n['parts_denominator']
    impact.append({'run_id':run['run_id'],'cell':run['cell'],'speed':run['speed'],'seed':run['seed'],'latency_mode':run['latency_mode'],'source_complete_sha256':run['complete_hash'],'parts_denominator':den,'reinspection_per_1000':n['ng_per_1000'],'false_positives_per_1000':n['false_positives_per_1000'],'escaped_defects':m['escaped_defects'],'escaped_defects_per_1000':m['escaped_defects']/den*1000 if den else None})
   fig,ax=plt.subplots(figsize=(7,3));ax.stairs(nh,bins,label='Normal',color='#10295E');ax.stairs(dh,bins,label='Defect',color='#5E66F4');ax.axvline(threshold,color='#E5484D',label='Locked threshold');ax.set(xlabel='P1 score',ylabel='Images',title=f'{cls} / {model}');ax.legend();fig.tight_layout();fig.savefig(dest/'distribution.svg');plt.close(fig)
   report={'class':cls,'model':model,'images':len(rows),'counts':counts,'threshold':threshold,'histogram':{'edges':bins.tolist(),'normal':nh.tolist(),'defect':dh.tolist()},'overlap':overlap,'defect_types':types,'gallery':gallery,'gallery_scope':{'fp_top_k':8,'fp_total':len(fp),'fn_all':len(fn)},'background_response':{'numerator':sum(r['peak_on_background_proxy'] for r in response),'denominator':len(fp),'images':response},'process_impact':impact}
   write(dest/'report.json',report);reports[model]=report;lookups[model]={r['image_id']:r for r in rows};summary.append({'class':cls,'model':model,**counts})
   lines=[f'# {cls} · {model} 비전 진단','',f'이미지 {len(rows)}개. TP {counts["TP"]}, FN {counts["FN"]}, FP {counts["FP"]}, TN {counts["TN"]}. 고정 임계값 {threshold}.','', '## 점수 분포','![score distribution](distribution.svg)','',f'정상/불량 점수 범위의 교집합(경계 포함): {overlap}. 확률적 중첩률이나 원인 판정이 아니다.','', '## 결함 유형별 성능','|유형|이미지|NG|탐지율(정상은 오탐률)|평균 점수|','|---|---:|---:|---:|---:|']
   lines += [f'|{t["type"]}|{t["images"]}|{t["ng_count"]}|{t["detection_rate"]:.6f}|{t["mean_score"]:.9f}|' for t in types]
   lines += ['','## 배경 반응과 한계',f'오탐의 최대 raw 패치 반응이 배경 proxy에 있었던 비율: {report["background_response"]["numerator"]}/{len(fp)}. 분모 0은 해당 없음.', '정상 fit 이미지의 테두리 RGB 중앙값과의 색 거리 히스토그램에 Otsu를 적용한 고정 임계값이다. 테스트 이미지/GT로 튜닝하지 않았다. 이는 물체 GT가 아닌 색 기반 proxy다. 물체와 배경의 색이 비슷하거나 질감이 화면을 채우는 carpet에서는 특히 신뢰할 수 없다. 배경 간섭의 인과관계를 단정하지 않는다.','', '## 공정 영향','[600,3600] 본 라인 출구 전체(보류 포함)를 분모로 기존 reconstruct_b 결과를 인용한다. 사람 1명·30초·민감도/특이도 1 assumed. 파일럿 조건이 서로 달라 모델 효과의 직접 비교가 아니다.','```json',json.dumps(impact,ensure_ascii=False,indent=2),'```','','## 오탐·미탐 갤러리', '오탐은 점수 상위 8개, 미탐은 전부. 원본 외 비교 이미지는 짧은 변 256 resize → 중앙 224 crop 좌표로 정렬했다. GT 마스크는 보고서 표시 전용이다. 히트맵은 기존 EvidenceStore의 이미지별 min/max 상대 표시다.']
   for g in gallery:
    base='outputs/factory-evidence/'+g['evidence_id'];lines += ['',f'### {g["kind"]} · {g["image_id"]}',f'점수 {g["score"]} · 임계값 {g["threshold"]} · 판정 {g["verdict"]} · 최대 패치 {g["peak_patch"]}',f'[원본]({base}/source.png) · ![입력 시야]({base}/original.png) ![히트맵]({base}/overlay.png) ![GT]({base}/gt_mask.png) ![물체 proxy]({base}/object_proxy.png)']
   lines += ['','## 모델 간 차이','클래스 상위 REPORT.md와 report.json의 disagreements에 세 모델의 점수·판정을 같은 이미지 ID로 대조했다.']
   (dest/'REPORT.md').write_text('\n'.join(lines)+'\n');print(cls,model,counts,flush=True)
  disagreements=[]
  for iid in protocol['test_ids']:
   model_rows={m:{k:lookups[m][iid][k] for k in ('score','threshold','verdict')} for m in MODELS}
   if len({r['verdict'] for r in model_rows.values()})>1:disagreements.append({'image_id':iid,'models':model_rows})
  result={'schema_version':1,'class':cls,'source':'verified P1; existing saved maps; CPU only; no new inference','models':reports,'disagreements':disagreements,'object_proxy':{'method':'normal-fit border RGB median; global Otsu on RGB distance; foreground distance > threshold','normal_fit_images':len(protocol['fit_ids']),'background_rgb':background.tolist(),'distance_threshold':mask_threshold,'limit':'not semantic ground truth; unsuitable for equal-colour objects/background and full-frame textures; no causal claim'},'source_hashes':verified,'p1_complete_sha256':store.sha(source/'complete.json')}
  write(target/'report.json',result)
  lines=[f'# {cls} 비전 분석','', 'P1 저장 점수·맵을 CPU로 분석했다. 새 추론·임계값 변경·테스트 GT 기반 튜닝은 없다. 모델별 7개 분석 항목과 갤러리는 아래에 있다.','']+[f'- [{m}]({m}/REPORT.md)' for m in MODELS]+['','## 모델 간 판정 차이',f'{len(disagreements)}개 이미지. 모든 점수·임계값·판정은 CSV 원값이다.','|이미지|coreset 점수/판정|ccifps 점수/판정|random_same_k 점수/판정|','|---|---|---|---|']
  lines += ['|'+d['image_id']+'|'+'|'.join(str(d['models'][m]['score'])+'/'+d['models'][m]['verdict'] for m in MODELS)+'|' for d in disagreements]
  lines += ['','화면은 이 폴더 report.json의 동일 바이트를 읽는다. 원본·히트맵·GT 그림은 로컬 전용이며 Git에 포함하지 않는다.'];(target/'REPORT.md').write_text('\n'.join(lines)+'\n')
 write(OUT/'index.json',{'classes':list(CLASSES),'models':list(MODELS),'summary':summary})
if __name__=='__main__':build()
