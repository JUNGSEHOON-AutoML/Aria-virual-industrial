"""User-confirmed capped plan: 1080 display references, 270 unique 2m/s DES jobs. No execution."""
import csv,hashlib,json,math,shutil,statistics
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/validation/aria_dt_20261013_04_plan';P1=ROOT/'docs/validation/aria_dt_20261012_02/p1_verified';PILOT=ROOT/'docs/validation/aria_dt_20261013_03/des_pilot30'
def writecsv(p,rows):
 with p.open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def parallel_makespan(durations):
 slots=[0.,0.]
 for value in durations:
  i=min(range(2),key=lambda i:slots[i]);slots[i]+=value
 return max(slots)
def main():
 prior=json.loads((OUT/'execution_plan.json').read_text());(OUT/'execution_plan_v1_superseded.json').write_text(json.dumps(prior,indent=2)) if not (OUT/'execution_plan_v1_superseded.json').exists() else None
 old=json.loads((OUT/'execution_plan_v1_superseded.json').read_text());base=old['options'][0]
 rows=list(csv.DictReader((PILOT/'scenario_results.csv').open()));aa=[r for r in rows if r['policy']=='A'];refs={(r['class_name'],r['cell'],float(r['speed'])):r for r in aa}
 tables=[];points=[];jobs={};means={};profiles={};bwmean=bwflow=bsmean=bsflow=0.
 for cls in ['bottle','screw','carpet']:
  for sel in ['coreset','ccifps','random_same_k']:
   file=P1/cls/sel/'latency_profile_faiss_gpu.json';profile=json.loads(file.read_text());profiles[cls,sel]=profile;samples=np.array(profile['total_ms'])/1000;mean=float(samples.mean());cap=.1/mean;means[cls,sel]=mean
   t=dict(class_name=cls,selector=sel,mean_inspection_ms=mean*1000,pitch_m=.1,pitch_source='assumed',d_m=1.,d_source='CAD design envelope',actuator_s=.1,actuator_source='assumed',v_belt_max_m_s=2.,v_belt_max_source='assumed',v_cap_m_s=cap,capacity_margin_over_2=cap/2)
   for q in (50,95,99):
    latency=float(np.percentile(samples,q));vmax=1/(latency+.1);t.update({f'T_p{q}_ms':latency*1000,f'vmax_p{q}_m_s':vmax,f'deadline_margin_p{q}_over_2':vmax/2,f'combined_limit_p{q}_m_s':min(vmax,cap,2.)})
   tables.append(t)
   for seed in range(30):
    j=dict(class_name=cls,selector=sel,seed=seed,policy='A',latency_mode='profile',cell='inline',speed_m_s=2.,defect_rate=.05,pitch_m=.1)
    uid=hashlib.sha256(json.dumps(j,sort_keys=True).encode()).hexdigest()[:16];jobs[uid]=dict(unique_condition_id=uid,**j)
    for label,q,factor in [('0.8*p99',99,.8),('p99',99,1.),('p95',95,1.),('p50',50,1.)]:
     raw=t[f'vmax_p{q}_m_s']*factor;effective=min(raw,2.);assert effective==2.
     points.append(dict(unique_condition_id=uid,class_name=cls,selector=sel,seed=seed,reference=label,q=q,raw_speed_m_s=raw,command_speed_m_s=effective,clipped_by_belt=True,capacity_limit_m_s=cap,combined_limit_m_s=min(effective,cap),deadline_margin_over_2=t[f'deadline_margin_p{q}_over_2'],capacity_margin_over_2=cap/2,nominal_one_minus_q=1-q/100 if factor==1 else None,nominal_tail_applicable_to_command=False,actual_deadline_s=1/effective-.1,empirical_profile_tail_at_command=float(np.mean(samples>(1/effective-.1))),inference_samples=len(samples),sampling_zero_is_not_population_zero=True))
   ref=refs[cls,'inline',1.];time_s=float(ref['wall_seconds']);size=sum(p.stat().st_size for p in (PILOT/'runs'/ref['run_id']).iterdir() if p.is_file())
   scale=min(2.,cap);bwmean+=time_s*scale*30;bwflow+=time_s*2*30;bsmean+=size*scale*30;bsflow+=size*2*30
 writecsv(OUT/'vmax_capacity_margins.csv',tables);writecsv(OUT/'capped_reference_points_1080.csv',points);writecsv(OUT/'cap_check_unique_conditions_270.csv',list(jobs.values()))
 posthoc_work=old['posthoc_compute_seconds_estimated'];posthoc_bytes=base['estimated_posthoc_storage_bytes'];baseh=base['estimated_baseline_DES_hours_two_workers_25pct'];baseb=base['estimated_baseline_storage_bytes']
 estimate=dict(baseline_A_hours=baseh,cap_check_hours_service_scenario=bwmean/2/3600*1.25,cap_check_hours_offered_scenario=bwflow/2/3600*1.25,posthoc_hours=posthoc_work/2/3600*1.25,total_hours_service_scenario=baseh+(bwmean+posthoc_work)/2/3600*1.25,total_hours_offered_scenario=baseh+(bwflow+posthoc_work)/2/3600*1.25,baseline_storage_bytes=baseb,cap_storage_service_scenario=bsmean,cap_storage_offered_scenario=bsflow,posthoc_storage_bytes=posthoc_bytes,total_storage_service_scenario=baseb+bsmean+posthoc_bytes,total_storage_offered_scenario=baseb+bsflow+posthoc_bytes,free_bytes=shutil.disk_usage(OUT).free)
 estimate['required_free_bytes_with_reserve']=estimate['total_storage_offered_scenario']*1.15+2*1024**3
 # Optional measurements: CCIFPS only, 3 classes. Existing k1 GPU profiles are reused.
 gpu=[]
 for beta in [1,2,4]:
  durations=[]
  for cls in ['bottle','screw','carpet']:
   p=profiles[cls,'ccifps'];base_ms=statistics.mean(p['total_ms']);search_ms=statistics.mean(p['stages_ms']['search'])
   durations.append(1050*(base_ms+(beta-1)*search_ms)/1000)
  gpu.append(dict(assumed_k9_search_multiplier=beta,two_gpu_elapsed_minutes_with_25pct=parallel_makespan(durations)*1.25/60,assumption='k9 search factor is not measured; existing pre/feature/post stage means reused'))
 cpu=[]
 for seconds in [.25,.5,1.,2.]:cpu.append(dict(assumed_cpu_seconds_per_image=seconds,CCIFPS_3_profiles_minutes=parallel_makespan([1050*seconds]*3)*1.25/60,all_models_9_profiles_minutes=parallel_makespan([1050*seconds]*9)*1.25/60,source='assumed sensitivity of estimate; CPU end-to-end not measured'))
 optional=dict(status='proposal_only_no_measurements_started',minimum_scope='CCIFPS x bottle/screw/carpet only',gpu_multi_k_new_profiles=3,cpu_k1_new_profiles=3,k1_gpu_reused_profiles=3,new_warmup_calls=300,new_measured_calls=6000,total_calls_including_warmup=6300,multi_k='mean of means for k1/3/5/9 using one exact top9 search; cosine normalized; density off; sigma2',cpu='full CPU feature extraction + exact NumPy chunk search; GPU backbone + NumPy search is not CPU inference',gpu_estimate=gpu,cpu_assumption_scenarios=cpu,new_latency_profile_bytes_proxy=2*sum((P1/c/'ccifps'/'latency_profile_faiss_gpu.json').stat().st_size for c in ['bottle','screw','carpet']),additional_costs_not_measured='model load, exact top9 parity, full CPU numerical drift check, warmup convergence, logging IO',preflight_after_approval='first CPU 5 warmup +20 timings per class; report measured estimate before 1000 repeats if budget expands',weight_bank_cache_reuse=True,no_model_selection_or_AP_tuning=True)
 (OUT/'optional_P1_measurement_estimate.json').write_text(json.dumps(optional,indent=2))
 plan=dict(status='plan_fixed_execution_awaits_user_confirmation',new_DES_executed=0,posthoc_actual_B_validation_pairs=15,baseline_A_total=2700,baseline_A_reuse=15,baseline_A_new=2685,cap_check_name='상한 확인 실행',cap_check_new=270,reference_rows=1080,total_new_DES=2955,total_unique_DES_including_reuse=2970,new_actual_B_DES=0,posthoc_B_baseline_views=2700,posthoc_OFAT_views=1620,cost_ratio_views='5/20/100 computed after, no runs',seed0_cap_cost_probe_subset=9,probe_included_in_270=True,workers=2,threads_per_worker_max=4,classes=['bottle','screw','carpet'],cell_cap='inline',speed_cap=2.,policy_cap='A',latency_cap='profile',horizon_s=3600,warmup_s=600,assumed=dict(defect_rate=.05,pitch_m=.1,servers=1,service_s=30,belt_max_m_s=2.,actuator_s=.1),future_scope_expansion=False,estimate=estimate,eight_hour_gate='not waived; capped timing has not been measured; re-evaluate after authorized seed0 subset',storage_gate='insufficient with current raw logging; no full launch',H1_requested_statement_status='hypothesis not conclusion; carpet capacity margin <1 contradicts uniform slack before cap tests',source_schema='interarrival=0.1/2=0.05 matches existing floor; no validator relaxation needed',queue_caveat='current blocking engine deadline starts at inspection admission; cannot claim free-flow conveyor queue deadline coverage',hold_curve='not identifiable because all four reference points are clipped to2; do not uncap',theory='1-q is an unclipped quantile benchmark only; empirical tail at clipped2m/s deadline0.4s=0/1000 for all9 profiles; not a population guarantee')
 (OUT/'execution_plan.json').write_text(json.dumps(plan,indent=2,allow_nan=False));print(json.dumps(estimate,indent=2))
if __name__=='__main__':main()
