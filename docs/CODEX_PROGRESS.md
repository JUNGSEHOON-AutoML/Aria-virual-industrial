# ARIA Industrial V1 progress

## Final Goal
Existing ARIA + editable 3D factory + deterministic DES + measured KPIs + local industrial agent + approved what-if changes.

## Architecture Decisions
See `specs/INDUSTRIAL_SIM_AGENT_V1.md`. Additive factory domain, heap queue DES, shared WS fanout, actual detector adapter, deterministic offline tools and optional local language planner, revision-bound approvals. Reuse FastMCP through the API so its subprocess never creates a second simulation owner.

## Current Phase
M13 completed for the implemented V1 scope, 2026-09-17. Final report: `INDUSTRIAL_V1_REPORT.md`.

## Completed
- M1: inspected architecture, existing contracts, local routing, inspection and user diffs; wrote specification.
- M2–M3: validated factory graph and deterministic finite-capacity DES with reproducible faults, setup, blocking, starvation, FIFO/LIFO and routing.
- M4–M5: Factory REST/WS API, default seed-42 factory, independent simulation clock.
- M6–M7: model-driven R3F renderer, existing conveyor prefab, palette, selection, actual XZ gizmo drag, property/rotation edit, connections, save/load JSON.
- M8: event-derived metrics and deterministic bottleneck ranking.
- M9–M10: bounded industrial tool agent, Korean/English baseline commands, optional configured local Ollama planner, revision-bound human approval and undo; FastMCP adapter.
- M11: saved scenarios, comparisons, measured parameter sweeps.
- M12: Chrome/CDP E2E and visual review, 3D camera adjusted after observation; actual drag fixed and verified.
- M13: backend regression, production build, CCIFPS CPU integration proof, documentation and reproducible browser harness.

## In Progress
None for this implementation pass. Local-model availability limitations are recorded below.

## Remaining
V2 recommendations: rework cycles, AGV/robot/worker scheduling, multi-seed confidence intervals, separate inference worker/process cancellation, secure multi-user deployment. Broader generative natural-language planning requires the configured local model to be installed and available.

## Tests Passed
- Existing 30 backend tests + 23 new tests: `python -m pytest tests/ -q -p no:cacheprovider` → **53 passed**, 3.25s (conda aria; OMP/BLAS threads=4).
- `npm run build` → success, Vite 5.4.21, 2211 modules.
- Chrome: Run/Pause/Resume/Step/Reset, select/edit/reject, chat input, improvement/apply, palette add, actual XZ drag (position [0,0,5] → [1.1,0,5]), property move, connect/delete/apply, save/load JSON, saved scenario comparison. No JS exceptions or HTTP errors; 165 WS frames.
- Measured seed42/600s baseline **1140/h**; machine capacity2 **1770/h (+55.263%)**; process time2.4/capacity1 **1428/h (+25.263%)**.
- Actual CCIFPS CPU inspection: score **0.2812235355**, threshold **0.3996464610**, verdict OK; GOOD-SINK=1. Model and inference reused, 4.81s. No training or GPU allocation.
- MCP adapter read actual running API metrics; agent/MCP apply without human approval rejected.
- `git diff --check` clean; AGENTS.md unchanged.

## Tests Failed
- Initial system Python has no pytest; corrected by using existing conda aria.
- Initial sandbox baseline stalled in existing API tests; stopped only that owned process. Same complete suite passed outside sandbox.
- `npm run lint` cannot execute: repository has no ESLint configuration. No tests were deleted or skipped.
- Browser harness initially chose an extension target and later had a result-serialization bug; corrected target selection and serialization. Final complete harness exited 0.

## Known Issues
Configured `qwen2.5:14b`/`llama3.1` are absent from local Ollama (only qwen3:32b reported). Core analysis, optimization and supported edits work offline; unconstrained wording may need local model setup. No external OpenAI dependency was added and the previously created key remains in CCIFPS-AutoML.
V1 model is a DAG, single process owner, max100 components/2000 slots; experiment bounds apply. OEE is the documented V1 line proxy. In-flight native inference cannot be forcibly interrupted by the agent wall-time check. Combined mode uses the existing optional YOLO gate without configuring YOLO weights. Bundle is ~2.83MB (gzip~883KB); existing FastAPI/pynvml deprecation warnings remain.

## Next Action
Open `http://localhost:8230`, run the default factory, ask “현재 병목을 분석해줘” or “처리량 10% 개선해줘”, and review the proposal. The final validation leaves the restored demo paused with a short live run visible. Standard future launch uses frontend/dist and existing uvicorn entrypoint.


## Visual workspace revision — 2026-09-17

User feedback: the initial symbolic blocks did not resemble a professional industrial process simulator. Reference screenshots were treated as visual references, not executable instructions.

Implemented model-driven CNC enclosures with table/spindle/control pendant, jointed orange robot tenders, safety fences, transparent inspection enclosures and camera gantries, storage pallets/totes, rack buffers, rotary diverters and physical conveyor bridges. Added concrete floor joints, workshop walls/windows and marked walkways. Existing machine/inspection processing phases drive robot/spindle display poses; pause does not advance these poses. Product positioning now respects component rotation. No change to process topology or KPI calculations.

Added Factory view, Top, Cell close-up, Labels and Flow paths controls. Cell close-up isolates selected equipment after browser review found adjacent equipment obscured it. Reduced dashboard prominence and enlarged the industrial viewport. Existing user-added equipment uses the same component renderer.

Validation: production build passes (2212 modules). Actual Chrome/CDP checked overview, CNC/inspection close-ups, top view, selection, Run/Pause/Step; 0 JS exceptions and 0 HTTP errors. Final close-up isolation rechecked visually. Evidence: outputs/industrial_visual_revision/ and docs/images/industrial_process_*.png.

Limitations: parametric equipment geometry and process-driven joint poses, not imported OEM CAD models, robot inverse kinematics, reachability/collision validation or generated robot programs. Conveyor bridges visualize model connections; they are not additional DES resources. These distinctions matter before claiming commercial robotics simulation equivalence.
