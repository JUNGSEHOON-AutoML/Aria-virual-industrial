import json
from fastapi.testclient import TestClient
from aria.dashboard.server import app
from aria.dashboard import store
from .common import ROOT,emit
r=TestClient(app).get('/api/dt/results/summary');ready=store.full_ready()
progress=json.loads((store.FULL/'progress.json').read_text()) if (store.FULL/'progress.json').exists() else {}
checks={'availability':{'pass':r.status_code==(200 if ready else 404),'status':r.status_code},'summary_REPORT':{'pass':ready and r.status_code==200,'verified_rows':r.json().get('report_rows_verified',0)}}
emit('m5',checks,status='complete' if ready else 'pending',reason=None if ready else '실험 대기',experiment_progress=progress)
