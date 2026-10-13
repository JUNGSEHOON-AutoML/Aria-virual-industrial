"""Verify and summarize the current A-only DES and offline B result inventory."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import math

from scipy.stats import t
from aria.simulation.dt.plan import condition_key, des_plan, posthoc_variants
from tools.benchmark_dt import csvwrite, write
from tools.run_dt_matrix import sha

KEYS=('class_name','selector','cell','speed','latency_mode','policy','sensitivity','specificity','reinspection_s','scope')
METRICS=('throughput_per_hour','mainline_throughput_per_hour','gt_good_throughput_per_hour',
         'gt_quality','hold_ratio','FP','FN','false_positive_recovered','wrongly_discarded',
         'escaped_defects','reinspection_queue_mean','reinspection_queue_max','reinspection_utilization',
         'ng_per_1000','false_positives_per_1000','person_hours_per_1000','required_staff_rho_lt1')+tuple(
         f'cost_{kind}_fn{ratio}_per_hour' for kind in ('detection','disposition') for ratio in (5,20,100))


def stats(values):
    n=len(values)
    if not n:return dict(n=0,mean=None,ci95_low=None,ci95_high=None)
    mean=statistics.mean(values)
    delta=float(t.ppf(.975,n-1))*statistics.stdev(values)/math.sqrt(n) if n>1 else None
    return dict(n=n,mean=mean,ci95_low=mean-delta if delta is not None else None,ci95_high=mean+delta if delta is not None else None)


def summarize(out):
    out=Path(out);protocol=json.loads((out/'protocol.json').read_text())
    complete=json.loads((out/'completion.json').read_text())
    if complete['completed_DES']!=2970 or complete['posthoc_views']!=4320:raise ValueError('Incomplete matrix')
    index=json.loads((out/'run_index.json').read_text())
    expected={condition_key(c):c for c in des_plan()}
    if len(index)!=2970 or {condition_key(r['config']) for r in index}!=set(expected):raise ValueError('A inventory differs')
    rows=[];baselines={}
    for entry in index:
        folder=Path(entry['path']);c=entry['config']
        if sha(folder/'complete.json')!=entry['complete_sha256']:raise ValueError('Run completion changed')
        done=json.loads((folder/'complete.json').read_text())
        if condition_key(done['lock']['config'])!=condition_key(c):raise ValueError('A condition changed')
        for name,digest in done['hashes'].items():
            if sha(folder/name)!=digest:raise ValueError('A raw data changed')
        r=json.loads((folder/'result.json').read_text())
        if r['generated']!=r['completed']+r['wip']:raise ValueError('A conservation failed')
        rows.append({**r,**c})
        if c['scope']=='main':baselines[condition_key(c)]=entry
    expected_views=[v for c in des_plan() for v in posthoc_variants(c)]
    for c in expected_views:
        vid=hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()[:16]
        folder=out/'posthoc'/vid;done=json.loads((folder/'complete.json').read_text())
        if done['config']!=c or done['new_DES_runs']!=0:raise ValueError('B view changed')
        source_config=dict(c,policy='A',sensitivity=1.,specificity=1.,reinspection_s=30.,scope='main')
        if Path(done['source_A_run'])!=Path(baselines[condition_key(source_config)]['path']):raise ValueError('B references wrong A condition')
        if sha(Path(done['source_A_run'])/'complete.json')!=done['source_complete_sha256']:raise ValueError('B source changed')
        for name,digest in done['hashes'].items():
            if sha(folder/name)!=digest:raise ValueError('B raw data changed')
        r=json.loads((folder/'result.json').read_text())
        if r['generated']!=r['completed']+r['wip']:raise ValueError('B conservation failed')
        rows.append(r)
    groups=defaultdict(list)
    for row in rows:groups[tuple(row[k] for k in KEYS)].append(row)
    summary=[]
    for key,group in groups.items():
        if sorted(r['seed'] for r in group)!=list(range(30)):raise ValueError('Group lacks 30 unique seeds')
        for metric in METRICS:
            summary.append({**dict(zip(KEYS,key)),'metric':metric,**stats([r[metric] for r in group if r.get(metric) is not None])})
    paired=[];lookup={tuple(r[k] for k in KEYS)+(r['seed'],):r for r in rows}
    for key,group in groups.items():
        if key[1]!='ccifps':continue
        reference=list(key);reference[1]='coreset'
        for metric in METRICS:
            differences=[]
            for r in group:
                b=lookup[tuple(reference)+(r['seed'],)]
                if r.get(metric) is not None and b.get(metric) is not None:differences.append(r[metric]-b[metric])
            paired.append({**dict(zip(KEYS,key)),'metric':metric,'contrast':'CCIFPS minus coreset, paired seed',**stats(differences)})
    csvwrite(out/'summary_ci95.csv',summary);csvwrite(out/'paired_effects.csv',paired)
    verification=dict(passed=True,unique_A_DES=2970,new_A_DES_including_probe=2955,
                      historical_A_reused=15,posthoc_B_views=4320,actual_B_DES=0,
                      groups=len(groups),all_groups_30_unique_seeds=True,all_raw_hashes_verified=True)
    write(out/'verification.json',verification)
    lines=['# ARIA 정책 A DES와 B 사후 계산 결과','',
           'sim=1. 신규 정책 A 2,955회(상한 seed0 9회 포함)와 기존 A 15회를 합쳐 고유 A 2,970개를 검증했다. B는 신규 DES 없이 4,320개 사후 결과를 계산했다.', '',
           f"본 단계 실행 시간: {complete['wall_seconds']/3600:.3f}시간. 별도 상한 seed0 측정 시간은 cap_probe 보고서에 기록했다.", '',
           '## 대표 조건 inline 0.5 m/s profile','',
           '|클래스|모델|정책|처리량/h 평균|95% CI|HOLD 비율|인시/1,000|',
           '|---|---|---|---:|---|---:|---:|']
    for key,group in groups.items():
        c=dict(zip(KEYS,key))
        if (c['scope'],c['cell'],c['speed'],c['latency_mode'])!=('main','inline',.5,'profile'):continue
        st=stats([r['throughput_per_hour'] for r in group]);hold=statistics.mean(r['hold_ratio'] for r in group)
        human=[r['person_hours_per_1000'] for r in group if r.get('person_hours_per_1000') is not None]
        human_text=f'{statistics.mean(human):.4f}' if human else '해당 없음'
        lines.append(f"|{c['class_name']}|{c['selector']}|{c['policy']}|{st['mean']:.2f}|[{st['ci95_low']:.2f}, {st['ci95_high']:.2f}]|{hold:.6f}|{human_text}|")
    lines+=['','## 해석과 원자료','',
        '- 불량률 5%는 복원추출의 가정 확률이다. GT는 사전 소스 준비·평가·가정 사람 oracle에만 사용한다.',
        '- 재검사 지표의 분모는 관측 창 [600,3600]의 본 라인 출구 전체이며 HOLD를 포함한다. NG·오탐·인시를 1,000개당 표시한다.',
        '- 사람 1명, 서비스 30초·민감도/특이도 1.0은 가정이다. 변형은 10/60초·민감도 .98/.95·특이도 .98/.95를 각각 독립 변경했다.',
        '- CI는 고정 이미지·뱅크에 대한 DES 30시드 변동이다. 실제 공장 검증이나 독립 학습 30회를 뜻하지 않는다.',
        '- 상한 2m/s는 가정이며 270개 고유 실행이다. 분위수 참조 1,080개를 별도로 실행하지 않았고 클리핑된 속도로 1−q HOLD 확률을 주장하지 않는다.',
        '- 오프라인 큐는 본 라인을 차단하지 않는다. 미완료 잔량·대기시간과 최종 처분 비용을 함께 평가한다.',
        '- 원자료: run_index.json의 실제 저장 위치, posthoc/*/events.json, scenario_results.csv, posthoc_results.csv.',
        '- 전체 조건 CI: summary_ci95.csv. 같은 seed CCIFPS−coreset 차이 CI: paired_effects.csv. 검증: verification.json.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    return verification


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    print(json.dumps(summarize(p.parse_args().out)))
