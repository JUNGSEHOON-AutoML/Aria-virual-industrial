"""Factory tools over existing ARIA API. No direct state or approval access.

Run with the same interpreter as the other ARIA FastMCP servers. The API is
single owner; do not instantiate a second DES in the MCP subprocess.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path
from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from aria.simulation.des.service import TOOL_NAMES

mcp = FastMCP('aria-factory')
ALLOWED = (set(TOOL_NAMES) | {'get_patrol_report'}) - {'apply_factory_change', 'reject_factory_change'}

@mcp.tool()
def factory_tool(name: str, arguments: dict | None = None) -> dict:
    """Execute an ARIA factory query/control/experiment or propose a change.

    Names: get_factory_model, get_factory_state, get_component(id), list_components,
    create_component(component), update_component(id, changes), delete_component(id),
    connect_components(source,target,condition), validate_factory_model(model),
    start_simulation(speed), pause_simulation, resume_simulation, step_simulation,
    reset_simulation, get_simulation_metrics, get_bottleneck_analysis,
    create_scenario(name,model), list_scenarios, run_scenario(id,duration),
    compare_scenarios(ids,duration), run_parameter_sweep(component,parameters,duration),
    propose_factory_change(model,reason), undo_factory_change.
    Every model change returns a proposal for human approval in the HMI.
    """
    if name not in ALLOWED:
        raise ValueError('Unknown tool or human-only approval action')
    base = os.environ.get('ARIA_FACTORY_API', 'http://127.0.0.1:8200').rstrip('/')
    req = urllib.request.Request(base + '/api/factory/tools/' + name,
        data=json.dumps(arguments or {}).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=35) as response:
        return {'result': json.loads(response.read(20 * 1024 * 1024))}

if __name__ == '__main__':
    mcp.run()
