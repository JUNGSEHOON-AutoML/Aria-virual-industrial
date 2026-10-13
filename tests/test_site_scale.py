import copy
import json
import pytest
from aria.simulation.des.engine import Engine
from aria.simulation.des.model import demo_factory
from aria.simulation.site.contract import build_site, SiteDefinition
from aria.simulation.site.runtime import SiteRuntime, RouteNetwork, TRUCK_STATES, FORKLIFT_STATES, DOCK_STATES

def advance(site, seconds):
    site.control('run')
    for _ in range(int(seconds*10)):
        site.tick(.1)
        if site.status in ('completed','error'):break
    assert site.error is None,site.error
    return site.snapshot()

def test_static_contract_reference_validation_and_no_runtime_entities():
    d=build_site(demo_factory()).model_dump();assert d['synthetic']
    assert not {'trucks','shipments','pallets','workpieces'} & d.keys()
    d['transport_edges'][0]['target']='missing'
    with pytest.raises(ValueError):SiteDefinition.model_validate(d)

def test_external_admission_and_backpressure_preserve_legacy_arrivals():
    m=demo_factory();legacy=Engine(m);legacy.run_until(1);assert legacy.serial>0
    e=Engine(m,external_sources=['SOURCE']);e.run_until(5);assert e.serial==0
    assert e.admit_external('SOURCE',workpiece_id='W1',shipment_id='S1',pallet_id='P1')
    with pytest.raises(ValueError,match='Duplicate'):e.admit_external('SOURCE',workpiece_id='W1',shipment_id='S1',pallet_id='P1')
    e.nodes['SOURCE']['down']=True
    assert not e.admit_external('SOURCE',workpiece_id='W2',shipment_id='S1',pallet_id='P1')
    assert e.serial==1

def test_full_causal_demo_and_conservation():
    s=SiteRuntime(demo_factory().model_dump());static=copy.deepcopy(s.definition.model_dump())
    # Automatic Source is disabled; no workpiece exists before real pallet delivery.
    first=advance(s,15);assert first['production']['metrics']['generated']==0
    final=advance(s,1500)
    assert s.status=='completed'
    assert all(x['state']=='DEPARTED' for x in final['shipments'])
    assert final['production']['metrics']['generated']==9
    assert final['production']['metrics']['completed']==9
    assert len({x['id'] for x in final['workpieces']})==9
    assert s.definition.model_dump()==static
    json.dumps(final,allow_nan=False)
    events=list(s.events)
    for shipment in final['shipments']:
        sid=shipment['id'];rows=[e for e in events if e.get('shipment_id')==sid]
        for stage in ['gate_passed','dock_assigned','pallet_unloaded','production_external_material_admitted','production_inspection_result','production_part_exit','finished_goods_staged','shipment_departed']:
            assert any(e['type']==stage for e in rows),(sid,stage)
        admitted=min(e['time'] for e in rows if e['type']=='production_external_material_admitted')
        delivered=min(e['time'] for e in rows if e['type']=='pallet_delivered' and e['purpose']=='production')
        assert admitted>=delivered
        departed=next(e for e in rows if e['type']=='shipment_departed')
        assert set(departed['workpiece_ids'])==set(shipment['good_ids'])
        assert not set(shipment['reject_ids']) & set(departed['workpiece_ids'])
        assert set(final['pallets'][list(s.shipments).index(sid)]['workpiece_ids'])==set(shipment['good_ids'])
    states={e['state'] for e in events if 'state' in e}
    assert {'ARRIVING','WAITING','ASSIGNED_TO_DOCK','DRIVING','DOCKED','LOADING','UNLOADING','DEPARTING','IDLE','ASSIGNED','TO_PICKUP','TO_DESTINATION','RETURNING'}<=states

def test_routes_use_valid_edges_and_vehicle_modes():
    s=SiteRuntime(demo_factory().model_dump());n=s.network
    for mode,start,end in [('truck','GATE-01','DOCK-A01-N'),('forklift','FORK-HOME-N','DOCK-B01-N')]:
        route=n.route(start,end,mode)
        for a,b in zip(route,route[1:]):assert any(mode in e.modes and {a,b}=={e.source,e.target} for e in n.edges)
    with pytest.raises(ValueError):n.route('GATE-01','PRODUCTION-IN-01-N','truck')

def test_pause_fixed_timestep_determinism_and_reset():
    a=SiteRuntime(demo_factory().model_dump());b=SiteRuntime(demo_factory().model_dump())
    a.control('run');b.control('run')
    for _ in range(400):a.tick(.1)
    for _ in range(80):b.tick(.5)
    for key in ['trucks','forklifts','pallets','workpieces']:
        assert a.snapshot()[key]==b.snapshot()[key],key
    a.control('pause');before=a.snapshot();a.tick(.9);after=a.snapshot();assert before==after
    a.control('step');assert a.time==40.1
    a.reset();assert a.time==0 and not a.engine.external_parts
    assert all(s['state']=='PLANNED' for s in a.shipments.values())

def test_blocked_docks_waiting_reason_and_query_no_mutation():
    s=SiteRuntime(demo_factory().model_dump())
    s.block_dock('DOCK-A01',True);s.block_dock('DOCK-A02',True)
    advance(s,20);assert s.trucks['TRUCK-02']['state']=='WAITING'
    before=s.snapshot();q=s.query('Why is TRUCK-02 still waiting?');assert q['trace'][0]['tool']=='get_site_entity'
    assert 'No available inbound_dock' in q['answer'];assert s.snapshot()==before
    assert '지원하지' in s.query('What change would improve total site throughput?')['answer']
    s.block_dock('DOCK-A01',False);advance(s,2);assert s.trucks['TRUCK-01']['state']!='WAITING'

def test_missing_real_inspection_is_held_not_fake_ok():
    m=demo_factory();c=next(c for c in m.components if c.kind=='Inspection');c.inspection_mode='ccifps'
    s=SiteRuntime(m.model_dump());end=advance(s,1500)
    assert end['production']['metrics']['counts']['SKIPPED']==9
    assert all(x['state']=='ON_HOLD' for x in end['shipments'])
    assert not any(x['state']=='DEPARTED' for x in end['shipments'])
    assert not any(e['type']=='shipment_departed' for e in s.events)


def test_site_api_scope_isolation_and_bounded_controls(tmp_path,monkeypatch):
    import asyncio
    from fastapi import FastAPI
    from httpx import AsyncClient,ASGITransport
    from server.routers import factory
    from aria.simulation.des.service import FactoryService
    standalone=FactoryService(tmp_path)
    site=SiteRuntime(standalone.engine.model.model_dump())
    monkeypatch.setattr(factory,'service',standalone);monkeypatch.setattr(factory,'site',site)
    broadcasts=[]
    async def capture(message):broadcasts.append(message)
    monkeypatch.setattr(factory.manager,'broadcast',capture)
    app=FastAPI();app.include_router(factory.router)
    async def run():
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as c:
            definition=(await c.get('/api/factory/site/definition')).json();assert definition['synthetic']
            result=(await c.post('/api/factory/site/control/run',json={'speed':20})).json();assert result['status']=='running'
            assert standalone.engine.status=='paused'
            site.tick(.5);assert site.time==10
            assert (await c.post('/api/factory/site/control/run',json={'speed':999})).status_code==422
            r=(await c.post('/api/factory/agent',json={'scope':'site','message':'Where is SHIPMENT-101?'})).json()
            assert r['route']=='deterministic site tools';assert r['evidence']['entity']['id']=='SHIPMENT-101'
            assert not r['proposal']
            assert all(e['scope']=='site' for e in broadcasts if e.get('type','').startswith('agent_'))
            assert any(e['type']=='agent_result' for e in broadcasts)
            assert (await c.get('/api/factory/site/entities/UNKNOWN')).status_code==404
            q=(await c.post('/api/factory/agent',json={'scope':'site','message':'Where is SHIPMENT-104?'})).json();assert q['evidence']['unsupported']=='unknown entity ID'
            await c.post('/api/factory/site/control/pause',json={});before=site.time;site.tick(1);assert site.time==before
            await c.post('/api/factory/site/control/reset',json={});assert site.time==0 and site.engine.serial==0
    asyncio.run(run())


def test_all_ng_fixture_is_quarantined_not_loaded():
    m=demo_factory();next(c for c in m.components if c.kind=='Inspection').defect_rate=1
    s=SiteRuntime(m.model_dump());r=advance(s,1500)
    assert r['production']['metrics']['counts']['NG']==9
    assert r['metrics']['departed_shipments']==0
    assert all(x['state']=='ON_HOLD' for x in r['shipments'])
    assert not any(e['type']=='shipment_departed' for e in s.events)


def test_mixed_inspection_fixture_only_loads_accepted_workpieces():
    m=demo_factory();next(c for c in m.components if c.kind=='Inspection').inspection_mode='ccifps'
    # Explicit stub, not a claim of CCIFPS inference: one rejected unit per pallet.
    def fixture_inspect(component, part):
        return {'verdict':'NG' if part['serial']%3==0 else 'OK','mode':'test_fixture'}
    s=SiteRuntime(m.model_dump(),fixture_inspect);r=advance(s,1500)
    assert r['production']['metrics']['counts']['OK']==6
    assert r['production']['metrics']['counts']['NG']==3
    assert r['metrics']['departed_shipments']==3
    assert r['metrics']['reject_units']==3
    for sh in r['shipments']:
        pallet=s.pallets[sh['pallet_id']]
        assert len(pallet['workpiece_ids'])==2
        assert set(pallet['workpiece_ids'])==set(sh['good_ids'])
        assert not set(sh['reject_ids']) & set(pallet['workpiece_ids'])
        event=next(e for e in s.events if e['type']=='shipment_departed' and e['shipment_id']==sh['id'])
        assert set(event['workpiece_ids'])==set(sh['good_ids'])
