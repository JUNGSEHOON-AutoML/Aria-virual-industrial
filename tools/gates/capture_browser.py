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
   await cmd('Page.navigate',{'url':'http://127.0.0.1:5278/cnotta.html'});await asyncio.sleep(12)
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
   report['errors']=[e for e in events if e.get('method')=='Runtime.exceptionThrown']
   report['http_errors']=[e['params']['response']['url'] for e in events if e.get('method')=='Network.responseReceived' and e['params']['response']['status']>=400]
 finally:
  (OUT/'browser.json').write_text(json.dumps(report,indent=2));proc.terminate()
asyncio.run(main())
