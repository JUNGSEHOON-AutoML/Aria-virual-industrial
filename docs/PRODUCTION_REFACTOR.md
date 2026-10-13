# ARIA production refactor: runtime, visual assets and durable history

## Boundaries

The deterministic `SiteRuntime` / DES owns live factory truth. PostgreSQL stores immutable historical records and approved static revisions. No PostgreSQL query occurs in a simulation tick. The current slice persists **site** events, including its production/inspection events. Independent Engineering patrol records retain their existing storage; this slice does not migrate every legacy subsystem.

Rendering uses React/Vite/R3F/Zustand and the existing native WebSocket transport. The live bounded deque is retained. Human proposal Apply/Reject, CCIFPS verdicts, robot joint hierarchy and logistics dispatch are unchanged. Redis, Socket.IO, Next.js, NestJS and RAG frameworks were not introduced.

## Visual asset registry

`config/assets/registry.json` contains asset ID, format/URI, version/hash, units/up axis/origin, bounds policy, provenance/license, LOD, instancing and fallback metadata. Procedural hashes identify the parameter generator bytes. Existing CAD/URDF entries explicitly leave an unverified content hash null; that is not an integrity guarantee. CAD and robot loaders remain their existing verified paths.

`frontend/src/features/twin/assets/VisualAsset.jsx` resolves `visual_asset_id`. The measured high contributors migrated are **fences and pallets**, not unrelated campus decoration. Each assembly has one box instance batch with per-instance color. Parent transforms and click bubbling retain the canonical equipment ID. Exact primitive dimensions, count and material parameters are preserved. No robot joints, CAD bodies, or independently selectable equipment are merged.

Other registered formats are extension points. No production GLB was substituted for verified CAD/URDF geometry. The GLB loader is lazy; no codec is added. Unknown bindings are rejected, configured fallback IDs validated (including cycles), and GLB load failure can render the supplied/registered fallback. GLB end-to-end artwork validation remains separate from this procedural migration.

### Optional Blender pipeline

1. Author in metres, Y-up export, explicit pivot/origin. Preserve per-equipment identity and articulated joint hierarchy.
2. Export glTF 2.0 GLB; inspect physical bounds, axes, material count, animations and license/provenance.
3. Validate the glTF artifact and compare measured dimensions against its source before accepting it.
4. Only if a measured bottleneck warrants it, optimize meshes/textures. Document changed triangle count, material/draw submissions, decode cost and download bytes. GLB conversion alone is not optimization.
5. Register immutable URI, version, SHA-256, origin, bounds and fallback; route it through the lazy loader.
6. Measure equivalent camera/runtime/renderer conditions and exercise selection and failed-loading fallback before replacing a production asset.

No Meshopt/Draco/KTX2 dependency is installed in this slice. Add a decoder only when an accepted asset requires it and measurements justify it.

## Explicit history backend

Default minimal-development mode is `ARIA_HISTORY_BACKEND=memory`, reported as `VOLATILE_DEVELOPMENT`. It does not promise restart survival. PostgreSQL mode requires `ARIA_HISTORY_DSN`; no automatic memory fallback exists.

Optional Python dependency: `requirements-history.txt`. Install into a chosen environment. For local containers, `docker compose -f compose.history.yml up -d` starts only the opt-in history DB with a persistent volume and loopback port. Set `ARIA_LOCAL_DB_PASSWORD` privately. This compose file is independent from the repository's GPU compose configuration.

Apply migrations explicitly with `PYTHONPATH=. python tools/migrate_history.py` after setting `ARIA_HISTORY_DSN`. Configure `ARIA_HISTORY_BACKEND=postgres` and `ARIA_HISTORY_SPOOL` on a persistent local filesystem before starting one API worker. The same spool cannot be shared by two writers; a process-lifetime file lock enforces this.

The optional container recipe uses PostGIS 16/3.4. This environment lacked Docker socket access, so actual acceptance used an isolated existing PostgreSQL 12.22 binary plus extracted PostGIS 3.0.0 libraries, without modifying the system install. The container recipe has not been execution-validated here. Deployment should validate its chosen supported DB version independently.

## Schema and coordinates

- `001_history.sql`: `aria_twin_revisions`, `aria_runs`, append-only repository writes to `aria_events`.
- Stable event columns: identity, run/revision/site hash, sequence, simulation/wall time, site/zone/asset/shipment/workpiece, event type/severity, correlation/causation, content hash. Event-specific fields stay in JSONB `payload`.
- Unique `(run_id,sequence)` and event ID. A conflicting identity with different content is an error, not an overwrite.
- `aria_inspection_history`, `aria_shipment_history`, `aria_incidents` are **views over persisted events**, not duplicate mutable history tables. Independent patrol incident migration remains future work.
- `002_spatial.sql`: PostGIS anchors and transport lines in `aria_spatial_entities`, versioned by site + revision + definition hash, with GiST and hierarchy indexes.
- Local metre coordinates only: runtime `(x,y,z)` maps to geometry `(x,z)` and `elevation_m=y`. **SRID 0** explicitly means no geographical reference. Never EPSG:4326; no latitude/longitude or GPS is fabricated.
- Nearby query measures horizontal Euclidean distance between asset anchors. It is not 3D clearance or collision distance. Zone membership follows the approved parent hierarchy, not point-in-footprint inference. Sizes remain in the static metadata; this slice does not create survey-quality building footprints.
- Static reads are loaded into a repository snapshot for the selected revision. Dynamic vehicle locations remain the live runtime API's responsibility.
- Reusing a revision/hash for a different static model is rejected. Seed is recorded per run. Causation ID stays null when the source event does not supply a verified parent cause.

## Durability and failure semantics

The local spool is **SQLite WAL with synchronous=FULL**, not PostgreSQL and not an authoritative simulation state store. It is the bounded persistence queue itself: accepted events are synchronously committed to local disk, then an independent writer batches network DB writes. This avoids a volatile queue-to-disk gap. Local fsync cost remains on event production; no network round trip occurs there.

1. Register the immutable run context in the spool.
2. Append an envelope and checksum, commit locally before submit returns.
3. Writer reads FIFO rows and contexts, validates checksums and sends an atomic DB batch.
4. Only after DB commit succeeds, remove acknowledged rows and advance per-run persisted checkpoints.
5. Checkpoint/truncate SQLite WAL and reclaim free pages. A crash after DB commit but before local deletion replays the batch; DB uniqueness makes it idempotent.
6. On restart, SQLite atomic recovery + integrity check + record/context SHA-256 validation precede replay. Corrupt rows remain present and expose FAULT; no skipping/deletion is performed.

Diagnostics: `GET /api/factory/history/status` reports mode, status, queue depth, disk bytes, retries, error, lag and per-run enqueued/persisted sequences. PostgreSQL failure becomes DEGRADED with bounded backoff. Queue/lag saturation becomes BACKPRESSURE and pauses simulation. Local durable append failure becomes FAULT; the rejected event remains in memory and the simulation is stopped. Shutdown reports an uncommitted event as an error rather than claiming durability. A physically unwritable disk cannot guarantee durability of a rejected append; this boundary is explicit and requires operator intervention.

Default demo limits (all configurable, not universal production sizing): 4096 pending records, 64 MiB spool files, retry 0.2–5 s, maximum pending age 300 s, batch 64, graceful flush 8 s. See `config/persistence/development.env.example`. Size for measured event volume and outage tolerance. Context registration also enforces the disk budget. Historical run contexts/checkpoints remain in the local spool; eventual retention/archiving is a future operational policy, and the configured cap prevents unbounded growth.

On shutdown, stop the simulation loop, reject new submissions, flush until deadline, leave unacknowledged records durable, checkpoint and close the writer/DB. PostgreSQL acknowledgements and local durability are distinct. Restart replays history; it does **not** restore an interrupted DES execution from an event-sourced checkpoint. A new runtime gets a new run ID, while old history remains queryable.

## Read interfaces

- `/api/factory/history/runs/{run_id}/events?after=0&limit=1000`: ordered, bounded pagination.
- `/api/factory/site/spatial/site`, `zone?entity_id=...`, `assets_in_zone?entity_id=...`, `nearby_assets?x=...&y=...&z=...&radius=...`, `transport_nodes`, `transport_edges`, `docks`, `staging_areas`.
- Responses identify static revision/hash and coordinate semantics. DB errors return unavailability; they do not manufacture fresh spatial data from a different revision.

## Reasoning provider

`aria/reasoning/providers.py` extracts the previous Ollama payload, prompt, model lookup, 1 MB response bound, JSON parsing and `min(12, timeout)` network timeout. `IndustrialAgent` independently validates intents and change-tool allowlist before invoking the existing service. Proposal resolution remains human-only.

Known deterministic requests remain offline. `AnthropicProvider` is an unavailable boundary only; it makes no requests and returns no simulated successful response. No key is required for ordinary operation, and no alternate cloud model is silently selected.

The old request/intent path is frozen in a test fixture. Normal, invalid, forbidden and unavailable replies are compared with that reference. Actual installed Ollama in this environment contains `qwen3:32b`, while existing configuration selects `qwen2.5:14b`. The real call returns 404 and the preserved unavailable fallback. Successful live reasoning for that configured model has not been demonstrated; no model was downloaded or substituted.

## Future infrastructure boundaries

Redis may become useful for cross-process WebSocket fanout, background jobs or shared caches. It is not required here and must not be the sole factory state store. Multiple API workers currently cannot share one in-memory simulation; introducing fanout alone would not solve ownership.

RAG remains a future retrieval boundary for manuals, SOP and maintenance records. Select a framework/vector store only after one real retrieval workflow and its evidence-quality evaluation exist.
