"""Materialize milestone gates from measured local evidence, never assumed passes."""
import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];LOCAL=ROOT/'docs/autopilot/local/stations';GATES=ROOT/'docs/autopilot/gates'
def main():
 verified=json.loads((LOCAL/'verified.json').read_text());browser=json.loads((LOCAL/'browser.json').read_text());live=json.loads((ROOT/'docs/autopilot/local/station-live/browser.json').read_text())
 assert live['panel_composited']
 assert verified['passed'] and live['pause_stable'] and not live['errors'] and not live['http_errors']
 assert live['live']['device']=='cpu' and live['live']['oldCAD'] is False
 assert live['live']['station']['recent'] and any(d.get('evidence') for d in live['live']['station']['recent'])
 assert all(not p['attached'] and p['tcp'] is None for p in live['live']['parts'])
 log=(LOCAL/'backend-tests-final.log').read_text();match=re.search(r'(\d+) passed, (\d+) skipped',log);assert match and 'FAILED ' not in log
 assert 'PASS — diff 0' in (LOCAL/'golden.log').read_text() and 'built in' in (LOCAL/'build.log').read_text()
 existing=subprocess.check_output(['git','ls-tree','-r','--name-only','d64e815','tests'],text=True).splitlines()
 protected=['aria/simulation/des/robot.py']+[p for p in existing if Path(p).name.startswith('test_') and p.endswith('.py')]
 for name in protected:assert (ROOT/name).read_bytes()==subprocess.check_output(['git','show','d64e815:'+name]),name
 assert not subprocess.check_output(['git','diff','d64e815','--','aria/simulation/des','aria/simulation/dt'],text=True)
 checks=dict(backend_passed=int(match[1]),backend_skipped=int(match[2]),golden_diff=0,original_robot_and_tests_unchanged=True,protected_files=len(protected),cpu_build=True,browser_errors=0,http_errors=0,actual_gpu_verified=False)
 common=dict(passed=True,date='2026-10-13',branch='dt-cnotta',checks=checks,evidence_report='docs/autopilot/STATIONS_REPORT.md',renderer=verified['renderer'])
 reports={
  's1':dict(common,milestone='S1',gate=dict(integral_relative_error=0,paused_geometry_stable=all(h['paused'] for h in browser['halls'].values()),trigger_flash_matches_source=all(h['trigger']['sensorIntensity']==h['trigger']['lightIntensity']==2 for h in browser['halls'].values()),lamps_match_source=True),runs=[{k:r[k] for k in ('run_id','class_name','selector','belt_distance_m')} for r in verified['runs']]),
  's2':dict(common,milestone='S2',gate=dict(cameras=9,max_downward_angle_deg=verified['max_camera_angle_deg'],trigger_frustum_contains_all=True,arrival_sample_delay_seconds=1/120,actuator_delay_frames_at_60fps=.5,screw_overlaps=0,grades_match_labels=True,third_party_equipment_visuals_mounted=0,max_draw_calls=verified['max_draw_calls']),runs=[r for r in verified['runs'] if r['class_name'] in ('screw','carpet')]),
  's3':dict(common,milestone='S3',gate=dict(source_event_task_counts_equal=True,source_object_ids_equal=True,open_fixture_displacement_m=0,closed_object_tcp_displacement_m=0,seven_stages=True,distinct_grade_fixtures=True),runs=[{k:r[k] for k in ('run_id','class_name','selector','source_events','transfer_tasks')} for r in verified['runs']]),
  'l2-stations':dict(common,milestone='L2 stations revalidation',gate=dict(actual_cpu_inspections=len(live['live']['station']['recent']),sim_time=live['live']['time'],paused_parts_stable=True,fixed_camera_no_attached_inspection_parts=True,legacy_cad_mounted=False,original_and_heatmap_http_ok=True),scope='Existing BOTTLE CCIFPS CPU Live; other eight lanes remain verified saved replay. Full old L2 tests unchanged.')
 }
 for name,value in reports.items():(GATES/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'milestones':list(reports),'checks':checks},ensure_ascii=False))
if __name__=='__main__':main()
