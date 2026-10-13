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
   await asyncio.sleep(2);await shot('g2-before.png')
   report['campus']=await js('window.__campus.audit()');report['renderer']=await js('window.__campus.renderer')
   for _ in range(120):
    if await js('window.__campus.catalog?.ready_lanes>0 && Object.keys(window.__campus.timelines||{}).length===window.__campus.catalog.ready_lanes'):break
    await asyncio.sleep(1)
   report['catalog']=await js('window.__campus.catalog');await shot('g2-before.png')
   await js("[...document.querySelectorAll('header button')].find(b=>b.textContent==='물류').click();window.__campus.setTime(1800)")
   await asyncio.sleep(3);await shot('g2-logistics.png')
   report['logistics']=await js("({panel:document.querySelector('.logistics-panel')?.textContent,vehicles:window.__campus.scene.getObjectByName('derived-logistics')?.children.length})")
   await js('window.__campus.setPlaying(true)');await asyncio.sleep(2);await js('window.__campus.setPlaying(false)')
   report['live_time']=await js('window.__campus.time');await shot('g2-logistics-playing.png')
   report['errors']=[e for e in events if e.get('method')=='Runtime.exceptionThrown']
   report['http_errors']=[e['params']['response']['url'] for e in events if e.get('method')=='Network.responseReceived' and e['params']['response']['status']>=400]
 finally:
  (OUT/'g2-browser.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');proc.terminate();proc.wait(timeout=10);log.close()
 print(json.dumps({k:v for k,v in report.items() if k in ('renderer','data','errors','http_errors')},ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
