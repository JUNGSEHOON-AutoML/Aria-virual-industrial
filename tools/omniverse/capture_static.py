"""Capture shared Three.js prefabs using an isolated CPU browser. No API traffic."""
import argparse
import asyncio
import base64
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time
import httpx
import websockets

ROOT = Path(__file__).resolve().parents[2]


async def capture(url, output, dashboard=False):
    sources = json.loads((Path(__file__).parent/'sources.json').read_text())
    def hashes():
        return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}
    initial_hashes = hashes()
    output.parent.mkdir(parents=True, exist_ok=True)
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    log = output.with_suffix('.chrome.log').open('w')
    proc = subprocess.Popen(['/usr/bin/google-chrome', '--headless=new', '--no-sandbox', '--disable-dev-shm-usage',
        '--disable-gpu', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
        f'--remote-debugging-port={port}', f'--user-data-dir=/tmp/cnotta-usd-{time.time_ns()}', 'about:blank'], stdout=log, stderr=log)
    events = []
    try:
        for _ in range(100):
            try:
                tab = next(t for t in httpx.get(f'http://127.0.0.1:{port}/json/list').json() if t['type'] == 'page')
                break
            except (httpx.HTTPError, StopIteration):
                await asyncio.sleep(.2)
        else:
            raise RuntimeError('CPU browser did not start')
        async with websockets.connect(tab['webSocketDebuggerUrl'], max_size=100_000_000) as ws:
            seq = 0
            async def cmd(method, params=None):
                nonlocal seq
                seq += 1
                await ws.send(json.dumps(dict(id=seq, method=method, params=params or {})))
                while True:
                    reply = json.loads(await asyncio.wait_for(ws.recv(), 90))
                    if reply.get('id') == seq:
                        if 'error' in reply:
                            raise RuntimeError(reply['error'])
                        return reply.get('result', {})
                    events.append(reply)
            async def js(expression):
                reply = await cmd('Runtime.evaluate', dict(expression=expression, returnByValue=True, awaitPromise=True))
                if 'exceptionDetails' in reply:
                    raise RuntimeError(reply['exceptionDetails'])
                return reply.get('result', {}).get('value')
            await cmd('Runtime.enable')
            await cmd('Network.enable')
            await cmd('Page.enable')
            await cmd('Emulation.setDeviceMetricsOverride', dict(width=1440, height=900, deviceScaleFactor=1, mobile=False))
            await cmd('Page.navigate', dict(url=url))
            for _ in range(120):
                target = '__campus' if dashboard else '__usdExport'
                if await js(f'!!window.{target}?.scene?.getObjectByName("wordmark-hall-carpet")'):
                    break
                await asyncio.sleep(.25)
            else:
                raise RuntimeError('Static export scene not ready')
            await asyncio.sleep(1)
            data = await js("import('/src/omniverse/serialize.js').then(m=>m.snapshot(window.__campus.scene))" if dashboard else 'window.__usdExport.snapshot()')
            data['renderer'] = await js(f'window.{target}.renderer')
            if isinstance(data['renderer'], dict):
                data['renderer'] = data['renderer'].get('renderer', str(data['renderer']))
            if 'SwiftShader' not in data['renderer']:
                raise RuntimeError('CPU renderer required')
            data['errors'] = [e for e in events if e.get('method') == 'Runtime.exceptionThrown']
            responses = [e['params']['response'] for e in events if e.get('method') == 'Network.responseReceived']
            data['http_errors'] = [r['url'] for r in responses if r['status'] >= 400]
            api = [e['params']['request'] for e in events if e.get('method') == 'Network.requestWillBeSent' and '/api/' in e['params']['request']['url']]
            data['api_requests'] = [r['url'] for r in api]
            if data['errors'] or data['http_errors'] or (api and not dashboard) or any(r['method'] != 'GET' for r in api):
                raise RuntimeError('Static capture had errors/API traffic: ' + str([data['errors'], data['http_errors'], data['api_requests']]))
            if initial_hashes != hashes():
                raise RuntimeError('Sources changed during capture; run again')
            data['source_hashes'] = initial_hashes
            data['capture_mode'] = 'dashboard_readonly' if dashboard else 'isolated_static'
            if dashboard:
                data['web_audit'] = await js('window.__campus.audit()')
            output.write_text(json.dumps(data, separators=(',', ':'), ensure_ascii=False) + '\n')
            shot = await cmd('Page.captureScreenshot', dict(format='png'))
            output.with_suffix('.png').write_bytes(base64.b64decode(shot['data']))
            print(json.dumps(dict(nodes=len(data['nodes']), geometries=len(data['geometries']), materials=len(data['materials']), bounds=data['worldBounds'], renderer=data['renderer'])))
    finally:
        proc.terminate()  # Only this tool's own CPU browser child.
        proc.wait(timeout=15)
        log.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:5278/usd-export.html')
    parser.add_argument('--output', type=Path, default=ROOT/'docs/autopilot/local/usd-web.json')
    parser.add_argument('--dashboard', action='store_true', help='Read the actual Replay scene without controls')
    args = parser.parse_args()
    asyncio.run(capture(args.url, args.output, args.dashboard))
