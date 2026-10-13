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
    for _ in range(720):
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
   await shot('l2-mode-live.png')
   await js("document.querySelector('[data-mode-toggle]').click()")
   await waitfor("document.querySelector('main').dataset.mode==='replay' && window.__campus.catalog?.ready_lanes===9 && Object.keys(window.__campus.timelines).length===9")
   report['replay_lanes']=await js('window.__campus.catalog.ready_lanes')
   await shot('l2-mode-replay.png')
   await js('window.__campus.setPlaying(true)');await asyncio.sleep(2);await js('window.__campus.setPlaying(false)')
   report['replay_time']=await js('window.__campus.time')
   await shot('l2-mode-before-live.png')
   await js("document.querySelector('[data-mode-toggle]').click()")
   await waitfor("window.__live.connected && document.querySelector('[data-action=live-toggle]')?.textContent==='Live 시작'")
   await shot('l2-mode-before-start.png')
   await js("document.querySelector('[data-action=live-toggle]').click()")
   await waitfor("window.__live.store.snapshot.status==='running' && window.__live.render.time>2")
   report['running']=await js('({time:window.__live.render.time,status:window.__live.store.snapshot.status,speed:window.__live.store.snapshot.speed,uiSpeed:document.querySelector(\"select[aria-label=\\\"Live 속도\\\"]\").value,connected:window.__live.connected})')
   await shot('l2-final-running.png')
   report['errors']=[e for e in events if e.get('method')=='Runtime.exceptionThrown']
   report['http_errors']=[e['params']['response']['url'] for e in events if e.get('method')=='Network.responseReceived' and e['params']['response']['status']>=400]
 finally:
  (OUT/'l2-access.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');proc.terminate();proc.wait(timeout=10);log.close()
 print(json.dumps({k:v for k,v in report.items() if k in ('renderer','data','errors','http_errors')},ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
