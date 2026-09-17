import asyncio,json
from pathlib import Path
import pytest
from fastapi import FastAPI
from httpx import AsyncClient,ASGITransport
from aria.cad.service import CADService,CNCParameters
from aria.simulation.des import Engine,demo_factory
from aria.simulation.des.service import FactoryService

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'outputs/cad-runtime/squashfs-root'

def test_cad_input_and_asset_boundaries(tmp_path):
 for payload in ({'width_mm':99999},{'height_mm':float('nan')},{'script':'untrusted'},{'depth_mm':-1}):
  with pytest.raises(ValueError):CNCParameters.model_validate(payload)
 service=CADService(tmp_path)
 for aid in ('../report.json','a'*25,'g'*24):
  with pytest.raises(ValueError):service.asset(aid)
 with pytest.raises(FileNotFoundError):service.asset('a'*24)
 with pytest.raises(RuntimeError,match='unavailable'):service.build({})

@pytest.mark.skipif(not RUNTIME.exists(),reason='Install optional pinned FreeCAD runtime first')
@pytest.mark.parametrize('width',[1800,2500,3000])
def test_real_freecad_solids_units_exports_and_cache(tmp_path,width):
 service=CADService(tmp_path);service.runtime=RUNTIME
 a=service.build({'width_mm':width});r=a['report'];folder=service.directory/a['id']
 assert r['version']=='1.1.3' and r['all_solids_valid'] and r['parts']==16
 assert r['static_interferences']==[]
 assert r['envelope_mm']['width']==pytest.approx(width)
 mesh=json.loads((folder/'mesh.json').read_text());assert mesh['units']=='m' and mesh['up_axis']=='Y'
 xs=[v for part in mesh['meshes'] for v in part['positions'][0::3]]
 ys=[v for part in mesh['meshes'] for v in part['positions'][1::3]]
 assert max(xs)-min(xs)==pytest.approx(width/1000)
 assert max(ys)==pytest.approx(2.6)
 assert (folder/'cnc.FCStd').read_bytes().startswith(b'PK')
 assert 'ISO-10303-21' in (folder/'cnc.step').read_text()
 stamp=(folder/'report.json').stat().st_mtime_ns
 assert service.build({'width_mm':width})['id']==a['id']
 assert (folder/'report.json').stat().st_mtime_ns==stamp

@pytest.mark.skipif(not RUNTIME.exists(),reason='Install optional pinned FreeCAD runtime first')
def test_cad_http_requires_existing_approval_flow(tmp_path,monkeypatch):
 from server.routers import cad,factory
 cs=CADService(tmp_path);cs.runtime=RUNTIME
 fs=FactoryService(tmp_path/'factory')
 monkeypatch.setattr(cad,'service',cs);monkeypatch.setattr(factory,'service',fs)
 app=FastAPI();app.include_router(cad.router);app.include_router(factory.router)
 async def run():
  async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as c:
   assert (await c.post('/api/factory/cad/build',json={'component':'SOURCE'})).status_code==422
   invalid=await c.post('/api/factory/cad/build',json={'component':'MACHINE-01','parameters':{'width_mm':4000}})
   assert invalid.status_code==422
   result=await c.post('/api/factory/cad/build',json={'component':'MACHINE-01','parameters':{'width_mm':2800}})
   assert result.status_code==200,result.text
   data=result.json();aid=data['asset']['id'];proposal=data['proposal']
   assert fs.engine.nodes['MACHINE-01']['c'].cad_asset=='' and proposal['status']=='pending'
   artifact=await c.get(data['asset']['files']['mesh.json']);assert artifact.status_code==200
   assert (await c.get(f'/api/factory/cad/assets/{aid}/secret.txt')).status_code==404
   before=Engine(fs.engine.model).run_until(60)
   applied=await c.post(f"/api/factory/proposals/{proposal['id']}/apply")
   assert applied.status_code==200
   assert fs.engine.nodes['MACHINE-01']['c'].cad_asset==aid
   assert Engine(fs.engine.model).run_until(60)==before
 asyncio.run(run())


def test_cad_routes_registered_once():
 import warnings
 from server.app import create_app
 with warnings.catch_warnings():
  warnings.simplefilter('error',UserWarning)
  schema=create_app().openapi()
 assert len([p for p in schema['paths'] if p.startswith('/api/factory/cad')])==4
