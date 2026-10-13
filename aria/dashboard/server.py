"""Independent read-only dashboard HTTP service. No experiment control endpoints."""
import json
from fastapi import FastAPI,HTTPException,Query
from fastapi.responses import JSONResponse
from . import store
app=FastAPI(title='CNOTTA ARIA saved-run replay')
@app.exception_handler(KeyError)
def unknown(request,exc):return JSONResponse(status_code=404,content={'detail':'Unknown saved run'})
@app.exception_handler(ValueError)
def invalid(request,exc):return JSONResponse(status_code=409,content={'detail':str(exc)})
@app.get('/api/dt/runs')
def runs():return [{k:v for k,v in r.items() if k!='_path'} for r in store.catalog()]
@app.get('/api/dt/runs/{run_id}/timeline')
def timeline(run_id:str,start:float=Query(0,alias='from',ge=0,le=3600),end:float=Query(3600,alias='to',ge=0,le=3600)):
 if start>end:raise HTTPException(422,'from exceeds to')
 r=store.load(run_id)
 return {'run_id':run_id,'sim':1,'horizon':3600,'complete_hash':r['complete_hash'],'parts':[p for p in r['public'] if p['born']<=end and (p['exit_time'] is None or p['exit_time']>=start)],'transitions':[e for e in r['transitions'] if e['time']<=end],'queue':[q for q in r['queue'] if q['time']<=end],'queue_at_from':store.queue_at(r,start),'geometry_source':'assumed visual layout; event times unchanged','assumed':{'human_service_seconds':30,'servers':1}}
@app.get('/api/dt/runs/{run_id}/kpi')
def kpi(run_id:str,t:float=Query(...,ge=0,le=3600)):return store.kpi(run_id,t)
@app.get('/api/dt/results/summary')
def summary():
 try:return store.summary_data()
 except FileNotFoundError:raise HTTPException(404,'실험 진행 중')

from .vision import router as vision_router
app.include_router(vision_router)
