import asyncio
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from aria.simulation.des.service import FactoryService


def test_api_proposals_controls_and_chat(tmp_path, monkeypatch):
    from server.routers import factory
    monkeypatch.setattr(factory, 'service', FactoryService(tmp_path))
    app = FastAPI();app.include_router(factory.router)
    async def run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            snapshot=(await client.get('/api/factory/snapshot')).json()
            assert snapshot['status']=='paused'
            invalid=await client.post('/api/factory/run',json={'speed':'bad'})
            assert invalid.status_code==422
            p=(await client.patch('/api/factory/components/MACHINE-01',json={'capacity':2})).json()
            forbidden=await client.post('/api/factory/tools/apply_factory_change',json={'id':p['id']})
            assert forbidden.status_code==409
            result=await client.post(f"/api/factory/proposals/{p['id']}/apply")
            assert result.status_code==200
            assert result.json()['revision']==1
            assert (await client.post('/api/factory/step',json={})).json()['metrics']['generated']>0
            assert (await client.post('/api/factory/reset',json={})).json()['metrics']['generated']==0
            result=(await client.post('/api/factory/agent',json={'message':'현재 병목을 분석해줘'})).json()
            assert result['trace']
            assert 'error' not in result
            invalid=await client.post('/api/factory/components',json={'id':'BAD','kind':'Machine','processing_time':-1})
            assert invalid.status_code==422
    asyncio.run(run())


def test_mcp_requires_human_approval():
    from aria.mcp.servers.factory_mcp import factory_tool
    with pytest.raises(ValueError, match='human-only'):
        factory_tool('apply_factory_change', {'id':'any'})


def test_patrol_fault_report_and_controls(tmp_path, monkeypatch):
    from server.routers import factory
    from aria.simulation.des.patrol import PatrolSupervisor
    monkeypatch.setattr(factory, 'service', FactoryService(tmp_path))
    monkeypatch.setattr(factory, 'patrol', PatrolSupervisor(tmp_path))
    app = FastAPI(); app.include_router(factory.router)
    async def run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            invalid = await client.post('/api/factory/patrol/fault', json={'component':'SOURCE-01','duration':60})
            assert invalid.status_code == 422
            result = await client.post('/api/factory/patrol/fault', json={'component':'MACHINE-01','duration':60})
            assert result.status_code == 200
            incident = next(r for r in result.json()['reports'] if r['kind']=='equipment_down')
            assert incident['evidence']['state']=='DOWN'
            assert incident['verified_by'] is None
            duplicate = await client.post('/api/factory/patrol/fault', json={'component':'MACHINE-01','duration':60})
            assert duplicate.status_code == 422
            paused = await client.post('/api/factory/patrol/control', json={'enabled':False})
            assert paused.json()['enabled'] is False
            report = await client.get('/api/factory/patrol/report')
            assert incident['id'] in report.text and 'DOWN' in report.text
            answer = (await client.post('/api/factory/agent',json={'message':'문제 보고서'})).json()
            assert answer['trace'][0]['tool']=='get_patrol_report'
    asyncio.run(run())
