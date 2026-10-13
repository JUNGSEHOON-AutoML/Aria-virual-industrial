# O0/O1 CPU tools

O0 inspects the host. O1 exports the current static web prefabs. Neither tool
installs or launches Kit, creates a CUDA context, controls Live Ops, or touches
the main experiment. Web milestone order remains unchanged.

Run from the repository root with the existing `aria` Python environment active.
The browser capture reuses its existing httpx/websockets and installed Chrome.

```bash
python -m tools.omniverse_preflight
# Exit 2 means environment conditions failed; see the generated admin request.

# One-time, explicitly approved local-only installation (already done):
python -m venv venv/omniverse
venv/omniverse/bin/python -m pip install --no-cache-dir --only-binary=:all: -r tools/omniverse/requirements.txt

# Existing CPU dashboard must be reachable (default localhost:5278).
# If it is not running, use ./scripts/demo.sh in a separate terminal.
bash tools/omniverse/run_o1.sh

# Read-only validation of an existing export:
venv/omniverse/bin/python -m tools.omniverse.usdchecker exports/usd/cnotta_campus.usda
```

Set `CNOTTA_CAPTURE_PYTHON` to an existing Python with the capture dependencies,
or `CNOTTA_WEB_URL` to the existing dashboard's original local server URL.
Do not use a transient Codex forwarding URL for the capture tool.

Outputs:

- `exports/usd/cnotta_campus.usda`: metres, Y-up; `/World/Campus/Hall_*`,
  `RobotCell`, `Yard`, `Landscape`; each hall contains the same three `Lane_*`
  groups, equipment and extruded SVG roof branding as the web.
- `exports/usd/assets/*.usda`: native-size CAD design envelopes converted from
  existing GLBs whose STEP/GLB hashes and dimensions match `dims.json`.
- `exports/usd/manifest.json`: source hashes, asset provenance, representation
  scope and web bounds. Source changes require a new capture; stale input fails.
- `docs/autopilot/gates/o0.json`, `o1.json`: recorded milestone gates.
- `docs/autopilot/local/usd-*.json`, `*.png`: ignored local browser evidence.

The default `web` representation preserves the exact shared prefab geometry.
Each conveyor/booth/diverter has a `representation=cad_envelope` variant with a
relative USD asset reference. Raw STEP is not a USD-readable reference without
a file-format plugin. This tool uses the existing hash-verified STEP-derived
GLB, already in metres, rather than pretending that USD can open STEP directly.
The variant preserves native CAD dimensions and places the prototype at its
web component's XZ center on the floor; this placement is **assumed** and is
not a complete mechanical assembly. The ≤1 cm web/USD gate covers default
`web` geometry. All CAD variants are additionally validated and their native
dimensions checked. CAD source files are unchanged.

M0609 stays a clearly labelled static placeholder: no verified official
URDF-to-USD converter is installed. HTML signs/panels, lights, dynamic parts,
process clocks and robot animation are outside this static export. Shared
SVG meshes and UsdPreviewSurface token colours (sRGB converted to linear RGB)
are included. O2 is the later event-driven animation/streaming milestone.

`usd-core 26.8` does not ship the upstream `usdchecker` executable. The project
`usdchecker.py` CLI uses all 28 official OpenUSD `UsdValidation` validators,
not a replacement set of homegrown compliance rules. It checks the default
stage and every individual CAD variant, rejects missing references and any
reported issue, and does not save variant selections. The geometric gate then
independently reopens the stage and measures transformed mesh vertices, every
site/lane/component bound, origins/yaw, logo depth, material values and counts.
An actual Replay browser scene is also compared with the isolated static scene.

Only CPU SwiftShader was used. This does not establish Omniverse rendering
quality, real GPU FPS, robot kinematic accuracy or O2 readiness.

Package provenance: `environment.json`. Official documentation:
[OpenUSD tools](https://openusd.org/release/toolset.html),
[usd-core distribution](https://pypi.org/project/usd-core/),
[Kit requirements](https://docs.omniverse.nvidia.com/dev-guide/latest/common/technical-requirements.html).
