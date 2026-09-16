# Industrial visual workspace


## Visual workspace revision — 2026-09-17

User feedback: the initial symbolic blocks did not resemble a professional industrial process simulator. Reference screenshots were treated as visual references, not executable instructions.

Implemented model-driven CNC enclosures with table/spindle/control pendant, jointed orange robot tenders, safety fences, transparent inspection enclosures and camera gantries, storage pallets/totes, rack buffers, rotary diverters and physical conveyor bridges. Added concrete floor joints, workshop walls/windows and marked walkways. Existing machine/inspection processing phases drive robot/spindle display poses; pause does not advance these poses. Product positioning now respects component rotation. No change to process topology or KPI calculations.

Added Factory view, Top, Cell close-up, Labels and Flow paths controls. Cell close-up isolates selected equipment after browser review found adjacent equipment obscured it. Reduced dashboard prominence and enlarged the industrial viewport. Existing user-added equipment uses the same component renderer.

Validation: production build passes (2212 modules). Actual Chrome/CDP checked overview, CNC/inspection close-ups, top view, selection, Run/Pause/Step; 0 JS exceptions and 0 HTTP errors. Final close-up isolation rechecked visually. Evidence: outputs/industrial_visual_revision/ and docs/images/industrial_process_*.png.

Limitations: parametric equipment geometry and process-driven joint poses, not imported OEM CAD models, robot inverse kinematics, reachability/collision validation or generated robot programs. Conveyor bridges visualize model connections; they are not additional DES resources. These distinctions matter before claiming commercial robotics simulation equivalence.
