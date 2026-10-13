import json,os,subprocess,time,hashlib
from pathlib import Path
import httpx
from aria.persistence.repositories import PostgresEventStore,PostgresSpatialRepository,MemorySpatialRepository
if os.environ.get('ARIA_HISTORY_ACCEPTANCE_ALLOW_RESET')!='1':raise SystemExit('Use an isolated acceptance DB and opt in with ARIA_HISTORY_ACCEPTANCE_ALLOW_RESET=1')
if not Path('/tmp/aria-refactor-pgdata/aria-acceptance-only').exists():raise SystemExit('Missing isolated DB marker; refusing to stop a database')
R=Path(__file__).resolve().parents[1];O=R/'docs/validation/production_refactor_20261007';DSN='host=127.0.0.1 port=55432 user=aria dbname=aria_refactor';BASE='http://127.0.0.1:8233/api/factory';PG='/tmp/aria-pgroot/usr/lib/postgresql/12/bin/pg_ctl'
env=dict(os.environ,ARIA_FACTORY_STATE_DIR='/tmp/aria-refactor-history-state',ARIA_HISTORY_BACKEND='postgres',ARIA_HISTORY_DSN=DSN,ARIA_HISTORY_SPOOL='/tmp/aria-refactor-live-spool',ARIA_HISTORY_RETRY_MIN='.1',ARIA_HISTORY_RETRY_MAX='.5',ARIA_HISTORY_SHUTDOWN_TIMEOUT='1',ARIA_CORE_URL='http://127.0.0.1:8233',ARIA_FACTORY_API='http://127.0.0.1:8233',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',PYTHONDONTWRITEBYTECODE='1')
Path(env['ARIA_FACTORY_STATE_DIR']).mkdir(exist_ok=True);(Path(env['ARIA_FACTORY_STATE_DIR'])/'factory.json').write_bytes((R/'outputs/factory/factory.json').read_bytes())
proc=None;counter=0;report={}
def get(path):r=httpx.get(BASE+path,timeout=10);r.raise_for_status();return r.json()
def post(path,data={}):r=httpx.post(BASE+path,json=data,timeout=10);r.raise_for_status();return r.json()
def wait(fn,timeout=20):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  try:
   value=fn()
   if value:return value
  except (httpx.HTTPError,ConnectionError):pass
  time.sleep(.15)
 raise RuntimeError('Timed out')
def start():
 global proc,counter
 counter+=1;log=(O/f'pg-server-{counter}.log').open('wb')
 proc=subprocess.Popen(['/userHome/userhome4/sehoon/miniconda3/envs/aria/bin/python','-m','uvicorn','server.app:app','--host','127.0.0.1','--port','8233'],env=env,stdout=log,stderr=subprocess.STDOUT)
 wait(lambda:get('/history/status'));return proc.pid
def stop():
 global proc
 if proc:proc.terminate();proc.wait(timeout=20);proc=None
def pg(action):
 penv=dict(os.environ,LD_LIBRARY_PATH='/tmp/aria-pgroot/usr/lib/x86_64-linux-gnu')
 cmd=[PG,'-D','/tmp/aria-refactor-pgdata','-l','/tmp/aria-refactor-postgres.log']
 if action=='start':cmd+=['-o','-p 55432 -h 127.0.0.1 -k /tmp','start']
 else:cmd+=['stop','-m','fast']
 subprocess.run(cmd,env=penv,check=True,stdout=subprocess.PIPE)
try:
 report['first_server_pid']=start();s=post('/site/control/run',{'speed':20});run=s['run_token']
 wait(lambda:get('/site/snapshot')['status']=='completed',45)
 state=get('/site/snapshot');wait(lambda:get('/history/status')['queue_depth']==0)
 rows=get('/history/runs/'+run+'/events');expected=max(e['sequence'] for e in state['events'])
 assert len(rows)==expected==558,(len(rows),expected)
 assert state['production']['metrics']['counts']['OK']==9 and state['metrics']['departed_shipments']==3
 report['completed_run']={'run_id':run,'event_count':len(rows),'sim_time':state['time'],'metrics':state['metrics'],'counts':state['production']['metrics']['counts']}
 (O/'persisted_lifecycle_events.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
 stop();report['second_server_pid']=start();restored=get('/history/runs/'+run+'/events');assert restored==rows
 report['server_restart']={'same_history':True,'events':len(restored)}
 second=post('/site/control/reset');run2=second['run_token'];wait(lambda:get('/history/status')['queue_depth']==0)
 pg('stop');post('/site/control/run',{'speed':20});time.sleep(2);post('/site/control/pause')
 h=wait(lambda:(lambda v:v if v['persistence_status']=='DEGRADED' else None)(get('/history/status')))
 expected2=h['checkpoints'][run2]['last_enqueued_sequence'];assert h['queue_depth']>0
 report['outage']=h;stop()
 # Process restart while PostgreSQL remains down must retain spool and advertise degradation.
 report['third_server_pid']=start();h=get('/history/status');assert h['queue_depth']>0
 pg('start');wait(lambda:get('/history/status')['queue_depth']==0,30)
 recovered=get('/history/runs/'+run2+'/events');assert len(recovered)==expected2
 store=PostgresEventStore(DSN)
 with store.connect() as c:
  assert c.execute('SELECT count(*) FROM (SELECT run_id,sequence,count(*) FROM aria_events GROUP BY run_id,sequence HAVING count(*)>1) q').fetchone()[0]==0
  ctx=c.execute('SELECT site_id,twin_revision,site_definition_hash FROM aria_runs WHERE run_id=%s',(run,)).fetchone()
 repo=PostgresSpatialRepository(store,*ctx);mem=MemorySpatialRepository(repo.definition)
 assert repo.get_assets_in_zone('ZONE-PRODUCTION')==mem.get_assets_in_zone('ZONE-PRODUCTION')
 pos=[26,999,-24];near=repo.get_nearby_assets(pos,8);near_mem=mem.get_nearby_assets(pos,8)
 assert {e['id'] for e in near}=={e['id'] for e in near_mem}
 with store.connect() as c:
  point=c.execute("SELECT ST_X(geom),ST_Y(geom),elevation_m,ST_SRID(geom) FROM aria_spatial_entities WHERE site_id=%s AND twin_revision=%s AND site_definition_hash=%s AND entity_id='MACHINE-01'",ctx).fetchone()
 p=repo.entities['MACHINE-01']['position'];assert tuple(point)==(p[0],p[2],p[1],0)
 report['spatial']={'axis_roundtrip':True,'logical_zone_membership':True,'nearby_matches_memory':True,'nearby_asset_count':len(near),'revision':list(ctx),'stored_machine_point':list(point)}
 # Replay identical envelopes into PostgreSQL twice, with original run metadata.
 with store.connect() as c:
  r=c.execute('SELECT r.site_id,r.twin_revision,r.site_definition_hash,r.seed,r.started_at,t.definition,t.model FROM aria_runs r JOIN aria_twin_revisions t USING(site_id,twin_revision,site_definition_hash) WHERE run_id=%s',(run,)).fetchone()
 context=dict(run_id=run,site_id=r[0],twin_revision=r[1],site_definition_hash=r[2],seed=r[3],started_at=r[4].isoformat(),definition=r[5],model=r[6])
 store.append(rows,{run:context});store.append(rows,{run:context});assert len(store.read(run))==558
 report['recovery']={'expected_events':expected2,'actual_events':len(recovered),'duplicates':0,'duplicate_replay_count':2,'status':get('/history/status')}
 print(json.dumps({k:v for k,v in report.items() if k not in ['outage','recovery']},ensure_ascii=False))
finally:
 stop();(O/'real_database_acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
