"""L1 independently checks report CSV counts and browser/API identity."""
import csv,json
from .common import ROOT,emit
b=json.loads((ROOT/'docs/autopilot/local/browser.json').read_text());checks={};rows=[]
for cls in ('bottle','screw','carpet'):
 for model in ('coreset','ccifps','random_same_k'):
  report=json.loads((ROOT/f'docs/reports/vision_audit/{cls}/{model}/report.json').read_text())
  raw=list(csv.DictReader((ROOT/f'docs/validation/aria_dt_20261012_02/p1_verified/{cls}/{model}/per_image.csv').open()));byid={r['image_id']:r for r in raw}
  counts={name:sum((r['is_defect']=='1')==defect and (r['verdict']=='NG')==ng for r in raw) for name,defect,ng in [('TP',True,True),('FN',True,False),('FP',False,True),('TN',False,False)]}
  gallery=all(g['score']==float(byid[g['image_id']]['score']) and g['verdict']==byid[g['image_id']]['verdict'] for g in report['gallery'])
  rows.append({'class':cls,'model':model,'counts':counts,'pass':counts==report['counts'] and gallery and sum(g['kind']=='FN' for g in report['gallery'])==counts['FN']})
checks['nine_reports']={'pass':len(rows)==9 and all(r['pass'] for r in rows),'models':rows}
ui=b['vision_audit'];checks['screen_report_identity']={'pass':len(ui)==3 and all(r['identical'] and all(v['value']==r['expected'][v['name']] for v in r['display_counts']) and len(r['display_counts'])==4 for r in ui),'classes':ui}
tests=(ROOT/'docs/autopilot/local/l1-tests.txt').read_text();golden=(ROOT/'docs/autopilot/local/l1-golden.txt').read_text();build=(ROOT/'docs/autopilot/local/l1-frontend-build.txt').read_text()
checks['backend_tests']={'pass':'176 passed' in tests and 'failed' not in tests,'summary':tests.splitlines()[-1]}
checks['golden']={'pass':'diff 0' in golden,'output':golden.strip()};checks['frontend_build']={'pass':'built in' in build};checks['console']={'pass':not b['errors'],'errors':b['errors']}
r=emit('l1',checks,execution='CPU only; saved P1 maps + existing EvidenceStore + reconstruct_b; no inference or GPU')
raise SystemExit(0 if r['pass'] else 1)
