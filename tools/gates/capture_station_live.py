"""S1-S3 CPU browser evidence; only controls its isolated preview and Chrome."""
import asyncio,base64,json,socket,subprocess,time,os
from pathlib import Path
import httpx,websockets
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'docs/autopilot/local/station-live';OUT.mkdir(parents=True,exist_ok=True)
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
   await cmd('Page.navigate',{'url':URL+'?mode=live'});await waitfor('window.__live?.connected && !!window.__live.store.snapshot.station');await asyncio.sleep(2);await shot('before-start')
   if not await js("window.__live.store.snapshot.live_events.some(e=>e.type==='live_inspection_ready')"):
    await js("document.querySelector('select[aria-label=\"Live 속도\"]').value='20';document.querySelector('select[aria-label=\"Live 속도\"]').dispatchEvent(new Event('change',{bubbles:true}))")
    await asyncio.sleep(.3);await js("document.querySelector('[data-action=live-toggle]').click()")
    await waitfor("window.__live.store.snapshot.live_events.some(e=>e.type==='live_inspection_ready')")
    await js("document.querySelector('[data-action=live-toggle]').click()")
    await waitfor("window.__live.store.snapshot.status==='paused'");await asyncio.sleep(.5);await shot('actual-cpu-inspection')
   report['live']=await js("({time:window.__live.store.snapshot.time,device:window.__live.store.snapshot.device,status:window.__live.store.snapshot.status,station:window.__live.store.snapshot.station,parts:window.__live.render.parts,oldCAD:!!window.__campus.scene.getObjectByName('live-m0609'),renderer:window.__campus.renderer})")
   before=await js('JSON.stringify(window.__live.render.parts)');await asyncio.sleep(.7);report['pause_stable']=before==await js('JSON.stringify(window.__live.render.parts)')
   await shot('before-detail');await js("[...document.querySelectorAll('.station-hmi')].find(b=>b.textContent.includes('ccifps')).click()")
   await waitfor("document.querySelectorAll('.station-evidence img').length>=2 && [...document.querySelectorAll('.station-evidence img')].every(i=>i.complete&&i.naturalWidth>0)")
   report['panel_layers']=await js("[...document.elementsFromPoint(1120,150)].map(e=>({tag:e.tagName,cls:e.className,z:getComputedStyle(e).zIndex,position:getComputedStyle(e).position,transform:getComputedStyle(e).transform,opacity:getComputedStyle(e).opacity}))")
   report['panel_composited']=await js("getComputedStyle(document.querySelector('.station-panel')).transform!=='none'")
   await asyncio.sleep(1);await shot('actual-evidence');report['detail']=await js("document.querySelector('.station-panel').innerText")
   report['errors']=[e for e in events if e.get('method')=='Runtime.exceptionThrown']
   report['http_errors']=[e['params']['response']['url'] for e in events if e.get('method')=='Network.responseReceived' and e['params']['response']['status']>=400]
 finally:
  (OUT/'browser.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');proc.terminate();proc.wait(timeout=10);log.close()
 print(json.dumps({'time':report.get('live',{}).get('time'),'pause_stable':report.get('pause_stable'),'errors':report.get('errors'),'http_errors':report.get('http_errors')},ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
