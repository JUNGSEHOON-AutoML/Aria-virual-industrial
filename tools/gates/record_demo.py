"""Record 60 wall-clock seconds in CPU SwiftShader; not an FPS benchmark."""
import asyncio,base64,json,socket,subprocess,time
from pathlib import Path
import httpx,websockets
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'docs/autopilot/local';FRAMES=OUT/f'demo-frames-{time.time_ns()}'
async def main():
 FRAMES.mkdir(parents=True)
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 log=(OUT/'record-chrome.log').open('w');proc=subprocess.Popen(['/usr/bin/google-chrome','--headless=new','--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader',f'--remote-debugging-port={port}',f'--user-data-dir=/tmp/cnotta-record-{time.time_ns()}','about:blank'],stdout=log,stderr=log)
 try:
  for _ in range(100):
   try:tab=next(t for t in httpx.get(f'http://127.0.0.1:{port}/json/list').json() if t['type']=='page');break
   except Exception:await asyncio.sleep(.2)
  async with websockets.connect(tab['webSocketDebuggerUrl'],max_size=100000000) as ws:
   seq=0;events=[]
   async def cmd(method,params=None):
    nonlocal seq
    seq+=1;await ws.send(json.dumps({'id':seq,'method':method,'params':params or {}}))
    while True:
     r=json.loads(await asyncio.wait_for(ws.recv(),120))
     if r.get('id')==seq:return r.get('result',{})
     events.append(r)
   async def js(s):return await cmd('Runtime.evaluate',{'expression':s,'returnByValue':True,'awaitPromise':True})
   await cmd('Runtime.enable');await cmd('Page.enable');await cmd('Emulation.setDeviceMetricsOverride',{'width':1440,'height':900,'deviceScaleFactor':1,'mobile':False});await cmd('Page.navigate',{'url':'http://127.0.0.1:5278/cnotta.html'})
   for _ in range(100):
    r=await js('!!window.__cnotta?.timeline')
    if r.get('result',{}).get('value'):break
    await asyncio.sleep(1)
   else:raise RuntimeError('Timeline did not load')
   await js('window.__cnotta.setTime(600);window.__cnotta.setSpeed(10);window.__cnotta.setPlaying(true)')
   start=time.monotonic();frames=[];actions=set()
   while time.monotonic()-start<60:
    elapsed=time.monotonic()-start
    if elapsed>=10 and 10 not in actions:
     await js('window.__cnotta.select(window.__cnotta.timeline.parts.find(p=>p.inspection_time<window.__cnotta.time))');actions.add(10)
    if elapsed>=22 and 22 not in actions:
     await js('window.__cnotta.setRun("888ddf2b7943f09e");[...document.querySelectorAll(".resources button")].find(b=>b.textContent==="재검사").click()');actions.add(22)
    if elapsed>=30 and 30 not in actions:
     await js('window.__cnotta.setTime(2300);window.__cnotta.setSpeed(10);window.__cnotta.setPlaying(true);window.__cnotta.controls.setLookAt(19,20.3,21,-1,.5,1,true)');actions.add(30)
    if elapsed>=45 and 45 not in actions:
     await js('window.__cnotta.setPlaying(false);window.__cnotta.setTime(2350.880121)');actions.add(45)
    if elapsed>=52 and 52 not in actions:
     await js('[...document.querySelectorAll(".resources button")].find(b=>b.textContent==="비교").click()');actions.add(52)
    frame=await cmd('Page.captureScreenshot',{'format':'jpeg','quality':85});path=FRAMES/f'{len(frames):04}.jpg';path.write_bytes(base64.b64decode(frame['data']));frames.append((time.monotonic()-start,path));await asyncio.sleep(.25)
   elapsed=time.monotonic()-start
   errors=[e for e in events if e.get('method')=='Runtime.exceptionThrown']
  lines=[]
  for i,(stamp,path) in enumerate(frames):
   duration=(frames[i+1][0]-stamp) if i+1<len(frames) else max(.05,60-stamp)
   if i==0:duration+=stamp
   lines.extend([f"file '{path}'",f'duration {duration:.6f}'])
  lines.append(f"file '{frames[-1][1]}'");concat=FRAMES/'frames.txt';concat.write_text('\n'.join(lines)+'\n')
  subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(concat),'-t','60','-r','10','-c:v','libx264','-threads','2','-preset','fast','-pix_fmt','yuv420p','-movflags','+faststart',str(OUT/'demo.mp4')],check=True)
  duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(OUT/'demo.mp4')]))
  (OUT/'recording.json').write_text(json.dumps({'duration_seconds':duration,'wall_seconds':elapsed,'captured_frames':len(frames),'renderer':'SwiftShader CPU','presentation_fps':10,'fps_benchmark':False,'errors':errors},indent=2))
 finally:proc.terminate()
asyncio.run(main())
