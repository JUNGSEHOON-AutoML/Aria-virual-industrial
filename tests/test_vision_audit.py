"""Independent L1 aggregation against locked CSVs, not report-generation helpers."""
import csv,json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from aria.dashboard.server import app
from aria.dashboard import store
from aria.dashboard.vision import AUDIT
client=TestClient(app)
@pytest.mark.parametrize('cls',['bottle','screw','carpet'])
@pytest.mark.parametrize('model',['coreset','ccifps','random_same_k'])
def test_report_counts_gallery_and_histograms(cls,model):
 report=json.loads((AUDIT/cls/model/'report.json').read_text());rows=list(csv.DictReader((store.P1/cls/model/'per_image.csv').open()));byid={r['image_id']:r for r in rows}
 expected={name:sum((r['is_defect']=='1')==defect and (r['verdict']=='NG')==ng for r in rows) for name,defect,ng in [('TP',True,True),('FN',True,False),('FP',False,True),('TN',False,False)]}
 assert report['counts']==expected and report['images']==len(rows)
 assert sum(report['histogram']['normal'])==expected['FP']+expected['TN']
 assert sum(report['histogram']['defect'])==expected['TP']+expected['FN']
 assert sum(g['kind']=='FN' for g in report['gallery'])==expected['FN']
 assert sum(g['kind']=='FP' for g in report['gallery'])==min(8,expected['FP'])
 for g in report['gallery']:
  row=byid[g['image_id']];assert g['score']==float(row['score']) and g['threshold']==float(row['threshold']) and g['verdict']==row['verdict']
  assert all(0<=v<28 for v in g['peak_patch'])
  for name in ('source.png','original.png','overlay.png','gt_mask.png','object_proxy.png'):assert (AUDIT/cls/model/'outputs/factory-evidence'/g['evidence_id']/name).is_file()
 for subtype in report['defect_types']:
  rs=[r for r in rows if r['image_id'].split('/')[2]==subtype['type']]
  assert subtype['images']==len(rs)
  assert subtype['detection_rate']==sum(r['verdict']=='NG' for r in rs)/len(rs)
 assert report['background_response']['denominator']==expected['FP']
 assert 0<=report['background_response']['numerator']<=expected['FP']
@pytest.mark.parametrize('cls',['bottle','screw','carpet'])
def test_api_exact_same_json_and_disagreement_list(cls):
 response=client.get(f'/api/dt/vision/{cls}/report');assert response.status_code==200
 assert response.content==(AUDIT/cls/'report.json').read_bytes()
 data=response.json();tables={model:{r['image_id']:r for r in csv.DictReader((store.P1/cls/model/'per_image.csv').open())} for model in ('coreset','ccifps','random_same_k')}
 expected={iid for iid in tables['coreset'] if len({table[iid]['verdict'] for table in tables.values()})>1}
 assert {r['image_id'] for r in data['disagreements']}==expected
 for row in data['disagreements']:
  for model,v in row['models'].items():assert v['score']==float(tables[model][row['image_id']]['score'])
 assert data['object_proxy']['normal_fit_images']>0

def test_assets_and_no_arbitrary_files():
 r=json.loads((AUDIT/'screw/ccifps/report.json').read_text())['gallery'][0]
 assert client.get(r['overlay_url']).headers['content-type']=='image/png'
 assert client.get('/api/dt/vision/screw/ccifps/distribution.svg').status_code==200
 assert client.get(r['overlay_url'].replace('overlay.png','metadata.json')).status_code==404
 assert client.get('/api/dt/vision/unknown/report').status_code==404
 assert client.get('/api/dt/vision/screw/ccifps/assets/not-a-key/source.png').status_code==404
