CREATE EXTENSION IF NOT EXISTS postgis;
-- SRID 0: intentionally unreferenced engineering plane, unit metres by contract.
-- (ARIA x,y,z) => geometry(x,z) + elevation_m=y. Never WGS84.
CREATE TABLE IF NOT EXISTS aria_spatial_entities (
 site_id text NOT NULL, twin_revision bigint NOT NULL, site_definition_hash text NOT NULL,
 entity_id text NOT NULL, section text NOT NULL, kind text NOT NULL, parent_id text,
 geom geometry(Geometry,0) NOT NULL, elevation_m double precision NOT NULL,
 metadata jsonb NOT NULL,
 PRIMARY KEY(site_id,twin_revision,site_definition_hash,entity_id),
 FOREIGN KEY(site_id,twin_revision,site_definition_hash) REFERENCES aria_twin_revisions
);
CREATE INDEX IF NOT EXISTS aria_spatial_geometry ON aria_spatial_entities USING gist(geom);
CREATE INDEX IF NOT EXISTS aria_spatial_parent ON aria_spatial_entities(site_id,site_definition_hash,parent_id);
