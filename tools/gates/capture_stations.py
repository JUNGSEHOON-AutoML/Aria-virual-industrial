"""S1-S3 CPU browser evidence; only controls its isolated preview and Chrome."""
import asyncio,base64,json,socket,subprocess,time,os
from pathlib import Path
import httpx,websockets
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'docs/autopilot/local/stations';OUT.mkdir(parents=True,exist_ok=True)
URL=os.environ.get('STATIONS_URL','http://127.0.0.1:5288/cnotta.html')
async def main():
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 log=(OUT/'chrome.log').open('w');proc=subprocess.Popen(['/usr/bin/google-chrome','--headless=new','--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader',f'--remote-debugging-port={port}',f'--user-data-dir=/tmp/aria-stations-{time.time_ns()}','about:blank'],stdout=log,stderr=log)
 report={'url':URL,'halls':{}};events=[]
 try:
  for _ in range(100):
   try:tab=next(t for t in httpx.get(f'http://127.0.0.1:{port}/json/list').json() if t['type']=='page');break
   except Exception:await asyncio.sleep(.2)
  async with websockets.connect(tab['webSocketDebuggerUrl'],max_size=100_000_000) as ws:
   seq=0
   async def cmd(m,p=None):
    nonlocal seq
    seq+=1;await ws.send(json.dumps({'id':seq,'method':m,'params':p or {}}))
    while True:
     r=json.loads(await asyncio.wait_for(ws.recv(),120))
     if r.get('id')==seq:
      if 'error' in r:raise RuntimeError(r['error'])
      return r.get('result',{})
     events.append(r)
   async def js(s):
    r=await cmd('Runtime.evaluate',{'expression':s,'returnByValue':True,'awaitPromise':True})
    if 'exceptionDetails' in r:raise RuntimeError(r['exceptionDetails'])
    return r.get('result',{}).get('value')
   async def waitfor(expr):
    for _ in range(480):
     if await js(expr):return
     await asyncio.sleep(.5)
    raise AssertionError('Timed out: '+expr)
   async def shot(name):
    result=await cmd('Page.captureScreenshot',{'format':'png'});(OUT/(name+'.png')).write_bytes(base64.b64decode(result['data']))
   async def seek(t):
    await js(f'window.__campus.setTime({t})');await asyncio.sleep(.4)
   await cmd('Runtime.enable');await cmd('Network.enable');await cmd('Page.enable');await cmd('Emulation.setDeviceMetricsOverride',{'width':1440,'height':900,'deviceScaleFactor':1,'mobile':False})
   await cmd('Page.navigate',{'url':URL});await waitfor('!!window.__campus?.scene && window.__campus?.catalog?.ready_lanes===9');await asyncio.sleep(2);await shot('campus')
   report['renderer']=await js('window.__campus.renderer')
   await js("import('/node_modules/three/build/three.module.js').then(m=>{window.stationTHREE=m;return true})")
   for cls in ('bottle','screw','carpet'):
    await js(f'window.__campus.enter("hall-{cls}")')
    await waitfor(f"window.__campus.catalog.sites.find(s=>s.id==='hall-{cls}').lanes.every(l=>window.__stations?.records?.[l.run.run_id])")
    await asyncio.sleep(2);await seek(1800);await shot(cls)
    d=await js(f"Object.values(window.__stations.records).find(d=>d.class_name==='{cls}'&&d.selector==='ccifps')")
    row=next(p for p in d['parts'] if p['route']=='NG' and p['arrival'] is not None and p['decision']<=p['arrival'])
    camera=await js('''(()=>{const T=window.stationTHREE,scene=window.__campus.scene,rows=[];scene.updateMatrixWorld(true);scene.traverse(c=>{if(!c.name.startsWith('inspection-camera-'))return;const d=c.getWorldDirection(new T.Vector3()),local=c.position.clone();local.y-=2.4;const p=c.parent.localToWorld(local);c.updateProjectionMatrix();c.updateMatrixWorld();const frustum=new T.Frustum().setFromProjectionMatrix(new T.Matrix4().multiplyMatrices(c.projectionMatrix,c.matrixWorldInverse));const size=c.name.includes('carpet')?[.09,.012,1.18]:c.name.includes('screw')?[.018,.012,.018]:[.08,.15,.08];const corners=[];for(const x of [-.5,.5])for(const y of [-.5,.5])for(const z of [-.5,.5])corners.push(p.clone().add(new T.Vector3(x*size[0],y*size[1],z*size[2])));rows.push({name:c.name,angle_deg:Math.acos(Math.min(1,Math.max(-1,d.dot(new T.Vector3(0,-1,0)))))*180/Math.PI,contains:corners.every(v=>frustum.containsPoint(v)),direction:d.toArray()})});return rows})()''')
    key='hall-'+cls+':ccifps'
    await seek(row['trigger']);trigger=await js(f'window.__stations.lanes[{json.dumps(key)}]')
    await seek(row['arrival']+1/120);arrival=await js(f'window.__stations.lanes[{json.dumps(key)}]')
    frozen=json.dumps(await js('window.__stations.lanes'),sort_keys=True);await asyncio.sleep(.5);paused=frozen==json.dumps(await js('window.__stations.lanes'),sort_keys=True)
    task=next(t for t in d['transfer_tasks'] if t['actor']=='production');program=d['grade_programs'][task['grade']] if task.get('grade') else d['transfer_program'];arm=[]
    for phase in program:
     for delta in (.1,.7) if phase['stage'] in ('MOVE_PICK','RETURN_HOME') else (.5,):
      await seek(task['start']+phase['start']+phase['duration']*delta);arm.append(await js(f'window.__stations.transfers[{json.dumps(d["run_id"]+":production")}]'))
    await seek(1800);await shot(cls+'-before-detail');await js("[...document.querySelectorAll('.station-hmi')].find(b=>b.textContent.includes('ccifps')).click()")
    await waitfor("document.querySelectorAll('.station-evidence img').length===20 && [...document.querySelectorAll('.station-evidence img')].every(i=>i.complete&&i.naturalWidth>0)")
    await shot(cls+'-detail');detail=await js("document.querySelector('.station-panel').innerText");await js("document.querySelector('.station-close').click()")
    report['halls'][cls]=dict(cameras=camera,trigger=trigger,arrival=arrival,source_part=row,paused=paused,arm=arm,detail=detail,draw_calls=await js('window.__campus.audit().draw_calls'))
    (OUT/'browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(cls,'captured',flush=True)
   await shot('before-live');await js("document.querySelector('[data-mode-toggle]').click()")
   await waitfor('window.__live?.connected && !!window.__live.store.snapshot.station')
   report['live_initial']=await js('({station:window.__live.store.snapshot.station,render:window.__live.render})')
   await shot('live-fixed-camera')
   report['errors']=[e for e in events if e.get('method')=='Runtime.exceptionThrown']
   report['http_errors']=[e['params']['response']['url'] for e in events if e.get('method')=='Network.responseReceived' and e['params']['response']['status']>=400]
 finally:
  (OUT/'browser.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');proc.terminate();proc.wait(timeout=10);log.close()
 print(json.dumps({'halls':list(report['halls']),'errors':report.get('errors'),'http_errors':report.get('http_errors')},ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
