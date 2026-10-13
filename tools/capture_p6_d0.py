"""Capture D0 with software Chrome only. Private references and outputs stay ignored.
Requires the D0 Vite server on 127.0.0.1:5276 and existing httpx/websockets.
These captures do not satisfy the hardware-GPU approval gate.
"""
import asyncio,json,base64,subprocess,socket,time,sys
from pathlib import Path
import httpx,websockets
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/specs/assets/p6_ref/d0_review';OUT.mkdir(exist_ok=True)
async def main():
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 log=(OUT/'chrome.log').open('w')
 p=subprocess.Popen(['/usr/bin/google-chrome','--headless=new','--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader',f'--remote-debugging-port={port}',f'--user-data-dir=/tmp/aria-p6-chrome-{time.time_ns()}','about:blank'],stdout=log,stderr=log)
 report=json.loads((OUT/'browser-report.json').read_text()) if '--comparisons-only' in sys.argv else {};events=[]
 try:
  for _ in range(100):
   try:tab=next(t for t in httpx.get(f'http://127.0.0.1:{port}/json/list').json() if t['type']=='page');break
   except Exception:await asyncio.sleep(.2)
  async with websockets.connect(tab['webSocketDebuggerUrl'],max_size=50000000) as ws:
   seq=0
   async def cmd(method,params=None):
    nonlocal seq
    seq+=1;await ws.send(json.dumps(dict(id=seq,method=method,params=params or {})))
    while True:
     r=json.loads(await asyncio.wait_for(ws.recv(),60))
     if r.get('id')==seq:
      if 'error' in r:raise RuntimeError(r['error'])
      return r.get('result',{})
     events.append(r)
   async def js(s):
    r=await cmd('Runtime.evaluate',dict(expression=s,returnByValue=True,awaitPromise=True))
    if 'exceptionDetails' in r:raise RuntimeError(r['exceptionDetails'])
    return r.get('result',{}).get('value')
   async def shot(name):
    r=await cmd('Page.captureScreenshot',dict(format='png'));(OUT/(name+'.png')).write_bytes(base64.b64decode(r['data']))
   await cmd('Runtime.enable');await cmd('Network.enable');await cmd('Page.enable')
   await cmd('Emulation.setDeviceMetricsOverride',dict(width=1440,height=900,deviceScaleFactor=1,mobile=False))
   for view in ([] if '--comparisons-only' in sys.argv else ['overview','line','reinspection']):
    await cmd('Page.navigate',dict(url='http://127.0.0.1:5276/d0.html?view='+view));await asyncio.sleep(10)
    await shot(view)
    report[view]=await js("({ready:window.__d0?.ready,renderer:window.__d0?.renderer,canvas:!!document.querySelector('canvas'),text:document.body.innerText,font:document.fonts.check('14px Pretendard'),audit:window.__d0?.audit()})")
    print(view, 'renderer:', report[view].get('renderer'), 'floating:', report[view].get('audit',{}).get('floating'),flush=True)
   if '--comparisons-only' not in sys.argv:
    report['errors']=[e for e in events if e.get('method')=='Runtime.exceptionThrown']
    report['http_errors']=[e['params']['response']['url'] for e in events if e.get('method')=='Network.responseReceived' and e['params']['response']['status']>=400]
    report['api_requests']=[e['params']['request']['url'] for e in events if e.get('method')=='Network.requestWillBeSent' and '/api/' in e['params']['request']['url']]
   for view in ['overview','line','reinspection']:
    html='''<!doctype html><style>body{margin:0;overflow:hidden;background:#e4e9f7;font:16px Arial;color:#263b67}.grid{display:grid;grid-template-columns:720px 1440px;gap:0}.refs img{width:720px;height:404px;display:block}h2{height:42px;margin:0;padding:12px 16px;font-size:16px;box-sizing:border-box}.refs h2{height:46px}img{object-fit:contain;display:block}</style><div class="grid"><div class="refs"><h2>PRIVATE REFERENCE · ref_01</h2><img src="../ref_01.png"><h2>PRIVATE REFERENCE · ref_03</h2><img src="../ref_03.png"></div><div><h2>ARIA D0 · '''+view+''' · SWIFTSHADER PREVIEW / GPU APPROVAL PENDING</h2><img width="1440" height="900" src="'''+view+'''.png"></div></div>'''
    (OUT/(view+'-compare.html')).write_text(html)
    await cmd('Emulation.setDeviceMetricsOverride',dict(width=2160,height=942,deviceScaleFactor=1,mobile=False))
    await cmd('Page.navigate',dict(url='http://127.0.0.1:5276/@fs/'+str(OUT/(view+'-compare.html'))));await asyncio.sleep(1)
    await shot(view+'-compare')
 finally:
  (OUT/'browser-report.json').write_text(json.dumps(report,indent=2));p.terminate()
asyncio.run(main())
