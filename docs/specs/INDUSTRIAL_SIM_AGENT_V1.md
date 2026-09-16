# Industrial Simulation & Agent V1

## Existing architecture / M1 inspection

- `server/app.py` assembles FastAPI routers before SPA fallback. `/api/sim` is image dataset/train/validation, not DES. `/ws/chat` originally received and discarded chat text.
- `server/ws.py` is the single broadcast choke point. Inspector/training events feed the existing `FactoryLine`; `twin.line_loop` publishes measured line and GPU telemetry.
- `TwinState` owns inspector run/lane epoch/agent state and safe restart. It is **not** a material-flow state engine. New factory state is an additive domain alongside this existing twin, published through the same channel. Existing live inspection counters must never consume simulated inspection results.
- `aria/simulation` synthesizes image datasets and performs FAT validation. Existing `AsyncPipeline`, detector registry, `PatchCoreDetector`, and user-added `CCIFPSDetector` provide inspection interfaces.
- `AppShell` uses MUI slots, R3F `QCLine`, reusable conveyor prefabs, `signalStore` and raw `signalFanout`. `flowEngine` animates live inspector results, not generic production rules. Add a Factory workspace accessible from the existing shell; keep original QC view available.
- `autonomous_agent`, harness loop and MCP client exist, with local Ollama routing and broad filesystem/system/vision tools. They are not an isolated factory-tool agent and have external side effects. Use a bounded factory-only agent with local routing from `mcp_config.json` (`chat_ko`, fallback model); no external API required. Reuse existing detector adapters and WS fanout, not unrestricted system tools.
- Existing data is symlinked to CCIFPS-AutoML. Existing user changes in detector/backend/router/HMI files must be preserved. `AGENTS.md` remains unchanged.

## Decisions

Custom heap-based DES gives reproducible same-time ordering, explicit one-event step, pause/reset, and deterministic failure interruptions without a new dependency. Wall time only selects how far to advance. Mock inspection uses a per-resource seeded RNG and is explicitly labeled; asset failures become SKIPPED and route to HOLD.

Finite capacity includes processing and blocked finished slots. Buffers use FIFO/LIFO; downstream refusal retains material upstream. Sources backpressure without creating unbounded external demand. MTBF samples exponential uptime, MTTR is fixed; availability derives an MTBF only when none is supplied. Setup is per admitted part. Maintenance prevents admission. V1 accepts DAGs; disconnected nodes are allowed during editing with validation warnings. IDs/edges/capacities/numeric bounds are validated before proposals.

KPI definitions: throughput = exits / simulation hours; WIP = admitted minus exited; lead time = mean born-to-exit; cycle time = mean inter-exit interval. Resource occupancy and processing-slot utilization are time integrals. Buffer waiting = mean completed residence; average queue includes current material. State time includes idle/starved/blocked/down/setup/maintenance. OEE is minimum machine A×P×Q: A excludes down/maintenance, P uses actual completions×ideal process time per available slot time (capped at 1), Q uses exit OK fraction. This is a V1 line proxy, not a certified production OEE measure. Bottleneck ranking uses busy time, upstream occupancy/wait, blocking/starvation; throughput sensitivity comes from parameter-sweep comparisons, never guessed by the LLM.

## Contracts

`/api/factory`: model GET/PUT, components GET/POST/PATCH/DELETE, connect POST; run/pause/resume/step/reset POST; snapshot/metrics/bottlenecks GET; scenarios GET/POST, scenarios/{id}/run POST; experiments POST; tools GET and tools/{name} POST; proposals/{id}/apply|reject POST; agent POST.

All model writes produce a before/after proposal with a model revision. Only the explicit human endpoint applies it. Applying resets simulation, atomically saves the model and scenarios, and rejects stale/double approvals. Undo produces another approval proposal. Agent never calls the approval endpoint. Persistence uses outputs/factory/factory.json; process restart is paused. Single server worker only.

WS `/ws/chat`: additive `simulation_state` snapshots contain bounded events/moves, metrics and revision; `agent_plan/action/observation/result` and `experiment_progress`. Existing inspector/line/telemetry contracts unchanged. Frontend uses raw fanout on the existing single socket. Optional incoming `{type: factory_chat, message}` routes to the same agent handler.

Experiments clone the model with the same seed and horizon; max 12 candidates, max 3600 simulated seconds, bounded event count. Actual detector modes stay actual; they are never silently replaced by mocks. Agent core commands work offline; local model is only needed for flexible wording and topology planning. Local plans pass through model validation and mandatory approval. All numerical responses are formatted directly from tool output.

## Acceptance

Backend: reproducibility, conservation, capacity, blocking, starvation, failures/resumption, setup, routing, exact simple-line KPI, controls, input validation, persistence, stale approval, refusal of agent apply, real-detector adapter contract, measured >10% demo improvement.
Frontend: production build, browser render, run/pause/step/reset, selection/edit/apply/reject, save/load, chat and experiment comparison, network/console review.

## Final validation / implementation notes

See ../INDUSTRIAL_V1_REPORT.md and ../CODEX_PROGRESS.md. 53 tests pass. Actual CCIFPS CPU inference and actual browser XZ drag/JSON roundtrip verified. FastMCP adapter uses the same HTTP tool boundary; no approval access. `ARIA_FACTORY_STATE_DIR` supports test state isolation. Agent sweep wall-time budget15s, each standalone scenario budget10s, checked between events. A native detector call already in progress cannot be forcibly interrupted. Analysis snapshot ranking exposes measured sweep sensitivity after a sweep; reset model changes discard it.
