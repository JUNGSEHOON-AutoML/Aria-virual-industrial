"""Local Chrome/CDP evidence harness. Run modes sequentially against an isolated demo."""
import asyncio,base64,json,socket,subprocess,time,os
from pathlib import Path
import httpx,websockets
R=Path(__file__).resolve().parents[1];OUT=Path(os.environ.get('SITE_E2E_OUTPUT',str(R/'docs/validation/aria_site_scale')));OUT.mkdir(parents=True,exist_ok=True);MODE=os.environ.get('SITE_MODE','overview')
BASE=os.environ.get('SITE_E2E_BASE','http://127.0.0.1:8231')
if os.environ.get('ARIA_SITE_E2E_ALLOW_RESET')!='1':
 raise SystemExit('This test resets/blocks the demo runtime. Use an isolated server and set ARIA_SITE_E2E_ALLOW_RESET=1.')
if MODE not in ('overview','flow','queries','performance'):raise SystemExit('Unknown SITE_MODE')
async def main():
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 log=(OUT/('chrome-'+MODE+'.log')).open('wb');events=[];report={}
 chrome=subprocess.Popen(['/usr/bin/google-chrome','--headless=new','--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader',f'--remote-debugging-port={port}',f'--user-data-dir=/tmp/aria-site-chrome-{time.time_ns()}','about:blank'],stdout=log,stderr=subprocess.STDOUT)
 try:
  for _ in range(60):
   try:tabs=httpx.get(f'http://127.0.0.1:{port}/json/list').json();target=next(t for t in tabs if t['type']=='page');break
   except Exception:await asyncio.sleep(.2)
  async with websockets.connect(target['webSocketDebuggerUrl'],max_size=50000000) as ws:
   seq=0
   async def cmd(method,params=None):
    nonlocal seq
    seq+=1;await ws.send(json.dumps(dict(id=seq,method=method,params=params or {})))
    while True:
     r=json.loads(await asyncio.wait_for(ws.recv(),35))
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
    await js("(()=>{let b=[...document.querySelectorAll('button')].find(b=>b.getAttribute('aria-label')==="+json.dumps(label)+"||b.textContent.trim()==="+json.dumps(label)+");if(!b||b.disabled)throw Error('button missing/disabled '+"+json.dumps(label)+");b.click()})()")
    await asyncio.sleep(2.1)
   async def api(path,body=None):
    return await js("fetch('/api/factory"+path+"',"+(json.dumps({'method':'POST','headers':{'Content-Type':'application/json'},'body':json.dumps(body)}) if body is not None else '{}')+").then(async r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()})")
   async def snap():return await api('/site/snapshot')
   for m in ['Runtime.enable','Network.enable','Page.enable']:await cmd(m)
   await cmd('Emulation.setDeviceMetricsOverride',dict(width=1440,height=900,deviceScaleFactor=1,mobile=False))
   await cmd('Page.navigate',dict(url=BASE+'/?measure=1'));await asyncio.sleep(6)

   async def select_value(label,value):
    await shot('before-action')
    await js("(()=>{const e=document.querySelector('select[aria-label="+json.dumps(label)+"]');if(!e)throw Error('select missing');e.value="+json.dumps(value)+";e.dispatchEvent(new Event('change',{bubbles:true}))})()")
    await asyncio.sleep(2.1)
   async def wait_agent():
    for _ in range(100):
     if not await js("!!document.querySelector('.ct-agent [role=status]')"):return
     await asyncio.sleep(.2)
    raise RuntimeError('Agent timeout')
   async def ask_text(message):
    await shot('before-action')
    await js("(()=>{const e=document.querySelector('input[aria-label=\"Agent message\"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,"+json.dumps(message)+");e.dispatchEvent(new Event('input',{bubbles:true}))})()")
    await click('Send');await wait_agent()
   async def benchmark(label):
    await js('window.__ARIA_V2_METRICS__.snapshots=[];window.__ARIA_V2_METRICS__.renders={}')
    r=await js("new Promise(resolve=>{let start,last;const d=[];function f(t){if(start===undefined){start=t;last=t}else{d.push(t-last);last=t}if(t-start<5000)requestAnimationFrame(f);else{const a=[...d].sort((a,b)=>a-b);resolve({fps:1000*d.length/(t-start),duration_ms:t-start,frames:d.length,p95_frame_ms:a[Math.floor(a.length*.95)]})}}requestAnimationFrame(f)})")
    m=await js('window.__ARIA_V2_METRICS__');t=m['snapshots'];r.update(snapshot_hz=(len(t)-1)*1000/(t[-1]-t[0]) if len(t)>1 else 0,draw_calls=m.get('drawCalls'),triangles=m.get('triangles'),render_counts=m['renders']);report.setdefault('performance',{})[label]=r
   await api('/site/control/reset',{})
   assert await js("document.querySelectorAll('canvas').length")==1
   await js('window.__siteCanvas=document.querySelector("canvas");true')
   if MODE=='overview':
    report['lazy_before']=[e['params']['response']['url'] for e in events if e.get('method')=='Network.responseReceived' and '/robots/' in e['params']['response']['url']]
    assert not report['lazy_before']
    await click('Run');await asyncio.sleep(3);await shot('1440-site-running')
    await click('Pause');a=await snap();poses=await js('window.__ARIA_V2_METRICS__.logistics');await asyncio.sleep(.7);b=await snap();poses2=await js('window.__ARIA_V2_METRICS__.logistics')
    assert a['time']==b['time'] and poses['poses']==poses2['poses'];report['pause_freezes_logistics']=True
    await click('Step');assert (await snap())['time']>b['time']
    await click('Resume');await asyncio.sleep(.6);await click('Pause')
    await shot('1440-site-overview')
    await select_value('Drill down','ZONE-PRODUCTION');await select_value('Drill down','PRODUCTION-01');await select_value('Drill down','CELL-01');await select_value('Drill down','MACHINE-01');await asyncio.sleep(2)
    report['hierarchy']=await js("document.querySelector('[aria-label=\"Spatial hierarchy\"]').innerText")
    assert 'Production cell' in report['hierarchy'] and 'MACHINE-01' in report['hierarchy']
    assert await js('window.__siteCanvas===document.querySelector("canvas")')
    await shot('1440-production-asset')
    await click('Site');await select_value('Find shipment','SHIPMENT-101');await shot('1440-shipment')
    await click('Ask ARIA');await click('Where is SHIPMENT-101?');await wait_agent();report['agent_trace']=await js("document.querySelector('.ct-conversation').innerText");assert 'get_site_entity' not in report['agent_trace'] or 'tool results' in report['agent_trace'];await shot('1440-site-agent');await click('Close Ask ARIA')
    await click('Site');await cmd('Emulation.setDeviceMetricsOverride',dict(width=1920,height=1080,deviceScaleFactor=1,mobile=False));await asyncio.sleep(1);await shot('1920-site-overview')
    await click('Inbound yard');await shot('1920-inbound-yard');await click('Production');await asyncio.sleep(1);await shot('1920-production');await click('Quality cell');await shot('1920-quality-cell')
    report['lazy_after']=[e['params']['response']['url'] for e in events if e.get('method')=='Network.responseReceived' and '/robots/' in e['params']['response']['url']];assert report['lazy_after']
    assert await js('window.__siteCanvas===document.querySelector("canvas")')
    report['canvas_preserved']=True
   elif MODE=='flow':
    await click('Run');await select_value('Site speed','20');started=time.monotonic();seen=set()
    for _ in range(180):
     r=await snap();state=r['status']
     stages={e['type'] for e in r['events']}
     for stage,name in [('pallet_unloaded','inbound-unloading'),('production_external_material_admitted','material-entered-production'),('finished_goods_staged','finished-goods'),('shipment_departed','outbound-departure')]:
      if stage in stages and stage not in seen:await shot(name);seen.add(stage)
     if state in ('completed','error'):break
     await asyncio.sleep(.35)
    assert state=='completed',r.get('error')
    assert r['metrics']['departed_shipments']==3 and r['production']['metrics']['completed']==9
    report['lifecycle']={'sim_time':r['time'],'observed_wall_s':time.monotonic()-started,'metrics':r['metrics'],'production_counts':r['production']['metrics']['counts'],'shipments':r['shipments'],'captured_stages':list(seen)}
    (OUT/'browser-completed-runtime.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
    await shot('1440-completed')
   elif MODE=='queries':
    for dock in ['DOCK-A01','DOCK-A02']:await api('/site/docks/'+dock+'/block',{'blocked':True})
    await api('/site/control/run',{'speed':20});await asyncio.sleep(1.3);await api('/site/control/pause',{})
    r=await snap();assert next(t for t in r['trucks'] if t['id']=='TRUCK-02')['state']=='WAITING'
    await click('Inbound yard');await click('Ask ARIA');await click('Why is TRUCK-02 still waiting?');await wait_agent();report['waiting_answer']=await js("document.querySelector('.ct-conversation').innerText");assert 'No available inbound_dock' in report['waiting_answer'];await shot('blocked-dock-agent')
    await ask_text('What change would improve total site throughput?');report['unsupported_answer']=await js("document.querySelector('.ct-conversation').innerText");assert '지원하지' in report['unsupported_answer']
    await click('Close Ask ARIA');await shot('truck-selected')
    assert await js("document.querySelector('[aria-label=\"Site asset inspector\"]').innerText.includes('TRUCK-02')")
    await api('/site/control/reset',{});report['no_site_proposal']=True
    frames=[json.loads(e['params']['response']['payloadData']) for e in events if e.get('method')=='Network.webSocketFrameReceived']
    agent_events=[e for e in frames if e.get('type','').startswith('agent_')]
    assert agent_events and all(e['scope']=='site' for e in agent_events)
    report['agent_websocket_scope']='site'
   elif MODE=='performance':
    await click('Run');await benchmark('1440_site')
    await cmd('Emulation.setDeviceMetricsOverride',dict(width=1920,height=1080,deviceScaleFactor=1,mobile=False));await asyncio.sleep(.6);await benchmark('1920_site');await shot('1920-site-running')
    await click('Production');await asyncio.sleep(2);await benchmark('1920_production_detail');await click('Pause')
    await click('Engineering');assert await js("document.body.innerText.includes('MATERIAL FLOW')");report['engineering_preserved']=True;await click('Overview')
   report['body']=await js('document.body.innerText')
   report['webgl']=await js("(()=>{const g=document.querySelector('canvas').getContext('webgl2');const d=g.getExtension('WEBGL_debug_renderer_info');return {renderer:d?g.getParameter(d.UNMASKED_RENDERER_WEBGL):g.getParameter(g.RENDERER),userAgent:navigator.userAgent}})()")
   report['errors']=[e for e in events if e.get('method')=='Runtime.exceptionThrown']
   report['http_errors']=[{'url':e['params']['response']['url'],'status':e['params']['response']['status']} for e in events if e.get('method')=='Network.responseReceived' and e['params']['response']['status']>=400]
   report['console_errors']=[e for e in events if e.get('method')=='Runtime.consoleAPICalled' and e['params']['type']=='error']
   assert not report['errors'],report['errors']
   assert not report['http_errors'],report['http_errors']
   assert not report['console_errors'],report['console_errors']
   report['completed']=True
   print(json.dumps({k:v for k,v in report.items() if k not in ['metrics','body','agent_trace','lazy_after','lifecycle']},ensure_ascii=False))
 finally:
  (OUT/(MODE+'-report.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2));chrome.terminate()
  try:chrome.wait(timeout=5)
  except subprocess.TimeoutExpired:chrome.kill()
asyncio.run(main())
