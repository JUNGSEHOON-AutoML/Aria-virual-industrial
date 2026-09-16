import asyncio,base64,json,os,socket,subprocess,time
from pathlib import Path
import httpx,websockets
ROOT=Path(__file__).resolve().parents[1]
if os.environ.get('ARIA_FACTORY_E2E_ALLOW_RESET') != '1':
    raise SystemExit('This harness resets the test factory on localhost:8230. Use an isolated ARIA_FACTORY_STATE_DIR and set ARIA_FACTORY_E2E_ALLOW_RESET=1.')
OUT=ROOT/'outputs/factory_validation/browser';OUT.mkdir(parents=True, exist_ok=True)

def freeport():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
async def main():
    port=freeport()
    log=(OUT/'chrome.log').open('wb')
    chrome=subprocess.Popen(['/usr/bin/google-chrome','--headless=new','--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--window-size=1600,1100',f'--remote-debugging-port={port}',f'--user-data-dir={OUT / ("profile-"+str(time.time_ns()))}','about:blank'],stdout=log,stderr=subprocess.STDOUT)
    events=[];report={}
    try:
        for _ in range(80):
            try:
                targets=httpx.get(f'http://127.0.0.1:{port}/json/list').json()
                if targets:break
            except Exception:pass
            await asyncio.sleep(.25)
        async with websockets.connect(next(t for t in targets if t['type']=='page')['webSocketDebuggerUrl'],max_size=25*1024*1024) as ws:
            idx=0
            async def cmd(method,params=None):
                nonlocal idx
                idx+=1;await ws.send(json.dumps(dict(id=idx,method=method,params=params or {})))
                while True:
                    r=json.loads(await asyncio.wait_for(ws.recv(), timeout=25))
                    if r.get('id')==idx:
                        if 'error' in r:raise RuntimeError(r['error'])
                        return r.get('result',{})
                    events.append(r)
            async def js(expression):
                r=await cmd('Runtime.evaluate',dict(expression=expression,returnByValue=True,awaitPromise=True))
                if 'exceptionDetails' in r:raise RuntimeError(r['exceptionDetails'])
                return r.get('result',{}).get('value')
            async def click(text):
                expression="(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==="+json.dumps(text)+"); if(!b)throw Error('Button missing: '+"+json.dumps(text)+"); if(b.disabled)throw Error('Button disabled'); b.click(); return true; })()"
                await js(expression);await asyncio.sleep(.6)
            async def shot(name):
                r=await cmd('Page.captureScreenshot',dict(format='png'))
                (OUT/(name+'.png')).write_bytes(base64.b64decode(r['data']))
            async def snap():
                return await js("fetch('/api/factory/snapshot').then(r=>r.json())")
            async def wait_idle():
                for _ in range(100):
                    if not await js("document.body.innerText.includes('Working…')"):return
                    await asyncio.sleep(.3)
                raise RuntimeError('Agent timeout')
            for method in ['Runtime.enable','Network.enable','Page.enable']:await cmd(method)
            await cmd('Page.navigate',dict(url='http://127.0.0.1:8230/'))
            await asyncio.sleep(5)
            # Dedicated verification server: restore a clean baseline through the tool boundary.
            await js("fetch('/api/factory/agent',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:'기본 공장을 설계해줘'})}).then(r=>r.json()).then(r=>fetch('/api/factory/proposals/'+r.proposal.id+'/apply',{method:'POST'}))")
            await asyncio.sleep(.5)
            report['initial_body']=await js('document.body.innerText')
            await shot('01-initial')
            assert await js("document.querySelectorAll('canvas').length")>=1
            await click('▶ Run');await asyncio.sleep(3)
            await click('Pause');a=await snap();await asyncio.sleep(.5);b=await snap()
            assert a['time']>0 and a['time']==b['time'];report['run_pause_time']=b['time']
            await click('Step');c=await snap();assert c['metrics']['events_processed']>b['metrics']['events_processed']
            await click('Resume');await asyncio.sleep(.5);await click('Pause')
            await shot('02-running-paused')
            await click('MACHINE-01')
            assert await js("!!document.querySelector('input[aria-label=processing_time]')")
            await js("(() => {const e=document.querySelector('input[aria-label=processing_time]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'2.7'); e.dispatchEvent(new Event('input',{bubbles:true}));})()")
            await click('Review changes');await shot('03-edit-approval')
            assert await js("document.querySelector('[role=dialog]').innerText.includes('2.7')")
            await click('Reject')
            assert next(c for c in (await snap())['model']['components'] if c['id']=='MACHINE-01')['processing_time']==3
            # Natural language entered into the actual form, not a direct agent request.
            await js("(() => {const e=document.querySelector('input[aria-label=\"Agent message\"]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'현재 병목을 분석해줘'); e.dispatchEvent(new Event('input',{bubbles:true}));})()")
            await click('Send');await wait_idle()
            assert 'MACHINE-01' in await js("document.querySelector('.factory-chat-messages').innerText")
            await click('처리량 10% 개선');await wait_idle();await asyncio.sleep(.5)
            await shot('04-improvement')
            p=await js("document.querySelector('[role=dialog]').innerText")
            report['proposal']=p
            await click('Apply');new=await snap();assert new['revision']>=1 and new['time']==0
            report['applied_model']=new['model']
            await click('Reset');assert (await snap())['metrics']['generated']==0
            await shot('05-applied')
            # Palette addition, actual property edit, translation tool and connection proposal.
            count=len(new['model']['components'])
            await js("document.querySelector('.factory-palette button').click()")
            await asyncio.sleep(.3);await click('Apply')
            added=(await snap())['model']['components'][-1]['id']
            assert len((await snap())['model']['components'])==count+1
            await click(added)
            await click('Move on XZ')
            assert await js("document.body.innerText.includes('Move on XZ ✓')")
            await shot('builder-gizmo')
            # Drag the red X handle using actual pointer input. Projection uses the
            # known initial camera and the current canvas viewport (no engine mutation).
            bbox=await js("(() => {const r=document.querySelector('canvas').getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}})()")
            import math
            def dot(a,b):return sum(x*y for x,y in zip(a,b))
            def norm(a):
                size=math.sqrt(dot(a,a));return [x/size for x in a]
            def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
            camera=[0,12,16];forward=norm([-1,-12,-16]);right=norm(cross(forward,[0,1,0]));up=cross(right,forward)
            relative=[0,-12,-11];depth=dot(relative,forward);focal=bbox['h']/(2*math.tan(math.radians(20)))
            x=bbox['x']+bbox['w']/2+dot(relative,right)*focal/depth
            y=bbox['y']+bbox['h']/2-dot(relative,up)*focal/depth
            # X-axis direction is almost horizontal in this view.
            for offset in [65,45,25]:
                await cmd('Input.dispatchMouseEvent',dict(type='mouseMoved',x=x+offset,y=y))
                await cmd('Input.dispatchMouseEvent',dict(type='mousePressed',x=x+offset,y=y,button='left',clickCount=1))
                await cmd('Input.dispatchMouseEvent',dict(type='mouseMoved',x=x+offset+45,y=y,button='left',buttons=1))
                await cmd('Input.dispatchMouseEvent',dict(type='mouseReleased',x=x+offset+45,y=y,button='left',clickCount=1))
                await asyncio.sleep(.4)
                if await js("!!document.querySelector('[role=dialog]')"):break
            assert await js("!!document.querySelector('[role=dialog]')"), 'XZ drag must produce a proposal'
            drag=await js("document.querySelector('[role=dialog]').innerText")
            assert 'position' in drag
            report['xz_drag']=drag
            await click('Reject')
            await click('Move on XZ ✓')
            await js("(() => {const e=document.querySelector('input[aria-label=\"position X\"]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'4'); e.dispatchEvent(new Event('input',{bubbles:true}));})()")
            await click('Review changes');await click('Apply')
            assert (await snap())['model']['components'][-1]['position'][0]==4
            await js("(() => {const e=document.querySelector('select[aria-label=\"Connection target\"]'); e.value='BUFFER-01'; e.dispatchEvent(new Event('change',{bubbles:true}));})()")
            await click('Connect');await click('Apply')
            assert any(e['source']==added for e in (await snap())['model']['connections'])
            await click('Delete component…');await click('Apply')
            assert len((await snap())['model']['components'])==count
            # Save and load the same JSON through the browser's file input.
            saved=await snap();fixture=OUT/'roundtrip.json';fixture.write_text(json.dumps(saved['model']))
            await cmd('Browser.setDownloadBehavior',dict(behavior='allow',downloadPath=str(OUT)))
            await click('Save JSON')
            dom=await cmd('DOM.getDocument')
            node=await cmd('DOM.querySelector',dict(nodeId=dom['root']['nodeId'],selector='input[type=file]'))
            await cmd('DOM.setFileInputFiles',dict(files=[str(fixture)],nodeId=node['nodeId']))
            await asyncio.sleep(.5);await click('Apply')
            assert (await snap())['model']==saved['model']
            report['builder_roundtrip']=True
            await click('Scenarios');await click('Save current scenario');await click('Save current scenario');await click('Compare saved scenarios');await asyncio.sleep(.8)
            assert await js("document.querySelector('table tbody tr')!==null")
            report['scenario_comparison']=True
            # Restore demo for the human's first run.
            await js("fetch('/api/factory/agent',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:'기본 공장을 설계해줘'})}).then(r=>r.json()).then(r=>fetch('/api/factory/proposals/'+r.proposal.id+'/apply',{method:'POST'}))")
            await click('▶ Run');await asyncio.sleep(5);await click('Pause');await click('Bottleneck')
            await shot('06-final-factory')
            report['body']=await js('document.body.innerText')
            report['canvas']=await js("[...document.querySelectorAll('canvas')].map(c=>({width:c.width,height:c.height}))")
            report['errors']=[e for e in events if e.get('method')=='Runtime.exceptionThrown']
            report['http_errors']=[e['params']['response']['url'] for e in events if e.get('method')=='Network.responseReceived' and e['params']['response']['status']>=400]
            report['websocket_frames']=sum(e.get('method')=='Network.webSocketFrameReceived' for e in events)
            assert not report['errors'],report['errors']
            assert not report['http_errors'],report['http_errors']
            print(json.dumps({k:v for k,v in report.items() if k in ['run_pause_time','canvas','errors','http_errors','websocket_frames','builder_roundtrip','scenario_comparison']},ensure_ascii=False))
    finally:
        (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        (OUT/'events.json').write_text(json.dumps(events,ensure_ascii=False))
        chrome.terminate()
        try:chrome.wait(timeout=8)
        except subprocess.TimeoutExpired:chrome.kill()
        log.close()
asyncio.run(main())
