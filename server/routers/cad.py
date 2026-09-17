"""CAD artifacts and explicit proposals share the existing factory model owner."""
import asyncio
from pathlib import Path
from fastapi import APIRouter,HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel,ConfigDict,Field
from aria.cad.service import CADService,CNCParameters
from server.routers import factory

router=APIRouter(prefix='/api/factory/cad',tags=['CAD'])
service=CADService(Path(__file__).resolve().parents[2])
class BuildRequest(BaseModel):
 model_config=ConfigDict(extra='forbid')
 component:str=Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
 parameters:CNCParameters=CNCParameters()

@router.get('/status')
async def status():return service.status()
@router.get('/assets/{aid}')
async def asset(aid:str):
 try:return service.asset(aid)
 except ValueError as e:raise HTTPException(422,str(e)) from e
 except FileNotFoundError as e:raise HTTPException(404,str(e)) from e
@router.get('/assets/{aid}/{filename}')
async def file(aid:str,filename:str):
 if filename not in ('mesh.json','cnc.FCStd','cnc.step','report.json'):raise HTTPException(404,'Unknown artifact')
 await asset(aid)
 return FileResponse(service.directory/aid/filename,filename=filename,media_type='application/json' if filename.endswith('.json') else 'application/octet-stream')
@router.post('/build')
async def build(payload:BuildRequest):
 def generate():
  with factory.service.lock:
   node=factory.service.engine.nodes.get(payload.component)
   if not node or node['c'].kind!='Machine':raise ValueError('Select an existing Machine')
   revision=factory.service.revision
  result=service.build(payload.parameters.model_dump())
  if result['report']['static_interferences']:raise ValueError('CAD bodies overlap; attachment blocked')
  with factory.service.lock:
   if revision!=factory.service.revision:raise ValueError('Factory changed during CAD build; retry')
   proposal=factory.service.call('update_component',dict(id=payload.component,changes=dict(cad_asset=result['id'])))
  return dict(asset=result,proposal=proposal)
 try:return await asyncio.to_thread(generate)
 except (ValueError,FileNotFoundError) as e:raise HTTPException(422,str(e)) from e
 except (RuntimeError,TimeoutError) as e:raise HTTPException(503,str(e)) from e
