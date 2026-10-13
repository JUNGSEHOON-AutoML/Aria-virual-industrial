"""Offline FCFS c-server processing of saved policy-A NG arrivals. No DES calls."""
import heapq,math
from aria.simulation.dt.evaluation import evaluate,offline_queue_metrics
from aria.simulation.dt.reinspect_oracle import ReinspectOracle

def reconstruct_b(a_parts,gt_path,*,seed,service_seconds=30.,sensitivity=1.,specificity=1.,servers=1,warmup=600.,horizon=3600.):
    if isinstance(servers,bool) or not isinstance(servers,int) or servers<1:raise ValueError('servers must be a positive integer')
    if not math.isfinite(service_seconds) or service_seconds<=0:raise ValueError('service_seconds must be positive')
    if not 0<=warmup<horizon:raise ValueError('Invalid observation window')
    oracle=ReinspectOracle(gt_path,seed=seed,sensitivity=sensitivity,specificity=specificity)
    oracle.validate_images([p['image_id'] for p in a_parts])
    parts=[dict(p) for p in a_parts]
    # Include arrivals before warmup; otherwise backlog and utilization are wrong.
    arrivals=sorted((p['mainline_exit_time'],i,p) for i,p in enumerate(parts) if p['ai_verdict']=='NG' and p['mainline_exit_time'] is not None and p['mainline_exit_time']<=horizon)
    machines=[(0.,i) for i in range(servers)];heapq.heapify(machines)
    wait_heap=[];peak=0;area=busy=0.;events=[]
    overlap=lambda begin,end:max(0.,min(horizon,end)-max(warmup,begin))
    for arrival,_,p in arrivals:
        free,sid=heapq.heappop(machines);start=max(arrival,free);finish=start+service_seconds;heapq.heappush(machines,(finish,sid))
        while wait_heap and wait_heap[0]<=arrival:heapq.heappop(wait_heap)
        heapq.heappush(wait_heap,start)
        if arrival>=warmup:peak=max(peak,len(wait_heap))
        area+=overlap(arrival,start);busy+=overlap(start,finish)
        p.update(reinspection_queue_enter=arrival,reinspection_start=round(start,6) if start<=horizon else None,reinspection_time=None,reinspection_verdict=None,exit_time=None,route=None)
        if finish<=horizon:
            result=oracle.inspect(image_id=p['image_id'],part_id=p['part_id'])
            p.update(reinspection_time=round(finish,6),reinspection_verdict=result['verdict'],exit_time=round(finish,6),route=result['verdict'])
            events.append(dict(part_id=p['part_id'],image_id=p['image_id'],arrival_s=arrival,start_s=round(start,6),completion_s=round(finish,6),server_id=sid,**result))
    metrics=evaluate(parts,gt_path,warmup=warmup,horizon=horizon)
    metrics.update(offline_queue_metrics(parts,warmup=warmup,horizon=horizon,service_seconds=service_seconds))
    completed=sum(p['exit_time'] is not None and p['exit_time']<=horizon for p in parts)
    metrics.update(generated=len(parts),completed=completed,wip=len(parts)-completed,reinspection_queue_mean=area/(horizon-warmup),reinspection_queue_max=peak,reinspection_utilization=busy/((horizon-warmup)*servers))
    # Offered work per 1000 main-line departures is independent of unfinished queue length.
    cohort=[dict(p,inspection_time=p['mainline_exit_time']) for p in a_parts if p['mainline_exit_time'] is not None and warmup<=p['mainline_exit_time']<=horizon]
    counts=evaluate(cohort,gt_path,warmup=warmup,horizon=horizon);n=len(cohort);ng=sum(p['ai_verdict']=='NG' for p in cohort)
    norm=dict(parts_denominator=n,normalization_scope='main-line departures in [warmup,horizon], including HOLD',ng_count=ng,false_positive_count=counts['FP'],ng_per_1000=ng/n*1000 if n else None,false_positives_per_1000=counts['FP']/n*1000 if n else None,person_hours_per_1000=ng/n*1000*service_seconds/3600 if n else None,required_staff_rho_lt1=math.floor(ng*service_seconds/(horizon-warmup))+1 if ng else 0,servers=servers,staffing_source='assumed',service_seconds=service_seconds,service_source='assumed',sensitivity=sensitivity,specificity=specificity)
    return parts,metrics,norm,events
