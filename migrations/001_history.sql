CREATE TABLE IF NOT EXISTS aria_twin_revisions (
 site_id text NOT NULL, twin_revision bigint NOT NULL, site_definition_hash text NOT NULL,
 definition jsonb NOT NULL, model jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(site_id,twin_revision,site_definition_hash)
);
CREATE TABLE IF NOT EXISTS aria_runs (
 run_id text PRIMARY KEY, site_id text NOT NULL, twin_revision bigint NOT NULL,
 site_definition_hash text NOT NULL, seed bigint NOT NULL, started_at timestamptz NOT NULL,
 FOREIGN KEY(site_id,twin_revision,site_definition_hash) REFERENCES aria_twin_revisions
);
CREATE TABLE IF NOT EXISTS aria_events (
 event_id text PRIMARY KEY, run_id text NOT NULL REFERENCES aria_runs, twin_revision bigint NOT NULL,
 site_definition_hash text NOT NULL, sequence bigint NOT NULL CHECK(sequence>0),
 simulation_time double precision NOT NULL, wall_time timestamptz NOT NULL,
 site_id text NOT NULL, zone_id text, asset_id text, shipment_id text, workpiece_id text,
 event_type text NOT NULL, severity text NOT NULL, payload jsonb NOT NULL,
 correlation_id text, causation_id text, content_hash text NOT NULL,
 UNIQUE(run_id,sequence)
);
CREATE INDEX IF NOT EXISTS aria_events_asset_time ON aria_events(asset_id,wall_time);
CREATE INDEX IF NOT EXISTS aria_events_shipment ON aria_events(shipment_id,run_id,sequence);
CREATE INDEX IF NOT EXISTS aria_events_type_time ON aria_events(event_type,wall_time);
CREATE OR REPLACE VIEW aria_inspection_history AS SELECT * FROM aria_events WHERE event_type='production_inspection_result';
CREATE OR REPLACE VIEW aria_shipment_history AS SELECT * FROM aria_events WHERE shipment_id IS NOT NULL;
CREATE OR REPLACE VIEW aria_incidents AS SELECT * FROM aria_events WHERE severity IN ('warning','error');
