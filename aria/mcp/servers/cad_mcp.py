"""FreeCAD tools for ARIA. Geometry changes return human-review proposals."""
import json,os,urllib.request
from mcp.server.fastmcp import FastMCP
mcp=FastMCP('aria-freecad')
def request(path,body=None):
 base=os.environ.get('ARIA_FACTORY_API','http://127.0.0.1:8230').rstrip('/')
 req=urllib.request.Request(base+'/api/factory/cad'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=70) as r:return json.load(r)
@mcp.tool()
def get_cad_status()->dict:
 """Check whether the FreeCAD runtime is available."""
 return request('/status')
@mcp.tool()
def build_cnc_cad(component:str='MACHINE-01',width_mm:float=2500,depth_mm:float=1900,height_mm:float=2600)->dict:
 """Generate real CNC CAD, validate solids/static overlap, export FCStd/STEP/mesh.
 Returns a proposal to attach the asset; approve it in ARIA. Does not change
 processing time or verify robot motion. Dimensions are millimetres.
 """
 return request('/build',dict(component=component,parameters=dict(width_mm=width_mm,depth_mm=depth_mm,height_mm=height_mm)))
@mcp.tool()
def get_cad_asset(asset_id:str)->dict:
 """Read an existing CAD validation report and artifact URLs."""
 if len(asset_id)!=24 or any(c not in '0123456789abcdef' for c in asset_id):raise ValueError('Invalid asset ID')
 return request('/assets/'+asset_id)
if __name__=='__main__':mcp.run()
