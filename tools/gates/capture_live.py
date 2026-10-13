"""CPU-only browser evidence for L2. Does not launch/control the experiment."""
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
   async def waitfor(expression):
    for _ in range(240):
     if await js(expression):return
     await asyncio.sleep(.25)
    raise AssertionError('Browser condition timed out: '+expression)
   async def shot(name):
    result=await cmd('Page.captureScreenshot',{'format':'png'});(OUT/name).write_bytes(base64.b64decode(result['data']))
   await cmd('Runtime.enable');await cmd('Network.enable');await cmd('Page.enable')
   await cmd('Emulation.setDeviceMetricsOverride',{'width':1440,'height':900,'deviceScaleFactor':1,'mobile':False})
   await cmd('Page.navigate',{'url':'http://127.0.0.1:5278/cnotta.html?mode=live'})
   for _ in range(120):
    if await js('!!window.__live?.connected && !!window.__live?.render'):break
    await asyncio.sleep(.5)
   await asyncio.sleep(2);await shot('l2-initial.png')
   report['initial']=await js('({connected:window.__live?.connected,render:window.__live?.render,body:document.body.innerText})')
   assert report['initial']['connected'], 'Live websocket unavailable'
   if await js("window.__live.store.snapshot.status==='running'"):
    await waitfor("!document.querySelector('[data-action=live-toggle]').disabled && document.querySelector('[data-action=live-toggle]').textContent==='일시정지'")
    await js("document.querySelector('[data-action=live-toggle]').click()")
   await waitfor("document.querySelector('[data-action=live-toggle]').textContent==='Live 시작' && !document.querySelector('[data-action=live-toggle]').disabled")
   baseline=await js('window.__live.store.snapshot.metrics.completed')
   await shot('l2-before-start.png')
   await js("document.querySelector('[data-action=live-toggle]').click()")
   samples=[];inspecting=False
   for _ in range(150):
    sample=await js("(()=>{const s=window.__campus.scene,m=s.getObjectByName('live-parts'),t=s.getObjectByName('live-tool');s.updateMatrixWorld(true);const e=t.matrixWorld.elements,tcp=[e[12]+.12*e[8],e[13]+.12*e[9],e[14]+.12*e[10]],out=[];for(let i=0;i<m.count;i++){const a=m.matrix.clone();m.getMatrixAt(i,a);out.push(a.elements.slice(12,15))}return {render:window.__live.render,events:window.__live.store.snapshot.live_events,busy:window.__live.store.snapshot.inspection_busy,status:window.__live.store.snapshot.status,completed:window.__live.store.snapshot.metrics.completed,actual:{tcp,parts:out}}})()")
    samples.append(sample)
    if sample['busy'] and not inspecting:
     await shot('l2-inspecting.png');inspecting=True
    if sample['completed']>=baseline+2:break
    await asyncio.sleep(.5)
   report['samples']=samples
   await shot('l2-released.png')
   await js("document.querySelector('[data-action=live-toggle]').click()")
   for _ in range(80):
    if await js("window.__live.store.snapshot.status==='paused'"):break
    await asyncio.sleep(.25)
   await asyncio.sleep(.5)
   frozen=await js('window.__live.render');await asyncio.sleep(1)
   report['pause_frozen']=frozen==await js('window.__live.render')
   await shot('l2-paused.png')
   await js("document.querySelector('.live-evidence-list button').click()")
   for _ in range(60):
    if await js("[...document.querySelectorAll('.live-evidence img')].length===2 && [...document.querySelectorAll('.live-evidence img')].every(i=>i.complete&&i.naturalWidth>0)"):break
    await asyncio.sleep(.5)
   await shot('l2-evidence.png')
   report['evidence']=await js("[...document.querySelectorAll('.live-evidence img')].map(i=>({url:i.src,width:i.naturalWidth}))")
   await js("document.querySelector('.live-evidence-close').click()")
   await shot('l2-before-fault.png')
   await js("const s=document.querySelector('select[aria-label=\"Live 속도\"]');s.value='5';s.dispatchEvent(new Event('change',{bubbles:true}))")
   await js("document.querySelector('[data-action=live-toggle]').click()")
   await waitfor("window.__live.store.snapshot.status==='running' && !document.querySelector('.live-maintenance button').disabled");await shot('l2-running.png')
   await js("document.querySelector('.live-maintenance button').click()")
   await asyncio.sleep(.3);await shot('l2-fault.png')
   for _ in range(100):
    task=await js('window.__live.store.snapshot.patrol.maintenance[0]')
    if task and task['state'] in ('RESTORED','ESCALATED','INTERRUPTED'):break
    await asyncio.sleep(.5)
   report['maintenance']=task
   assert task and task['state']=='RESTORED', task
   await shot('l2-recovery.png')
   await js("document.querySelector('[data-action=live-toggle]').click()")
   for _ in range(120):
    if await js("window.__live.store.snapshot.status==='paused'"):break
    await asyncio.sleep(.25)
   await waitfor("window.__live.store.snapshot.status==='paused'")
   report['final']=await js('({render:window.__live.render,snapshot:window.__live.store.snapshot})')
   report['renderer']=await js('window.__campus.renderer')
   report['hold_fixture']=await js('window.__live.store.snapshot.robot_info.fixtures.hold')
   assert report['pause_frozen'] and len(report['evidence'])==2 and all(i['width']>0 for i in report['evidence'])
   assert sum(e['type']=='live_robot_release' for e in report['final']['snapshot']['live_events'])>=2
   report['errors']=[e for e in events if e.get('method')=='Runtime.exceptionThrown']
   report['http_errors']=[e['params']['response']['url'] for e in events if e.get('method')=='Network.responseReceived' and e['params']['response']['status']>=400]
 finally:
  (OUT/'l2-browser.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');proc.terminate();proc.wait(timeout=10);log.close()
 print(json.dumps({k:v for k,v in report.items() if k in ('renderer','data','errors','http_errors')},ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
