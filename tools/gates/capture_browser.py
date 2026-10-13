import asyncio,json,subprocess,socket,time,base64
from pathlib import Path
import httpx,websockets
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'docs/autopilot/local';OUT.mkdir(exist_ok=True)
async def main():
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 log=(OUT/'chrome.log').open('w');proc=subprocess.Popen(['/usr/bin/google-chrome','--headless=new','--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader',f'--remote-debugging-port={port}',f'--user-data-dir=/tmp/cnotta-chrome-{time.time_ns()}','about:blank'],stdout=log,stderr=log)
 events=[];report={}
 try:
  for _ in range(100):
   try:tab=next(t for t in httpx.get(f'http://127.0.0.1:{port}/json/list').json() if t['type']=='page');break
   except Exception:await asyncio.sleep(.2)
  async with websockets.connect(tab['webSocketDebuggerUrl'],max_size=100000000) as ws:
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
   await cmd('Runtime.enable');await cmd('Network.enable');await cmd('Page.enable');await cmd('Emulation.setDeviceMetricsOverride',{'width':1440,'height':900,'deviceScaleFactor':1,'mobile':False})
   await cmd('Page.navigate',{'url':'http://127.0.0.1:5278/cnotta.html?view=line'});await asyncio.sleep(12)
   report['audit']=await js('window.__cnotta.audit()');report['renderer']=await js('window.__cnotta.renderer')
   shot=await cmd('Page.captureScreenshot',{'format':'png'});(OUT/'m1.png').write_bytes(base64.b64decode(shot['data']))
   for _ in range(90):
    if await js('!!window.__cnotta.timeline'):break
    await asyncio.sleep(1)
   await js('window.__cnotta.setPlaying(false);window.__cnotta.setTime(100)');await asyncio.sleep(.5)
   snap=await js('({time:window.__cnotta.time,ids:window.__cnotta.activeIds,positions:window.__cnotta.positions,expected:window.__cnotta.timeline.parts.filter(p=>p.born<=window.__cnotta.time&&(p.exit_time==null||window.__cnotta.time<p.exit_time)).map(p=>p.part_id)})')
   await asyncio.sleep(.6)
   report['replay']={'snapshot':snap,'paused_positions_equal':snap['positions']==await js('window.__cnotta.positions')}
   await js('window.__cnotta.setSpeed(10);window.__cnotta.setPlaying(true)');await asyncio.sleep(1)
   samples=[]
   for _ in range(5):
    samples.append(await js('({time:window.__cnotta.time,ids:window.__cnotta.activeIds,expected:window.__cnotta.timeline.parts.filter(p=>p.born<=window.__cnotta.time&&(p.exit_time==null||window.__cnotta.time<p.exit_time)).map(p=>p.part_id)})'));await asyncio.sleep(.2)
   await js('window.__cnotta.setPlaying(false)')
   report['replay']['ten_x_samples']=samples;report['replay']['run_id']=await js('window.__cnotta.runId')
   await js('window.__cnotta.setTime(100)');await asyncio.sleep(.3)
   before=await js('({ids:window.__cnotta.activeIds,positions:window.__cnotta.positions,motion:window.__cnotta.motion})')
   await js('window.__cnotta.setTime(101)');await asyncio.sleep(.3)
   after=await js('({ids:window.__cnotta.activeIds,positions:window.__cnotta.positions,motion:window.__cnotta.motion})')
   await asyncio.sleep(.4)
   report['visible_motion']={'before':before,'after':after,'paused':await js('({ids:window.__cnotta.activeIds,positions:window.__cnotta.positions,motion:window.__cnotta.motion})')}
   report['interaction']=await js("""(async()=>{
    const c=window.__cnotta,p=c.timeline.parts.find(p=>p.inspection_time!=null&&p.score!=null);c.setTime(p.inspection_time+.01);
    const input=document.querySelector('.search input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,p.part_id);input.dispatchEvent(new Event('input',{bubbles:true}));await new Promise(r=>setTimeout(r,150));input.form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await new Promise(r=>setTimeout(r,1600));
    let handlers=0,decorations=0;c.scene.traverse(o=>{if(o.name.startsWith('decorative-')){decorations++;o.traverse(n=>{handlers+=Object.keys(n.__r3f?.handlers||{}).length});let n=o.parent;while(n){handlers+=Object.keys(n.__r3f?.handlers||{}).length;n=n.parent}}});
    return {part_id:p.part_id,selected:window.__cnotta.selected?.part_id,score:Number(document.querySelector('[data-score]')?.dataset.score),verdict:document.querySelector('[data-verdict]')?.dataset.verdict,decorations,decoration_handlers:handlers,markers:c.scene.children.flatMap(()=>[]).length,run_id:c.runId,target:c.controls.getTarget().toArray()};
   })()""")
   shot=await cmd('Page.captureScreenshot',{'format':'png'});(OUT/'m3.png').write_bytes(base64.b64decode(shot['data']))
   report['panels']=await js("""(async()=>{const c=window.__cnotta;c.controls.setLookAt(19,20.3,21,-1,.5,1,false);c.setTime(1800);await new Promise(r=>setTimeout(r,1800));const k=window.__cnotta.kpi;return {run_id:c.runId,kpi:k,display:[...document.querySelectorAll('[data-metric]')].map(e=>({metric:e.dataset.metric,value:e.dataset.value,text:e.textContent})),rack_count:window.__cnotta.rackCount,coverage:window.__cnotta.panelCoverage()}})()""")
   shot=await cmd('Page.captureScreenshot',{'format':'png'});(OUT/'m4.png').write_bytes(base64.b64decode(shot['data']))
   report['queue_cases']=[]
   for rid,t in [('888ddf2b7943f09e',2350.880121),('8ced11f8476a3116',3599.335112)]:
    await js(f"window.__cnotta.setRun('{rid}')")
    for _ in range(100):
     if await js(f"window.__cnotta.timeline?.run_id === '{rid}'"):break
     await asyncio.sleep(.3)
    await js(f'window.__cnotta.setTime({t})');await asyncio.sleep(.6)
    report['queue_cases'].append(await js('({run_id:window.__cnotta.runId,time:window.__cnotta.time,mesh_count:window.__cnotta.scene.getObjectByName("queue-boxes").count,rack_count:window.__cnotta.rackCount})'))
   report['vision_audit']=await js("""(async()=>{
    [...document.querySelectorAll('header button')].find(b=>b.textContent==='비전 분석').click();
    for(let i=0;i<100&&!window.__cnotta.visionReport;i++)await new Promise(r=>setTimeout(r,100));
    const checks=[];
    for(const cls of ['bottle','screw','carpet']){
     const input=document.querySelector('[aria-label="분석 클래스"]');Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(input,cls);input.dispatchEvent(new Event('change',{bubbles:true}));
     for(let i=0;i<100&&window.__cnotta.visionReport?.class!==cls;i++)await new Promise(r=>setTimeout(r,100));
     await new Promise(r=>setTimeout(r,200));const server=await (await fetch(`/api/dt/vision/${cls}/report`)).json();
     checks.push({class:cls,identical:JSON.stringify(server)===JSON.stringify(window.__cnotta.visionReport),display_counts:[...document.querySelectorAll('[data-audit-count]')].map(e=>({name:e.dataset.auditCount,value:Number(e.textContent)})),expected:server.models.ccifps.counts});
    }return checks;
   })()""")
   shot=await cmd('Page.captureScreenshot',{'format':'png'});(OUT/'l1-vision.png').write_bytes(base64.b64decode(shot['data']))
   report['errors']=[e for e in events if e.get('method')=='Runtime.exceptionThrown']
   report['http_errors']=[e['params']['response']['url'] for e in events if e.get('method')=='Network.responseReceived' and e['params']['response']['status']>=400]
 finally:
  (OUT/'browser.json').write_text(json.dumps(report,indent=2));proc.terminate()
asyncio.run(main())
