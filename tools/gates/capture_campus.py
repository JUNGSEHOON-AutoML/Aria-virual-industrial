"""CPU-only browser evidence for M7. Does not launch/control the experiment."""
import asyncio,base64,json,socket,subprocess,time
from pathlib import Path
import httpx,websockets
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/autopilot/local';OUT.mkdir(exist_ok=True)
async def main():
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 log=(OUT/'campus-chrome.log').open('w')
 proc=subprocess.Popen(['/usr/bin/google-chrome','--headless=new','--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader',f'--remote-debugging-port={port}',f'--user-data-dir=/tmp/cnotta-campus-{time.time_ns()}','about:blank'],stdout=log,stderr=log)
 report={};events=[]
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
     if r.get('id')==seq:return r.get('result',{})
     events.append(r)
   async def js(s):
    r=await cmd('Runtime.evaluate',{'expression':s,'returnByValue':True,'awaitPromise':True})
    if 'exceptionDetails' in r:raise RuntimeError(r['exceptionDetails'])
    return r.get('result',{}).get('value')
   async def shot(name):
    result=await cmd('Page.captureScreenshot',{'format':'png'});(OUT/name).write_bytes(base64.b64decode(result['data']))
   await cmd('Runtime.enable');await cmd('Network.enable');await cmd('Page.enable')
   await cmd('Emulation.setDeviceMetricsOverride',{'width':1440,'height':900,'deviceScaleFactor':1,'mobile':False})
   await cmd('Page.navigate',{'url':'http://127.0.0.1:5278/cnotta.html'})
   for _ in range(120):
    if await js('!!window.__campus?.scene?.getObjectByName("wordmark-hall-bottle")'):break
    await asyncio.sleep(.5)
   await asyncio.sleep(2);await shot('m7-campus.png')
   report['campus']=await js('window.__campus.audit()');report['renderer']=await js('window.__campus.renderer')
   for _ in range(120):
    if await js('window.__campus.catalog?.ready_lanes>0 && Object.keys(window.__campus.timelines||{}).length===window.__campus.catalog.ready_lanes'):break
    await asyncio.sleep(1)
   report['catalog']=await js('window.__campus.catalog');await shot('m7-campus.png')
   report['data']=await js('''(()=>{const c=window.__campus;return c.catalog.sites.map(site=>{const runs=site.lanes.filter(l=>l.run&&c.timelines[l.run.run_id]).map(l=>({model:l.selector,run_id:l.run.run_id,sequence:c.timelines[l.run.run_id].parts.map(p=>p.part_id),births:c.timelines[l.run.run_id].parts.map(p=>p.born)}));return {site:site.id,available:runs.length,parts:runs.map(r=>({run_id:r.run_id,model:r.model,count:r.sequence.length})),sequences_equal:runs.length>1&&runs.every(r=>JSON.stringify(r.sequence)===JSON.stringify(runs[0].sequence)),max_born_delta_seconds:Math.max(0,...runs.flatMap(r=>r.births.map((t,i)=>Math.abs(t-runs[0].births[i]))))}})})()''')
   # Physical click on a front-wall sign (not a test-only focus shortcut).
   await js("document.querySelector('[data-hall-name=hall-bottle]').click()")
   await asyncio.sleep(2)
   report['hall']=await js('window.__campus.audit()');await shot('m7-hall-bottle.png')
   await js('window.__campus.setTime(1800)');await asyncio.sleep(1)
   report['replay']=await js('''(()=>{const c=window.__campus;return {time:c.time,snapshots:c.snapshots,positions:c.positions,rendered_parts:c.renderedParts,rendered_queue:c.renderedQueue,expected:c.snapshots.map(s=>{const t=c.timelines[s.run_id];return {run_id:s.run_id,active_ids:t?.parts.filter(p=>p.born<=c.time&&(p.exit_time==null||c.time<p.exit_time)).map(p=>p.part_id),ng_count:t?.parts.filter(p=>p.inspection_time!=null&&p.inspection_time<=c.time&&p.verdict==='NG').length}})}})()''')
   await asyncio.sleep(.5);report['paused_positions_equal']=report['replay']['positions']==await js('window.__campus.positions')
   await js('window.__campus.setTime(1801)');await asyncio.sleep(.5)
   report['next_positions']=await js('window.__campus.positions')
   report['motion_before']=await js('JSON.parse(JSON.stringify(window.__campus.motionMetrics))')
   await js('window.__campus.setSpeed(10);window.__campus.setPlaying(true)');await asyncio.sleep(5)
   report['playing']=await js('({time:window.__campus.time,snapshots:window.__campus.snapshots,draw_calls:window.__campus.audit().draw_calls})')
   await js('window.__campus.setPlaying(false)')
   report['motion_metrics']=await js('window.__campus.motionMetrics');report['worker_indexed']=await js('window.__campus.workerIndexed')
   await js("document.querySelectorAll('.mini-hall')[1].dispatchEvent(new MouseEvent('click',{bubbles:true}))");await asyncio.sleep(2)
   report['minimap']=await js('window.__campus.audit()');await shot('m7-hall-screw.png')
   await js("[...document.querySelectorAll('header button')].find(b=>b.textContent==='캠퍼스').click()");await asyncio.sleep(2)
   report['return']=await js('window.__campus.audit()');await shot('m7-campus-return.png')
   await cmd('Page.reload');await asyncio.sleep(5)
   report['reload_foliage']=await js('window.__campus.audit().foliage')
   report['errors']=[e for e in events if e.get('method')=='Runtime.exceptionThrown']
   report['http_errors']=[e['params']['response']['url'] for e in events if e.get('method')=='Network.responseReceived' and e['params']['response']['status']>=400]
 finally:
  (OUT/'campus-browser.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');proc.terminate();proc.wait(timeout=10);log.close()
 print(json.dumps({k:v for k,v in report.items() if k in ('renderer','data','errors','http_errors')},ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
