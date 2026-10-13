import json
import sqlite3
import time
import pytest
from aria.persistence.contracts import PersistenceFault,envelope,digest,utcnow
from aria.persistence.repositories import InMemoryEventStore,MemorySpatialRepository,planar
from aria.persistence.writer import DurableWriter,Limits
from aria.simulation.des.model import demo_factory
from aria.simulation.site.runtime import SiteRuntime

def context():
    s=SiteRuntime(demo_factory().model_dump());return s.history_context

def event(ctx,n):return envelope(dict(id=f"{ctx['run_id']}:{n}",sequence=n,time=n*.1,type='test',component='MACHINE-01'),ctx)
def wait_for(fn):
    until=time.monotonic()+4
    while time.monotonic()<until:
        if fn():return
        time.sleep(.02)
    assert fn()
class SwitchStore(InMemoryEventStore):
    mode='test-outage'
    down=False
    def append(self,*a):
        if self.down:raise ConnectionError('Explicit test DB outage')
        return super().append(*a)

def test_append_duplicate_order_and_collision():
    s=InMemoryEventStore();c=context();e=event(c,1);s.append([e,e],{c['run_id']:c});assert len(s.read(c['run_id']))==1
    s.append([event(c,3),event(c,2)],{c['run_id']:c});assert [e['sequence'] for e in s.read(c['run_id'])]==[1,2,3]
    with pytest.raises(PersistenceFault):s.append([{**e,'content_hash':'different'}],{})

def test_durable_spool_outage_shutdown_restart_replay(tmp_path):
    s=SwitchStore();s.down=True;c=context();limits=Limits(retry_min=.02,retry_max=.04,shutdown_timeout=.05)
    w=DurableWriter(s,tmp_path,limits);w.register(c)
    events=[event(c,n) for n in range(1,5)]
    for e in events:w.submit(e)
    wait_for(lambda:w.health()['persistence_status']=='DEGRADED');assert w.health()['queue_depth']==4
    assert not w.close()
    s.down=False;w=DurableWriter(s,tmp_path,limits);assert w.flush(4);assert len(s.read(c['run_id']))==4
    for e in events:w.submit(e)
    assert w.flush(4);assert len(s.read(c['run_id']))==4
    assert w.health()['checkpoints'][c['run_id']]['last_persisted_sequence']==4
    assert w.close()

def test_spool_corruption_detected_preserved(tmp_path):
    s=SwitchStore();s.down=True;c=context();w=DurableWriter(s,tmp_path,Limits(shutdown_timeout=.02));w.register(c);w.submit(event(c,1));w.close()
    with sqlite3.connect(tmp_path/'spool.sqlite3') as db:db.execute("UPDATE pending SET body='{}'")
    w=DurableWriter(s,tmp_path,Limits(shutdown_timeout=.02));wait_for(lambda:w.health()['persistence_status']=='FAULT');assert w.health()['queue_depth']==1;w.close()

def test_single_owner_and_queue_pressure(tmp_path):
    s=SwitchStore();s.down=True;c=context();w=DurableWriter(s,tmp_path,Limits(queue_size=1,shutdown_timeout=.02));w.register(c)
    with pytest.raises(PersistenceFault,match='owned'):DurableWriter(s,tmp_path)
    w.submit(event(c,1))
    with pytest.raises(PersistenceFault,match='queue full'):w.can_advance()
    w.close()

def test_spatial_axes_and_membership():
    d=SiteRuntime(demo_factory().model_dump()).definition.model_dump();r=MemorySpatialRepository(d)
    assert planar([3,8,4])==((3.,4.),8.)
    assert 'MACHINE-01' in {e['id'] for e in r.get_assets_in_zone('ZONE-PRODUCTION')}
    e=next(e for e in d['assets'] if e['id']=='MACHINE-01');p=e['position'];assert any(x['id']==e['id'] for x in r.get_nearby_assets([p[0],p[1]+100,p[2]],0))
    with pytest.raises(ValueError):r.get_nearby_assets([0,0,0],-1)

def test_site_durable_history_preserves_simulation(tmp_path):
    store=InMemoryEventStore();w=DurableWriter(store,tmp_path);a=SiteRuntime(demo_factory().model_dump(),history=w);b=SiteRuntime(demo_factory().model_dump());a.control('run');b.control('run')
    for _ in range(600):a.tick(.1);b.tick(.1)
    for k in ('trucks','forklifts','pallets','workpieces'):assert a.snapshot()[k]==b.snapshot()[k]
    assert w.flush();events=store.read(a.run_token);assert len(events)==a.sequence
    assert all(e['site_definition_hash']==digest(a.definition.model_dump()) for e in events)
    assert all(e['twin_revision']==a.revision for e in events);w.close()


def test_process_crash_replays_synced_spool(tmp_path):
    import subprocess,sys
    script='''
import os,sys
from aria.persistence.repositories import InMemoryEventStore
from aria.persistence.writer import DurableWriter
from aria.persistence.contracts import envelope
from aria.simulation.site.runtime import SiteRuntime
from aria.simulation.des.model import demo_factory
class Down(InMemoryEventStore):
 def append(self,*a):raise ConnectionError('offline')
c=SiteRuntime(demo_factory().model_dump()).history_context
w=DurableWriter(Down(),sys.argv[1]);w.register(c)
for n in range(1,4):w.submit(envelope(dict(id=c['run_id']+':'+str(n),sequence=n,time=n,type='crash_test'),c))
print(c['run_id'],flush=True)
os._exit(0)
'''
    p=subprocess.run([sys.executable,'-c',script,str(tmp_path)],capture_output=True,text=True,check=True)
    s=InMemoryEventStore();w=DurableWriter(s,tmp_path);assert w.flush(4);assert len(s.read(p.stdout.strip()))==3;w.close()

def test_disk_limit_and_lag_are_explicit(tmp_path):
    s=SwitchStore();s.down=True;c=context();w=DurableWriter(s,tmp_path,Limits(max_lag=.02,shutdown_timeout=.02));w.register(c);w.submit(event(c,1));time.sleep(.04)
    with pytest.raises(PersistenceFault,match='lag'):w.can_advance()
    w.close()
    w=DurableWriter(s,tmp_path,Limits(spool_bytes=1,shutdown_timeout=.02))
    with pytest.raises(PersistenceFault,match='Durable append failed'):w.submit(event(c,2))
    assert w.health()['persistence_status']=='FAULT'
    with pytest.raises(PersistenceFault,match='uncommitted'):w.close()



def test_shutdown_waits_for_inflight_runtime_tick(monkeypatch):
    import threading
    from types import SimpleNamespace
    from server.routers import factory
    lock=threading.RLock();entered=threading.Event();release=threading.Event();order=[]
    site=SimpleNamespace(lock=lock,status='running',engine=SimpleNamespace(status='running'))
    monkeypatch.setattr(factory,'site',site)
    monkeypatch.setattr(factory,'history',SimpleNamespace(close=lambda:order.append('close')))
    def tick():
        with lock:entered.set();release.wait(2);order.append('tick_done')
    t=threading.Thread(target=tick);t.start();assert entered.wait(1)
    stop=threading.Thread(target=factory.shutdown_history);stop.start();time.sleep(.02);assert not order
    release.set();t.join();stop.join();assert order==['tick_done','close'];assert site.status=='paused'
