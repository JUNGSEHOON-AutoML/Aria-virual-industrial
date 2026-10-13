"""GT joins and quality/cost accounting outside AI prediction and DES routing."""
import csv
from pathlib import Path

class PartLedger:
    def __init__(self):self.parts={}
    def add(self,e):
        pid=e.get('part_id')
        if not pid or 'image_id' not in e:return
        p=self.parts.setdefault(pid,dict(part_id=pid,image_id=e['image_id'],born=e.get('born'),
            mainline_exit_time=None,reinspection_queue_enter=None,reinspection_start=None,inspection_time=None,ai_verdict=None,reinspection_time=None,reinspection_verdict=None,exit_time=None,route=None))
        if e['type']=='part_move' and e.get('component')=='REINSPECTION_BUFFER':p.update(reinspection_queue_enter=e['sim_time'],mainline_exit_time=e['sim_time'])
        if e['type']=='part_move' and e.get('component')=='REINSPECTION':p.update(reinspection_start=e['sim_time'])
        if e['type']=='part_exit' and p['mainline_exit_time'] is None:p['mainline_exit_time']=e['sim_time']
        if e['type']=='inspection_result':
            if e.get('source')=='reinspect_oracle':p.update(reinspection_time=e['sim_time'],reinspection_verdict=e['verdict'])
            else:p.update(inspection_time=e['sim_time'],ai_verdict=e['verdict'])
        if e['type']=='part_exit':p.update(exit_time=e['sim_time'],route='HOLD' if e['verdict']=='SKIPPED' else e['verdict'])
    def rows(self):return list(self.parts.values())


def evaluate(parts,gt_path,*,warmup=600,horizon=3600):
    with Path(gt_path).open() as f:gt={r['image_id']:int(r['is_defect']) for r in csv.DictReader(f)}
    if not all(p['image_id'] in gt for p in parts):raise ValueError('Missing evaluation GT')
    window=lambda t:t is not None and warmup<=t<=horizon
    exits=[p for p in parts if window(p['exit_time'])]
    ai=[p for p in parts if window(p['inspection_time']) and p['ai_verdict'] in ('OK','NG')]
    counts={name:0 for name in ['TP','TN','FP','FN']}
    for p in ai:
        y=gt[p['image_id']];reject=p['ai_verdict']=='NG'
        counts['TP' if y and reject else 'FN' if y else 'FP' if reject else 'TN']+=1
    good=sum(gt[p['image_id']]==0 and p['route']=='OK' for p in exits)
    shipped=sum(p['route']=='OK' for p in exits)
    bad_scrap=sum(gt[p['image_id']]==0 and p['route']=='NG' for p in exits)
    recovered=sum(gt[p['image_id']]==0 and p['ai_verdict']=='NG' and p['reinspection_verdict']=='OK' and p['route']=='OK' for p in exits)
    escaped=sum(gt[p['image_id']]==1 and p['route']=='OK' for p in exits)
    hold=sum(p['route']=='HOLD' for p in exits);hours=(horizon-warmup)/3600
    if hours<=0:raise ValueError('Empty observation window')
    result=dict(**counts,completed_window=len(exits),throughput_per_hour=len(exits)/hours,
        gt_good_throughput_per_hour=good/hours,gt_quality=good/shipped if shipped else None,
        model_ok_ratio=shipped/len(exits) if exits else None,hold_ratio=hold/len(exits) if exits else None,
        hold_count=hold,false_positive_recovered=recovered,wrongly_discarded=bad_scrap,escaped_defects=escaped,
        reinspection_completed=sum(window(p['reinspection_time']) for p in parts),window_seconds=horizon-warmup,
        confusion_scope='primary AI decisions in window, excluding HOLD',quality_scope='GT-normal / OK-dispatched exits in window',sim=1)
    # Cost assumptions: waste after reinspection, escaped defects and HOLD; service cost separate.
    for ratio in (5,20,100):
        result[f'cost_detection_fn{ratio}_per_hour']=(counts['FP']+ratio*counts['FN']+hold)/hours
        result[f'cost_disposition_fn{ratio}_per_hour']=(bad_scrap+ratio*escaped+hold)/hours
    mainline=sum(window(p.get('mainline_exit_time')) for p in parts)
    admitted=[p for p in parts if window(p.get('born'))]
    result.update(mainline_departures=mainline,mainline_throughput_per_hour=mainline/hours,source_defect_fraction_observed=sum(gt[p['image_id']] for p in admitted)/len(admitted) if admitted else None)
    result['cost_assumptions']='unit FP/discard=1, FN/escape=5|20|100, HOLD=1; assumed; human labor cost excluded'
    return result


def build_source_schedule(gt_path, image_ids, *, seed, defect_rate, count):
    """Offline evaluator creates a label-free source itinerary; AI never reads GT.

    A Bernoulli draw selects the pool, then an independent RNG chooses an image
    with replacement. Sorted IDs and separate RNGs preserve paired prefixes.
    """
    import random,math,hashlib
    if not math.isfinite(defect_rate) or not 0<=defect_rate<=1:raise ValueError('Invalid defect_rate')
    if not isinstance(count,int) or count<1:raise ValueError('Invalid schedule size')
    with Path(gt_path).open() as f:labels={r['image_id']:int(r['is_defect']) for r in csv.DictReader(f)}
    if not image_ids or any(i not in labels or labels[i] not in (0,1) for i in image_ids):raise ValueError('Missing or invalid source evaluation GT')
    pools={v:sorted(i for i in set(image_ids) if labels[i]==v) for v in (0,1)}
    if (defect_rate<1 and not pools[0]) or (defect_rate>0 and not pools[1]):raise ValueError('Required source image pool is empty')
    choose=random.Random(f'aria-source-pool:{seed}');pick=random.Random(f'aria-source-image:{seed}')
    ids=[pick.choice(pools[int(choose.random()<defect_rate)]) for _ in range(count)]
    return dict(schema_version=1,source='assumed',defect_rate=defect_rate,seed=seed,mode='bernoulli_pool_then_uniform_with_replacement',gt_sha256=hashlib.sha256(Path(gt_path).read_bytes()).hexdigest(),image_ids=ids,pool_sizes={str(k):len(v) for k,v in pools.items()})


def offline_queue_metrics(parts, *, warmup, horizon, service_seconds):
    """Complete-case waits and censored backlog are separate; staffing is offered-load only."""
    import math,statistics
    window=lambda t:t is not None and warmup<=t<=horizon
    arrivals=[p for p in parts if window(p.get('reinspection_queue_enter'))]
    started=[p for p in parts if window(p.get('reinspection_start'))]
    done=[p for p in parts if window(p.get('reinspection_time'))]
    waiting=[p for p in parts if p.get('reinspection_queue_enter') is not None and p.get('reinspection_start') is None]
    pending=[p for p in parts if p.get('reinspection_queue_enter') is not None and p.get('reinspection_time') is None]
    waits=[p['reinspection_start']-p['reinspection_queue_enter'] for p in started]
    dwell=[p['reinspection_time']-p['reinspection_queue_enter'] for p in done]
    ages=[horizon-p['reinspection_queue_enter'] for p in waiting]
    duration=horizon-warmup;load=len(arrivals)*service_seconds/duration
    mean=lambda xs:statistics.mean(xs) if xs else None
    return dict(reinspection_arrivals=len(arrivals),reinspection_wait_started_mean_s=mean(waits),reinspection_residence_completed_mean_s=mean(dwell),reinspection_waiting_at_end=len(waiting),reinspection_pending_at_end=len(pending),reinspection_unfinished_wait_age_mean_s=mean(ages),reinspection_unfinished_wait_age_max_s=max(ages,default=None),reinspection_offered_load_workers=load,reinspection_required_staff_rho_lt1=math.floor(load)+1 if arrivals else 0,staffing_basis='assumed fixed service; floor(arrival_rate*service_seconds)+1 for rho<1; not a waiting-time guarantee')
