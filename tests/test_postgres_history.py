"""Opt-in integration tests against an isolated migrated history database."""
import copy,os
import pytest
from aria.persistence.repositories import PostgresEventStore,PostgresSpatialRepository,MemorySpatialRepository
from aria.persistence.contracts import PersistenceFault
DSN=os.environ.get('ARIA_TEST_POSTGRES_DSN')
pytestmark=pytest.mark.skipif(not DSN,reason='explicit isolated PostgreSQL fixture required')

def saved():
    s=PostgresEventStore(DSN)
    with s.connect() as c:
        row=c.execute('SELECT r.run_id,r.site_id,r.twin_revision,r.site_definition_hash,r.seed,r.started_at,t.definition,t.model FROM aria_runs r JOIN aria_twin_revisions t USING(site_id,twin_revision,site_definition_hash) WHERE (SELECT count(*) FROM aria_events e WHERE e.run_id=r.run_id)>500 LIMIT 1').fetchone()
    assert row,'Run the isolated lifecycle acceptance first'
    return s,dict(zip(['run_id','site_id','twin_revision','site_definition_hash','seed','started_at','definition','model'],row))

def test_postgis_matches_horizontal_contract_and_zone_membership():
    s,c=saved();r=PostgresSpatialRepository(s,c['site_id'],c['twin_revision'],c['site_definition_hash']);m=MemorySpatialRepository(c['definition'])
    assert r.get_assets_in_zone('ZONE-PRODUCTION')==m.get_assets_in_zone('ZONE-PRODUCTION')
    assert {e['id'] for e in r.get_nearby_assets([26,500,-24],8)}=={e['id'] for e in m.get_nearby_assets([26,0,-24],8)}
    with s.connect() as db:
        p=db.execute("SELECT ST_X(geom),ST_Y(geom),elevation_m,ST_SRID(geom) FROM aria_spatial_entities WHERE site_id=%s AND twin_revision=%s AND site_definition_hash=%s AND entity_id='MACHINE-01'",(c['site_id'],c['twin_revision'],c['site_definition_hash'])).fetchone()
    xyz=r.entities['MACHINE-01']['position'];assert p==(xyz[0],xyz[2],xyz[1],0)

def test_postgres_idempotency_and_revision_collision_rollback():
    s,c=saved();rows=s.read(c['run_id']);n=len(rows);s.append(rows,{c['run_id']:c});s.append(rows,{c['run_id']:c});assert len(s.read(c['run_id']))==n
    bad=copy.deepcopy(c);bad['model']['components'][0]['capacity']+=1
    with pytest.raises(PersistenceFault,match='different model'):s.append(rows,{c['run_id']:bad})
    badrow={**rows[0],'twin_revision':9999}
    with pytest.raises(PersistenceFault,match='revision mismatch'):s.append([badrow],{c['run_id']:c})
    assert s.read(c['run_id'])==rows

def test_postgres_history_is_ordered_and_paginated():
    s,c=saved();rows=s.read(c['run_id']);assert [e['sequence'] for e in rows]==list(range(1,len(rows)+1))
    assert s.read(c['run_id'],after=10,limit=5)==rows[10:15]
