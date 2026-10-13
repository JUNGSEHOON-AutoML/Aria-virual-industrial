"""Read-only experiment budget from stored timings/profiles; creates a plan, never runs DES."""
import csv,hashlib,json,math,shutil,statistics
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/validation/aria_dt_20261013_04_plan';PILOT=ROOT/'docs/validation/aria_dt_20261013_03/des_pilot30';P1=ROOT/'docs/validation/aria_dt_20261012_02/p1_verified'
def writecsv(path,rows):
 with path.open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 rows=list(csv.DictReader((PILOT/'scenario_results.csv').open()));aa=[r for r in rows if r['policy']=='A'];gate=json.loads((OUT/'posthoc_gate/gate.json').read_text());checks=gate['part_checks'];lookup={(r['class_name'],r['cell'],float(r['speed'])):r for r in aa}
 bank=[];speeds=[];profiles={};distances={}
 for cls in ['bottle','screw','carpet']:
  for row in csv.DictReader((P1/cls/'latency_summary.csv').open()):
   if row['backend']!='faiss_gpu':continue
   sel=row['selector'];profile=json.loads((P1/cls/sel/'latency_profile_faiss_gpu.json').read_text());samples=np.array(profile['total_ms']);profiles[cls,sel]=samples/1000
   r=dict(class_name=cls,selector=sel,d_m=1.,actuator_s=.1,actuator_source='assumed',pitch_m=.1,pitch_source='assumed',samples=len(samples))
   for q in [50,95,99]:
    ms=float(row[f'p{q}_ms']);assert abs(ms-float(np.percentile(samples,q)))<1e-8
    vmax=1/(ms/1000+.1);r[f'T_p{q}_ms']=ms;r[f'vmax_p{q}_m_s']=vmax
    for factor in [.8,1.,1.2]:
     speed=factor*vmax;deadline=1/speed-.1
     speeds.append(dict(class_name=cls,selector=sel,q=q,factor=factor,speed_m_s=speed,interarrival_s=.1/speed,deadline_s=deadline,profile_tail_fraction_only=float(np.mean(samples/1000>deadline)),existing_source_schema_accepts=.1/speed>=.05,latency_mode='profile',policy='A',seed_count=30))
   bank.append(r)
 writecsv(OUT/'vmax_table.csv',bank);writecsv(OUT/'boundary_conditions_all_q.csv',speeds)
 base_worker=sum(float(r['wall_seconds'])*179 for r in aa) #180 original jobs per stratum minus1 reusable
 base_bytes=sum(sum(p.stat().st_size for p in (PILOT/'runs'/r['run_id']).iterdir() if p.is_file())*179 for r in aa)
 # Posthoc baseline and six OFAT variations, using measured per-stratum compute only.
 posthoc_baseline=sum(r['compute_seconds']*180 for r in checks)
 posthoc_sensitivity=sum(r['compute_seconds']*6*90 for r in checks if r['cell']=='inline' and r['speed']==.5)
 posthoc_bytes=sum(r['posthoc_output_bytes']*180 for r in checks)+sum(r['posthoc_output_bytes']*6*90 for r in checks if r['cell']=='inline' and r['speed']==.5)
 options=[]
 for qs in [[99],[50,95,99]]:
  chosen=[s for s in speeds if s['q'] in qs];bwmean=bwfree=bbmean=bbfree=0.
  for c in chosen:
   ref=lookup[c['class_name'],'inline',1.];samples=profiles[c['class_name'],c['selector']]
   # scenario1: single-slot average-service capacity; scenario2: offered-flow linear scaling.
   mean_scale=max(1.,min(c['speed_m_s']/.1,1/float(np.mean(samples)))/10)
   offered_scale=c['speed_m_s']
   size=sum(p.stat().st_size for p in (PILOT/'runs'/ref['run_id']).iterdir() if p.is_file())
   bwmean+=float(ref['wall_seconds'])*mean_scale*30;bwfree+=float(ref['wall_seconds'])*offered_scale*30
   bbmean+=size*mean_scale*30;bbfree+=size*offered_scale*30
  options.append(dict(qs=qs,baseline_A_total=2700,baseline_A_reusable=15,baseline_A_new=2685,boundary_A_new=len(chosen)*30,total_new_DES=2685+len(chosen)*30,unique_boundary_conditions=len(chosen),boundary_seed0_probe_subset=len(chosen),posthoc_baseline_B=2700,posthoc_OFAT=1620,new_actual_B_DES=0,estimated_baseline_DES_hours_two_workers_25pct=base_worker/2/3600*1.25,estimated_boundary_DES_hours_service_scenario=bwmean/2/3600*1.25,estimated_boundary_DES_hours_offered_flow_scenario=bwfree/2/3600*1.25,estimated_total_hours_service_scenario=(base_worker+bwmean+posthoc_baseline+posthoc_sensitivity)/2/3600*1.25,estimated_total_hours_offered_flow_scenario=(base_worker+bwfree+posthoc_baseline+posthoc_sensitivity)/2/3600*1.25,estimated_baseline_storage_bytes=base_bytes,estimated_posthoc_storage_bytes=posthoc_bytes,estimated_total_storage_service_scenario=base_bytes+bbmean+posthoc_bytes,estimated_total_storage_offered_flow_scenario=base_bytes+bbfree+posthoc_bytes))
 reuse=[]
 for r in aa:
  folder=PILOT/'runs'/r['run_id'];done=json.loads((folder/'complete.json').read_text());reuse.append(dict(class_name=r['class_name'],selector=r['selector'],cell=r['cell'],speed=r['speed'],latency_mode=r['latency_mode'],seed=r['seed'],policy='A',folder=str(folder),source_hash=done['lock']['source_hash'],complete_sha256=hashlib.sha256((folder/'complete.json').read_bytes()).hexdigest()))
 writecsv(OUT/'reusable_A_inventory.csv',reuse)
 plan=dict(status='proposal_only_not_authorized',new_DES_executed=0,posthoc_gate=gate['passed'],workers=2,classes=['bottle','screw','carpet'],horizon_s=3600,warmup_s=600,defect_rate=.05,defect_rate_source='assumed',pitch_m=.1,pitch_source='assumed',reinspection_servers=1,reinspection_servers_source='assumed',c_parameter_supported=True,no_staff_sweep=True,vmax_scope='measured normalized-cosine exact-FAISS end-to-end batch1 profile; timing boundary only',recommended_qs=[99],q_scope_pending_user_choice=True,original_fixed_speed_matrix_retained=True,posthoc_compute_seconds_estimated=posthoc_baseline+posthoc_sensitivity,posthoc_estimate_excludes_extra_long_services_and_final_report_io=True,options=options,free_bytes=shutil.disk_usage(OUT).free,high_speed_DES_not_measured=True,estimate_method='baseline: measured A times/bytes per class-cell-speed stratum, 179 remaining jobs. Boundary: class speed1 A reference scaled by mean service-limited or offered-flow rates;25% time reserve; not confidence limits or proven bounds.',known_blockers=['All proposed boundary speeds violate current interarrival >=0.05s schema at pitch0.1m','Blocking Source and inspection-admission deadline are not a continuous free-flow conveyor','No boundary timing/storage probe yet; no full launch justified','Current 8h gate and disk reserve remain active'],cost_ratios='5/20/100 postprocessing only')
 (OUT/'execution_plan.json').write_text(json.dumps(plan,indent=2,allow_nan=False));print(json.dumps(options,indent=2))
 # H1 observation table is from A only, not A/B duplicates.
 writecsv(OUT/'pilot_H1_observations.csv',[{k:r[k] for k in ['class_name','selector','cell','speed','latency_mode','seed','mainline_throughput_per_hour','hold_count','hold_ratio']} for r in aa if r['cell']=='inline'])
if __name__=='__main__':main()
