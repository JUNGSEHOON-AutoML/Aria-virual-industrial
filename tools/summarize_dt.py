"""Validate the fixed 7020-run inventory and report measured, paired-seed results."""
import argparse,csv,hashlib,json,math,statistics
from collections import defaultdict
from pathlib import Path
from scipy.stats import t
ROOT=Path(__file__).resolve().parents[1]
KEYS=['class_name','selector','cell','speed','latency_mode','policy','sensitivity','specificity','reinspection_s','scope']
METRICS=['throughput_per_hour','gt_good_throughput_per_hour','gt_quality','hold_ratio','FP','FN','false_positive_recovered','wrongly_discarded','escaped_defects','reinspection_queue_mean','reinspection_queue_max','reinspection_utilization','ai_utilization']+[f'cost_{kind}_fn{ratio}_per_hour' for kind in ('detection','disposition') for ratio in (5,20,100)]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def save(p,rows):
 with p.open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def stats(xs):
 n=len(xs);m=statistics.mean(xs) if n else None;sd=statistics.stdev(xs) if n>1 else None;d=float(t.ppf(.975,n-1))*sd/math.sqrt(n) if n>1 else None
 return dict(n=n,mean=m,sample_sd=sd,ci95_low=m-d if d is not None else None,ci95_high=m+d if d is not None else None)
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();out=a.out;parent=out.parent
 protocol=json.loads((out/'protocol.json').read_text());completion=json.loads((out/'completion.json').read_text())
 assert completion['completed']==completion['expected']==len(protocol['plan'])==7020
 expected={hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()[:16]:c for c in protocol['plan']}
 rows=[]
 for rid,c in expected.items():
  folder=out/'runs'/rid;done=json.loads((folder/'complete.json').read_text());assert done['lock']['config']==c and done['lock']['source_hash']==protocol['source_hash']
  for name,h in done['hashes'].items():assert sha(folder/name)==h,(rid,name)
  r=json.loads((folder/'result.json').read_text());assert r['generated']==r['completed']+r['wip'];rows.append(r)
 save(out/'verified_results.csv',rows)
 groups=defaultdict(list)
 for r in rows:groups[tuple(r[k] for k in KEYS)].append(r)
 summary=[]
 for key,rs in groups.items():
  assert sorted(r['seed'] for r in rs)==list(range(30))
  for m in METRICS:summary.append(dict(zip(KEYS,key),metric=m,**stats([r[m] for r in rs if r[m] is not None])))
 save(out/'summary_ci95.csv',summary)
 # Paired differences: same seed/class/process, CCIFPS minus actual coreset baseline.
 look={tuple(r[k] for k in KEYS)+ (r['seed'],):r for r in rows};paired=[]
 for key,rs in groups.items():
  if key[1]!='ccifps':continue
  other=list(key);other[1]='coreset'
  for m in METRICS:
   ds=[]
   for r in rs:
    b=look[tuple(other)+(r['seed'],)]
    if r[m] is not None and b[m] is not None:ds.append(r[m]-b[m])
   paired.append(dict(zip(KEYS,key),metric=m,contrast='CCIFPS minus coreset, paired seed',**stats(ds)))
 save(out/'paired_effects.csv',paired)
 # Sensitivity changes each one factor; ranking is descriptive, not an expansion trigger.
 variants=defaultdict(dict)
 for s in summary:
  if s['cell']=='inline' and s['speed']==.5 and s['latency_mode']=='profile' and s['policy']=='B':
   variant=(s['sensitivity'],s['specificity'],s['reinspection_s']);variants[(s['class_name'],s['metric'],variant)][s['selector']]=s['mean']
 ranks=[]
 for (cls,m,v),means in variants.items():
  baseline=variants[(cls,m,(1.,1.,30.))]
  def sign(x,y):return None if x is None or y is None else (0 if abs(x-y)<1e-9 else 1 if x>y else -1)
  for x,y in [('ccifps','coreset'),('ccifps','random_same_k'),('coreset','random_same_k')]:
   before=sign(baseline[x],baseline[y]);after=sign(means[x],means[y])
   ranks.append(dict(class_name=cls,metric=m,sensitivity=v[0],specificity=v[1],reinspection_s=v[2],pair=x+' vs '+y,baseline_sign=before,variant_sign=after,strict_reversal=before in (-1,1) and after==-before))
 save(out/'sensitivity_rank_changes.csv',ranks)
 status=dict(verified_runs=len(rows),main=sum(r['scope']=='main' for r in rows),sensitivity=sum(r['scope']=='sensitivity' for r in rows),groups=len(groups),all_groups_30_seeds=True,source_hash=protocol['source_hash'],wall_seconds=completion['wall_seconds'],total_worker_seconds=completion['total_worker_seconds'],strict_reversal_rows=sum(r['strict_reversal'] for r in ranks),automatic_expansion=False)
 (out/'verification.json').write_text(json.dumps(status,indent=2))
 lines=['# P5 공정 비교 결과','',f"실측 완료·해시 검증: **{len(rows):,}회** (본 실험 5,400 + 민감도 1,620).",f"전체 실행 wall-clock: {completion['wall_seconds']/3600:.3f}시간. worker별 이벤트 실행·평가 구간 시간 합(후속 parts 저장·해시 시간 제외): {completion['total_worker_seconds']/3600:.3f}시간. 병렬 시간은 알고리즘 단독 속도 우위가 아니다.",'','## 대표 조건: inline 0.5 m/s · profile','', '|클래스|모델|정책|처리량/h (평균)|95% CI|정상 출하/h|FN 평균|FP 회복 평균|', '|---|---|---|---:|---|---:|---:|---:|']
 for key,rs in groups.items():
  c=dict(zip(KEYS,key))
  if c['scope']!='main' or c['cell']!='inline' or c['speed']!=.5 or c['latency_mode']!='profile':continue
  st=stats([r['throughput_per_hour'] for r in rs]);lines.append(f"|{c['class_name']}|{c['selector']}|{c['policy']}|{st['mean']:.2f}|[{st['ci95_low']:.2f}, {st['ci95_high']:.2f}]|{statistics.mean(r['gt_good_throughput_per_hour'] for r in rs):.2f}|{statistics.mean(r['FN'] for r in rs):.2f}|{statistics.mean(r['false_positive_recovered'] for r in rs):.2f}|")
 lines+=['','## 해석 범위','', '- bottle은 실험 전에 고정한 대조군이다. 모델 차이가 작을 것이라는 예상은 결과를 바꾸거나 제외할 근거가 아니다.','- 30seed CI는 고정된 이미지 집합·모델의 DES 난수 변동이다. 독립적인 학습 30회나 새로운 이미지 모집단의 신뢰구간이 아니다.','- 정책 B는 assumed 사람 재검사 모델이다. GT는 oracle과 평가기의 라벨 판단에만 쓰이며 AI 판정을 개선한 것으로 해석하지 않는다.','- 완벽 재검사도 AI가 통과시킨 FN을 발견하지 않는다. NG만 재검사 대상으로 들어간다.','- MVTec test 결함 비율과 반복 재생은 실제 제조 불량률이 아니다. 재검사 병목·차단 효과가 이 분포에 의존한다.','- 비용 5/20/100은 후처리한 가정 단위비용이며 사람 인건비는 제외했다. detection 비용과 disposition 비용을 구분한다.','- blocking DES 및 설계 CAD는 연속 벨트 물리·센서 광학·로봇 충돌 검증을 대체하지 않는다.',f"- 민감도 분석에서 엄격한 모델 순서 역전 행: {status['strict_reversal_rows']}. 상세는 sensitivity_rank_changes.csv. 추가 탐색은 실행하지 않는다.",'','전체 조건: summary_ci95.csv. paired_effects.csv는 같은 seed의 CCIFPS−coreset 차이. 원자료는 verified_results.csv 및 runs/ 아래 압축 이벤트·부품 원장.']
 (out/'REPORT.md').write_text('\n'.join(lines)+'\n');print(json.dumps(status))
if __name__=='__main__':main()
