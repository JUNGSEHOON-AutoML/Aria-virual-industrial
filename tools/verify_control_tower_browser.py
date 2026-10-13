import asyncio,base64,json,socket,subprocess,time,os
from pathlib import Path
import httpx,websockets
R=Path(__file__).resolve().parents[1]
OUT=R/'docs/validation/aria_v2_control_tower';OUT.mkdir(parents=True,exist_ok=True)
MODE=os.environ.get('ARIA_CT_MODE','smoke')
if os.environ.get('ARIA_FACTORY_E2E_ALLOW_RESET')!='1':raise SystemExit('Requires isolated server on 8230 and ARIA_FACTORY_E2E_ALLOW_RESET=1')
async def main():
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 log=(OUT/'chrome.log').open('wb');events=[];report={}
 chrome=subprocess.Popen(['/usr/bin/google-chrome','--headless=new','--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader',f'--remote-debugging-port={port}',f'--user-data-dir=/tmp/aria-ct-chrome-{time.time_ns()}','about:blank'],stdout=log,stderr=subprocess.STDOUT)
 try:
  for _ in range(80):
   try:
    tabs=httpx.get(f'http://127.0.0.1:{port}/json/list',timeout=2).json();target=next(t for t in tabs if t['type']=='page');break
   except Exception:await asyncio.sleep(.25)
  async with websockets.connect(target['webSocketDebuggerUrl'],max_size=50000000) as ws:
   seq=0
   async def cmd(method,params=None):
    nonlocal seq
    seq+=1;await ws.send(json.dumps(dict(id=seq,method=method,params=params or {})))
    while True:
     r=json.loads(await asyncio.wait_for(ws.recv(),40))
     if r.get('id')==seq:
      if 'error'in r:raise RuntimeError(r['error'])
      return r.get('result',{})
     events.append(r)
   async def js(code):
    r=await cmd('Runtime.evaluate',dict(expression=code,returnByValue=True,awaitPromise=True))
    if 'exceptionDetails'in r:raise RuntimeError(r['exceptionDetails'])
    return r.get('result',{}).get('value')
   async def shot(name):
    r=await cmd('Page.captureScreenshot',dict(format='png'));(OUT/(name+'.png')).write_bytes(base64.b64decode(r['data']))
   async def click(label):
    await shot('before-action')
    await js("(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.getAttribute('aria-label')==="+json.dumps(label)+"||b.textContent.trim()==="+json.dumps(label)+");if(!b||b.disabled)throw Error('missing or disabled: '+"+json.dumps(label)+");b.click()})()")
    await asyncio.sleep(.9)
   for m in ['Runtime.enable','Network.enable','Page.enable']:await cmd(m)
   await cmd('Emulation.setDeviceMetricsOverride',dict(width=1440,height=900,deviceScaleFactor=1,mobile=False))
   await cmd('Page.addScriptToEvaluateOnNewDocument',dict(source="window.__ctSockets=[];const NativeWS=window.WebSocket;window.WebSocket=class extends NativeWS{constructor(...args){super(...args);window.__ctSockets.push(this)}}"))
   await cmd('Page.navigate' ,dict(url='http://127.0.0.1:8230/?measure=1'))
   await asyncio.sleep(5)

   async def snap():return await js("fetch('/api/factory/snapshot').then(r=>r.json())")
   async def wait_idle():
    for _ in range(180):
     if not await js("!!document.querySelector('.ct-agent [role=status]')"):return
     await asyncio.sleep(.4)
    raise RuntimeError('Agent timeout')
   async def type_message(message):
    await shot('before-action')
    await js("(()=>{const e=document.querySelector('input[aria-label=\"Agent message\"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,"+json.dumps(message)+");e.dispatchEvent(new Event('input',{bubbles:true}))})()")
    await click('Send');await wait_idle()
   async def select_event(cid):
    await shot('before-action')
    await js("(()=>{const b=[...document.querySelectorAll('.ct-event')].find(b=>b.querySelector('strong').textContent==="+json.dumps(cid)+");if(!b)throw Error('event missing');b.click()})()")
    await asyncio.sleep(1.3)
   async def benchmark(label):
    await js('window.__ARIA_V2_METRICS__.frames=[];window.__ARIA_V2_METRICS__.snapshots=[];window.__ARIA_V2_METRICS__.renders={}')
    result=await js("new Promise(resolve=>{const d=[];let start,last;function f(t){if(start===undefined){start=t;last=t}else{d.push(t-last);last=t}if(t-start<6000)requestAnimationFrame(f);else{const sorted=[...d].sort((a,b)=>a-b);resolve({frames:d.length,duration_ms:t-start,fps:1000*d.length/(t-start),p50_frame_ms:sorted[Math.floor(sorted.length*.5)],p95_frame_ms:sorted[Math.floor(sorted.length*.95)]})}}requestAnimationFrame(f)})")
    m=await js('window.__ARIA_V2_METRICS__');t=m['snapshots'];result['snapshot_hz']=(len(t)-1)*1000/(t[-1]-t[0]) if len(t)>1 else 0;result['render_counts']=m['renders'];result['draw_calls']=m.get('drawCalls');result['triangles']=m.get('triangles');report.setdefault('performance',{})[label]=result
   await js("fetch('/api/factory/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(r=>r.json())");await asyncio.sleep(.5)
   if MODE=='smoke':
    a=await snap();assert len(a['model']['components'])==18
    report['source_model']={'components':len(a['model']['components']),'revision':a['revision'],'run':a['run_token']}
    assert await js("document.querySelectorAll('.ct-kpi').length")==6
    assert not await js("document.body.innerText.includes('MATERIAL FLOW')")
    await shot('1440-overview')
    # Select the actual 3D CNC using projected world coordinates and CDP mouse events.
    import math
    cam=(await js('window.__ARIA_V2_METRICS__.camera')).pop()
    bbox=await js("(()=>{const r=document.querySelector('canvas').getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}})()")
    def norm(v):
     n=math.sqrt(sum(x*x for x in v));return [x/n for x in v]
    def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
    def dot(a,b):return sum(x*y for x,y in zip(a,b))
    forward=norm([t-c for t,c in zip(cam['target'],cam['xyz'])]);right=norm(cross(forward,[0,1,0]));up=cross(right,forward)
    c=next(c for c in a['model']['components'] if c['id']=='MACHINE-01');point=[c['position'][0],1.8,c['position'][2]];rel=[p-c for p,c in zip(point,cam['xyz'])];focal=bbox['h']/(2*math.tan(math.radians(18)));depth=dot(rel,forward)
    x=bbox['x']+bbox['w']/2+dot(rel,right)*focal/depth;y=bbox['y']+bbox['h']/2-dot(rel,up)*focal/depth
    await js('window.__ctOriginalCanvas=document.querySelector("canvas");window.__ARIA_V2_METRICS__.camera=[]')
    await shot('before-3d-select')
    for kind in ['mouseMoved','mousePressed','mouseReleased']:await cmd('Input.dispatchMouseEvent',dict(type=kind,x=x,y=y,button='left',clickCount=1))
    await asyncio.sleep(1.4)
    report['3d_selection']=await js("document.querySelector('.ct-inspector h2')?.textContent")
    assert report['3d_selection']=='MACHINE-01',report['3d_selection']
    assert await js('window.__ctOriginalCanvas===document.querySelector("canvas")')
    report['camera_transition']=await js('window.__ARIA_V2_METRICS__.camera')
    await shot('1440-selected')
    await click('Ask ARIA');await shot('1440-agent')
    await click('현재 병목을 분석해줘');await wait_idle()
    report['agent_bottleneck']=await js("document.querySelector('.ct-conversation').innerText")
    assert 'tool results' in report['agent_bottleneck']
    await click('Close Ask ARIA')
    assert await js("!!document.querySelector('.ct-inspector')")
    report['agent_selected']=await js("document.querySelector('.ct-inspector h2').textContent")
    await shot('agent-evidence-selection')
    await click('Close inspector')
   if MODE=='ops':
    await click('Run');await asyncio.sleep(4)
    await benchmark('1440_running')
    await click('Pause');a=await snap();pos=await js('window.__ARIA_V2_METRICS__.production');p1=await js("fetch('/api/factory/patrol').then(r=>r.json())")
    await asyncio.sleep(1.2);b=await snap();pos2=await js('window.__ARIA_V2_METRICS__.production');p2=await js("fetch('/api/factory/patrol').then(r=>r.json())")
    assert a['time']>0 and a['time']==b['time']
    assert pos['positions']==pos2['positions'],'production moved while paused'
    assert p2['elapsed']>p1['elapsed'],'patrol clock incorrectly frozen'
    report['pause']={'production_time':b['time'],'positions_frozen':True,'patrol_elapsed_delta':p2['elapsed']-p1['elapsed']}
    await click('Step');c=await snap();assert c['metrics']['events_processed']>b['metrics']['events_processed'];report['step_time']=c['time']
    await click('Resume');await asyncio.sleep(1);await click('Pause');assert (await snap())['time']>c['time']
    await click('Reset');d=await snap();assert d['time']==0 and d['metrics']['generated']==0
    assert not (await js('window.__ARIA_V2_METRICS__.production'))['positions']
    await select_event('MACHINE-01');assert await js('!!document.querySelector("canvas")')
    report['timeline_selection']=True
    await click('Close inspector')
   if MODE=='views':
    await cmd('Emulation.setDeviceMetricsOverride',dict(width=1920,height=1080,deviceScaleFactor=1,mobile=False));await asyncio.sleep(1.5)
    await shot('1920-overview');await select_event('MACHINE-01');await shot('1920-selected');await click('Ask ARIA');await shot('1920-agent')
   if MODE=='approval':
    await click('Ask ARIA')
    # Proposal from the actual agent. Reject first, then explicit Apply, never tool auto-apply.
    original=await snap();old=next(c for c in original['model']['components'] if c['id']=='MACHINE-01')['processing_time'];new=old+.1
    await type_message(f'MACHINE-01 processing time {new} 변경')
    assert await js("!!document.querySelector('.ct-proposal')")
    pending_snap=await snap();assert pending_snap['model']==original['model']
    pending_id=next(p['id'] for p in pending_snap['proposals'] if p['status']=='pending')
    boundary=await js("fetch('/api/factory/tools/apply_factory_change',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:"+json.dumps(pending_id)+"})}).then(r=>r.status)")
    assert boundary==409;report['approval_tool_denied']=boundary
    await shot('proposal-review');await click('Reject');assert (await snap())['model']==original['model']
    await type_message(f'MACHINE-01 processing time {new} 변경');await click('Apply');applied=await snap();assert applied['revision']==original['revision']+1;assert applied['time']==0
    assert next(c for c in applied['model']['components'] if c['id']=='MACHINE-01')['processing_time']==new
    # Restore only the isolated preview copy through the same explicit review path.
    await type_message(f'MACHINE-01 processing time {old} 변경');await click('Apply');assert (await snap())['model']==original['model']
    report['proposal_apply_reject_restore']=True
   if MODE=='performance':
    await click('Engineering')
    assert await js("document.body.innerText.includes('MATERIAL FLOW')");await shot('engineering');report['engineering_preserved']=True
    await click('Overview');await asyncio.sleep(2);await click('Run');await benchmark('1440_running');await cmd('Emulation.setDeviceMetricsOverride',dict(width=1920,height=1080,deviceScaleFactor=1,mobile=False));await asyncio.sleep(1);await benchmark('1920_running');await click('Pause')
   report['rects']=await js("Object.fromEntries(['.ct-stage','.ct-world','.ct-kpis','.ct-timeline'].map(s=>{const r=document.querySelector(s).getBoundingClientRect();return[s,{x:r.x,y:r.y,w:r.width,h:r.height}]}))")
   report['webgl']=await js("(()=>{const g=document.querySelector('canvas').getContext('webgl2');const d=g.getExtension('WEBGL_debug_renderer_info');return {renderer:d?g.getParameter(d.UNMASKED_RENDERER_WEBGL):g.getParameter(g.RENDERER),userAgent:navigator.userAgent}})()")
   if MODE=='performance':
    # Verify the disconnected display marks values STALE instead of showing false zero.
    await cmd('Network.emulateNetworkConditions',dict(offline=True,latency=0,downloadThroughput=0,uploadThroughput=0))
    await js('window.__ctSockets.forEach(s=>s.close())')
    await asyncio.sleep(10)
    report['offline_kpis']=await js("[...document.querySelectorAll('[data-kpi]')].map(e=>e.textContent)")
    assert all(v=='STALE' for v in report['offline_kpis']),report['offline_kpis']
    await cmd('Network.emulateNetworkConditions',dict(offline=False,latency=0,downloadThroughput=0,uploadThroughput=0))
    await asyncio.sleep(6)
    report['reconnected_kpis']=await js("[...document.querySelectorAll('[data-kpi]')].map(e=>e.textContent)")
    assert all(v!='STALE' for v in report['reconnected_kpis'])
    await shot('reconnected')
   report['errors']=[e for e in events if e.get('method')=='Runtime.exceptionThrown']
   report['console_errors']=[e for e in events if e.get('method')=='Runtime.consoleAPICalled' and e['params']['type']=='error']
   report['http_errors']=[{'url':e['params']['response']['url'],'status':e['params']['response']['status']} for e in events if e.get('method')=='Network.responseReceived' and e['params']['response']['status']>=400]
   report['failed_requests']=[e['params'] for e in events if e.get('method')=='Network.loadingFailed']
   report['unexpected_http_errors']=[e for e in report['http_errors'] if not (e['status']==409 and '/tools/apply_factory_change' in e['url'])]
   assert not report['unexpected_http_errors'],report['unexpected_http_errors']
   report['websocket_frames']=sum(e.get('method')=='Network.webSocketFrameReceived' for e in events)
   assert not report['errors'],report['errors']
   report['completed']=True
   print(json.dumps({k:v for k,v in report.items() if k not in ['camera_transition','agent_bottleneck','console_errors','failed_requests']},ensure_ascii=False))

 finally:
  (OUT/(MODE+'-report.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2));chrome.terminate()
  try:chrome.wait(timeout=8)
  except subprocess.TimeoutExpired:chrome.kill()
asyncio.run(main())
