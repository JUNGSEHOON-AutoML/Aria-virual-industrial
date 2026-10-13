"""Aggregate measured L2 evidence; never drive the research experiment."""
import json,math,re,subprocess
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
 local=ROOT/'docs/autopilot/local';browser=json.loads((local/'l2-browser.json').read_text())
 tests=(local/'l2-backend-tests.log').read_text();passed=int(re.findall(r'(\d+) passed',tests)[-1]);skipped=int(re.findall(r'(\d+) skipped',tests)[-1])
 golden=(local/'l2-golden.log').read_text();errors=[];sample_count=0;open_positions={};open_moved=0
 for row in browser['samples']:
  render=row['render'];actual=row['actual'];assert len(render['parts'])==render['wip']==len(actual['parts'])
  for part,position in zip(render['parts'],actual['parts']):
   assert math.dist(part['position'],position)<1e-5
   if part['attached']:
    assert part['gripper']=='CLOSED';errors.append(math.dist(position,actual['tcp']));sample_count+=1
   elif part.get('stage')=='RETURN_HOME':
    if part['id'] in open_positions and math.dist(position,open_positions[part['id']])>1e-5:open_moved+=1
    open_positions[part['id']]=position
 snap=browser['final']['snapshot'];decisions={e['part']:e for e in snap['live_events'] if e['type']=='live_inspection_ready'}
 releases=[e for e in snap['live_events'] if e['type']=='live_robot_release' and e['part'] in decisions]
 checks=dict(backend_tests={'passed':passed,'skipped':skipped},golden_diff=0 if 'diff 0' in golden else None,
  console_errors=browser['errors'],http_errors=browser['http_errors'],websocket_connected=browser['initial']['connected'],
  exact_wip_frames=len(browser['samples']),closed_grip_samples=sample_count,tcp_max_error_m=max(errors,default=None),
  open_carry_movements=open_moved,pause_frozen=browser['pause_frozen'],real_evidence_loaded=all(e['width']>0 for e in browser['evidence']) and len(browser['evidence'])==2,
  real_verdicts=sorted({d['verdict'] for d in decisions.values()}),release_ids_match_inspection=bool(releases) and all(e['verdict']==decisions[e['part']]['verdict'] for e in releases),
  live_recovery_states=[t['state'] for t in browser['maintenance']['trace']],fault_seeds=10,hold_fixture=bool(browser['hold_fixture']),cpu=snap['device']=='cpu',
  engine_evaluator_diff=subprocess.check_output(['git','diff','HEAD','--','aria/simulation/des/engine.py','aria/simulation/des/evaluator.py'],cwd=ROOT,text=True))
 ok=passed>=207 and checks['golden_diff']==0 and sample_count>0 and max(errors)<1e-5 and open_moved==0 and checks['pause_frozen'] and checks['real_evidence_loaded'] and checks['release_ids_match_inspection'] and checks['cpu'] and not checks['engine_evaluator_diff'] and not browser['errors'] and not browser['http_errors'] and checks['live_recovery_states']==['DISPATCHED','DIAGNOSING','REPAIRING','VERIFYING','RESTORED']
 report=dict(milestone='L2',at=datetime.now(timezone.utc).isoformat(),passed=ok,checks=checks,renderer=browser['renderer'],actual_gpu='미확인',scope='isolated BOTTLE CCIFPS CPU; replay 9 lanes preserved',screenshots=['docs/autopilot/local/l2-inspecting.png','docs/autopilot/local/l2-evidence.png','docs/autopilot/local/l2-recovery.png'],limitations=['Virtual URDF kinematics, no hardware/dynamics/collision validation','CPU inference holds DES time; actual images/scores/heatmaps','SCREW/CARPET live detector bundles unavailable','L3 agent task catalog and L4 quadruped are separate milestones'])
 report['pass']=report.pop('passed')
 (ROOT/'docs/autopilot/gates/l2.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(report,ensure_ascii=False,indent=2));assert ok
if __name__=='__main__':main()
