import asyncio,base64,json,socket,subprocess,time
from pathlib import Path
import httpx,websockets
OUT=Path('/tmp/aria-benchmark/browser-isolated');OUT.mkdir(exist_ok=True)
def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
async def main():
 debug=port();log=(OUT/'chrome.log').open('wb');events=[];report={}
 chrome=subprocess.Popen(['/usr/bin/google-chrome','--headless=new','--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--window-size=1600,1120',f'--remote-debugging-port={debug}',f'--user-data-dir=/tmp/aria-cad-chrome-{time.time_ns()}','about:blank'],stdout=log,stderr=subprocess.STDOUT)
 try:
  for _ in range(60):
   try:
    tabs=httpx.get(f'http://127.0.0.1:{debug}/json/list').json();target=next(t for t in tabs if t['type']=='page');break
   except Exception:await asyncio.sleep(.3)
  async with websockets.connect(target['webSocketDebuggerUrl'],max_size=30000000) as ws:
   seq=0
   async def cmd(method,params=None):
    nonlocal seq
    seq+=1;await ws.send(json.dumps(dict(id=seq,method=method,params=params or {})))
    while True:
     r=json.loads(await asyncio.wait_for(ws.recv(),30))
     if r.get('id')==seq:return r.get('result',{})
     events.append(r)
   async def js(code):
    r=await cmd('Runtime.evaluate',dict(expression=code,returnByValue=True,awaitPromise=True))
    if 'exceptionDetails' in r:raise RuntimeError(r['exceptionDetails'])
    return r.get('result',{}).get('value')
   async def shot(name):
    r=await cmd('Page.captureScreenshot',dict(format='png'));(OUT/(name+'.png')).write_bytes(base64.b64decode(r['data']))
   async def click(text):
    await shot('before-action')
    await js("(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==="+json.dumps(text)+");if(!b)throw Error('missing button');b.click()})()")
    await asyncio.sleep(.8)
   for m in ['Runtime.enable','Network.enable','Page.enable']:await cmd(m)
   await cmd('Page.navigate',dict(url='http://127.0.0.1:8230/'))
   await asyncio.sleep(5)
   before=await js("fetch('/api/factory/snapshot').then(r=>r.json())")
   await click('Reset');await click('▶ Run')
   samples={}
   for label,actions in [('overview',[]),('cnc_cell',['MACHINE-01','Cell close-up']),('top',['Factory view','Top'])]:
    for action in actions:await click(action)
    samples[label]=[]
    for repeat in range(3):
     samples[label].append(await js("new Promise(resolve=>{const d=[];let first,last;function frame(t){if(first===undefined){first=t;last=t;}else{d.push(t-last);last=t;}if(t-first<5000){requestAnimationFrame(frame)}else{const s=[...d].sort((a,b)=>a-b);resolve({frames:d.length,duration_ms:t-first,fps:d.length*1000/(t-first),median_frame_ms:s[Math.floor(s.length*.5)],p95_frame_ms:s[Math.floor(s.length*.95)]})}}requestAnimationFrame(frame)})"))
    await shot('benchmark-'+label)
   latencies=[]
   for _ in range(20):
    latencies.append(await js("(async()=>{const t=performance.now();const r=await fetch('/api/factory/snapshot');await r.json();return performance.now()-t})()"))
   await click('Pause')
   c=await js("fetch('/api/factory/snapshot').then(r=>r.json())")
   webgl=await js("(()=>{const c=document.querySelector('canvas');const g=c.getContext('webgl2')||c.getContext('webgl');const d=g.getExtension('WEBGL_debug_renderer_info');return {renderer:d?g.getParameter(d.UNMASKED_RENDERER_WEBGL):g.getParameter(g.RENDERER),userAgent:navigator.userAgent,width:c.width,height:c.height}})()")
   bench=dict(views=samples,snapshot_latency_ms=latencies,webgl=webgl,components=len(c['model']['components']),production_time=c['time'],environment='headless Chrome, ANGLE SwiftShader, same workstation; requestAnimationFrame cadence is not GPU completion time')
   (OUT/'browser_benchmark.json').write_text(json.dumps(bench,indent=2));print(json.dumps(bench))
   report=dict(errors=[e for e in events if e.get('method')=='Runtime.exceptionThrown'],http_errors=[e['params']['response']['url'] for e in events if e.get('method')=='Network.responseReceived' and e['params']['response']['status']>=400],time=c['time'],canvas=await js("[...document.querySelectorAll('canvas')].map(c=>({width:c.width,height:c.height}))"))
   assert not report['errors'],report['errors'];assert not report['http_errors'],report['http_errors']
   print(json.dumps(report))
 finally:
  (OUT/'report.json').write_text(json.dumps(report,indent=2));chrome.terminate()
  try:chrome.wait(timeout=8)
  except subprocess.TimeoutExpired:chrome.kill()
asyncio.run(main())
