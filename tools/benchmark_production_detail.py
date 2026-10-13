import asyncio,base64,json,os,socket,subprocess,time,hashlib
from pathlib import Path
import httpx,websockets
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/validation/production_refactor_20261007'/os.environ.get('BENCH_STAGE','before');OUT.mkdir(exist_ok=True)
async def main():
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 p=subprocess.Popen(['/usr/bin/google-chrome','--headless=new','--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader',f'--remote-debugging-port={port}',f'--user-data-dir=/tmp/aria-refactor-chrome-{time.time_ns()}','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 events=[];report={}
 try:
  for _ in range(60):
   try:target=next(t for t in httpx.get(f'http://127.0.0.1:{port}/json/list').json() if t['type']=='page');break
   except Exception:await asyncio.sleep(.2)
  async with websockets.connect(target['webSocketDebuggerUrl'],max_size=50000000) as ws:
   seq=0
   async def cmd(m,params={}):
    nonlocal seq
    seq+=1;await ws.send(json.dumps(dict(id=seq,method=m,params=params)))
    while True:
     x=json.loads(await asyncio.wait_for(ws.recv(),45))
     if x.get('id')==seq:
      if 'error'in x:raise RuntimeError(x)
      return x.get('result',{})
     events.append(x)
   async def js(s):
    x=await cmd('Runtime.evaluate',dict(expression=s,returnByValue=True,awaitPromise=True))
    if 'exceptionDetails'in x:raise RuntimeError(x)
    return x.get('result',{}).get('value')
   async def shot(n):
    x=await cmd('Page.captureScreenshot',{'format':'png'});(OUT/(n+'.png')).write_bytes(base64.b64decode(x['data']))
   for m in ['Runtime.enable','Network.enable','Page.enable']:await cmd(m)
   await cmd('Emulation.setDeviceMetricsOverride',dict(width=1920,height=1080,deviceScaleFactor=1,mobile=False))
   await cmd('Page.navigate',dict(url=os.environ.get('REFACTOR_BASE','http://127.0.0.1:8232')+'/?measure=1&fixture=1'));await asyncio.sleep(3)
   f=ROOT/'docs/validation/production_refactor_20261007/render_fixture.json'
   await js('window.__ARIA_SET_FIXTURE__('+f.read_text()+');true');await asyncio.sleep(2)
   await shot('before-selection');await js("[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Production').click();true")
   await asyncio.sleep(5)
   report['samples']=[]
   for _ in range(3):
    report['samples'].append(await js("new Promise(resolve=>{let start,last;const d=[];function f(t){if(start===undefined){start=t;last=t}else{d.push(t-last);last=t}if(t-start<5000)requestAnimationFrame(f);else{const a=[...d].sort((a,b)=>a-b);resolve({fps:1000*d.length/(t-start),p50_ms:a[Math.floor(a.length*.5)],p95_ms:a[Math.floor(a.length*.95)],frames:d.length,duration_ms:t-start})}}requestAnimationFrame(f)})"))
   report['metrics']=await js('window.__ARIA_V2_METRICS__')
   report['renderer']=await js("(()=>{const g=document.querySelector('canvas').getContext('webgl2'),d=g.getExtension('WEBGL_debug_renderer_info');return g.getParameter(d.UNMASKED_RENDERER_WEBGL)})()")
   report['heap']=await js('performance.memory?{used:performance.memory.usedJSHeapSize,total:performance.memory.totalJSHeapSize}:null')
   report['fixture_sha256']=hashlib.sha256(f.read_bytes()).hexdigest();report['condition']={'viewport':[1920,1080],'dpr':1,'camera':'PRODUCTION','time':120,'state':'paused','repetitions':3}
   report['responses']=[e['params']['response']['url'] for e in events if e.get('method')=='Network.responseReceived']
   report['errors']=[e for e in events if e.get('method')=='Runtime.exceptionThrown' or e.get('method')=='Runtime.consoleAPICalled' and e['params']['type']=='error']
   report['http_errors']=[e for e in events if e.get('method')=='Network.responseReceived' and e['params']['response']['status']>=400]
   await shot('production-detail');assert not report['errors'];assert not report['http_errors']
   (OUT/'render.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
   from collections import Counter
   rows=report['metrics']['profile']['rows'];groups={k:dict(Counter(x[k] for x in rows)) for k in ['component','category','source','material']}
   (OUT/'draw_contributions.json').write_text(json.dumps(groups,indent=2));print(json.dumps({'samples':report['samples'],'draw_calls':report['metrics']['drawCalls'],'categories':groups['category'],'components':groups['component']}))
 finally:p.terminate();p.wait(timeout=5)
asyncio.run(main())
