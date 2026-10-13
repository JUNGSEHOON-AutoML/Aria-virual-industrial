"""O1 gate: independently reopen USD and compare it to the actual web capture."""
import argparse
import json
import math
from pathlib import Path
from pxr import Gf, Usd, UsdGeom, UsdShade
from tools.omniverse.export_usd import ROOT, SOURCE_PATHS, digest
from tools.omniverse.usdchecker import check


def error(a, b):
    return max(abs(x-y) for aa, bb in zip(a,b) for x,y in zip(aa,bb))


def validate(usd, snapshot, dashboard):
    data = json.loads(snapshot.read_text())
    web = json.loads(dashboard.read_text())
    manifest = json.loads((usd.parent/'manifest.json').read_text())
    layout = json.loads((ROOT/'frontend/src/campus/campus.layout.json').read_text())
    stage = Usd.Stage.Open(str(usd))
    cache = UsdGeom.XformCache()
    expected_bounds = data['bounds']
    measured = {path:Gf.Range3d() for path in expected_bounds}
    world = Gf.Range3d()
    meshes = [p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]
    for prim in meshes:
        transform = cache.GetLocalToWorldTransform(prim)
        box = Gf.Range3d()
        for point in UsdGeom.Mesh(prim).GetPointsAttr().Get():
            box.UnionWith(transform.Transform(Gf.Vec3d(point)))
        world.UnionWith(box)
        for parent in measured:
            if str(prim.GetPath()).startswith(parent+'/'):
                measured[parent].UnionWith(box)
    def bounds(box):
        return [list(box.GetMin()),list(box.GetMax())]
    bbox_errors = {path:error(expected_bounds[path],bounds(box)) for path,box in measured.items()}
    bbox_errors['/World/Campus'] = error(data['worldBounds'], bounds(world))
    dashboard_errors = {path:error(box,web['bounds'][path]) for path,box in expected_bounds.items()}
    sites, lanes = [], []
    booth = json.loads((ROOT/'assets/cad/inspection_booth/dt_v1/dims.json').read_text())
    for site in layout['sites']:
        name = 'Hall_'+site['class'] if site['kind']=='inspection_hall' else 'RobotCell' if site['kind']=='robot_cell' else 'Yard'
        prim = stage.GetPrimAtPath('/World/Campus/'+name)
        transform = cache.GetLocalToWorldTransform(prim)
        origin = list(transform.ExtractTranslation())
        expected = [site['origin'][0],0,site['origin'][1]]
        forward = list(transform.TransformDir(Gf.Vec3d(0,0,1)))
        expected_forward = [math.sin(site['rotation']),0,math.cos(site['rotation'])]
        sites.append(dict(id=site['id'],origin=origin,expected=expected,
                          error_m=max(abs(a-b) for a,b in zip(origin,expected)),
                          yaw_vector_error=max(abs(a-b) for a,b in zip(forward,expected_forward))))
        for i,model in enumerate(site.get('lanes',[])):
            lane = stage.GetPrimAtPath(str(prim.GetPath())+'/Lane_'+model)
            local = UsdGeom.Xformable(lane).GetLocalTransformation().ExtractTranslation()
            expected_local = [0,0,(i-(len(site['lanes'])-1)/2)*(booth['width_mm']/1000+layout['design']['lane_gap'])]
            lanes.append(dict(site=site['id'],model=model,local_position=list(local),expected=expected_local,
                              error_m=max(abs(a-b) for a,b in zip(local,expected_local)),
                              components=[c.GetName() for c in lane.GetChildren()]))
    usd_sites = [p for p in stage.Traverse() if p.GetCustomDataByKey('site_id')]
    usd_lanes = [p for p in stage.Traverse() if p.GetName().startswith('Lane_')]
    logos = [p for p in meshes if p.GetName().startswith('wordmark_hall_')]
    marks = [p for p in meshes if p.GetName().startswith('roof_mark')]
    material_errors = []
    for i,mat in enumerate(data['materials']):
        shader = UsdShade.Shader.Get(stage,f'/World/Materials/M_{i}/PreviewSurface')
        actual = list(shader.GetInput('diffuseColor').Get())
        material_errors.append(max(abs(a-b) for a,b in zip(actual,mat['linear'])))
    validation = check(usd)
    assets = {name:check(usd.parent/entry['reference']) for name,entry in manifest['cad_assets'].items()}
    roof_depths = [min(UsdGeom.Mesh(p).GetExtentAttr().Get()[1][i]-UsdGeom.Mesh(p).GetExtentAttr().Get()[0][i] for i in range(3)) for p in logos+marks]
    current_sources = {p:digest(ROOT/p) for p in SOURCE_PATHS}
    checks = {
        'official_usd_validation': validation['pass'] and all(v['pass'] for v in assets.values()),
        'units_m_y_up': UsdGeom.GetStageMetersPerUnit(stage)==1 and UsdGeom.GetStageUpAxis(stage)=='Y',
        'sites_and_lanes': len(usd_sites)==len(layout['sites'])==5 and len(usd_lanes)==len(lanes)==9,
        'layout_positions_and_yaw': all(s['error_m']<1e-8 and s['yaw_vector_error']<1e-8 for s in sites) and all(l['error_m']<1e-8 for l in lanes),
        'lane_components': all(set(l['components'])=={'MainConveyor','Booth','Diverter','Reinspection'} for l in lanes),
        'web_usd_bbox_le_1cm': max(bbox_errors.values())<=.01,
        'actual_dashboard_static_bbox_le_1cm': max(dashboard_errors.values())<=.01,
        'mesh_count': len(meshes)==manifest['mesh_count']==sum(n['kind']=='mesh' for n in data['nodes']),
        'extruded_roof_logos': len(logos)==3 and len(marks)==3 and min(roof_depths)>0,
        'token_colors': max(material_errors)<1e-7,
        'cad_references': len(manifest['cad_assets'])==3 and len(manifest['cad_variants'])==27,
        'fresh_sources': current_sources==manifest['sources']==data['source_hashes']==web['source_hashes'],
        'fresh_usd': digest(usd)==manifest['usd_sha256'],
        'cpu_only_capture': 'SwiftShader' in data['renderer'] and 'SwiftShader' in web['renderer'],
        'browser_clean': not(data['errors'] or data['http_errors'] or data['api_requests'] or web['errors'] or web['http_errors']),
        'web_draw_calls': web['web_audit']['draw_calls']<300,
    }
    return {'milestone':'O1','pass':all(checks.values()),'checks':checks,'sites':sites,'lanes':lanes,
            'bbox_max_error_m':max(bbox_errors.values()),'bbox_errors_m':bbox_errors,
            'dashboard_bbox_max_error_m':max(dashboard_errors.values()),
            'material_max_linear_error':max(material_errors),'mesh_count':len(meshes),'roof_logo_mesh_count':len(logos)+len(marks),
            'cad_dimension_errors_m':{k:v['dimension_error_m'] for k,v in manifest['cad_assets'].items()},
            'usdchecker':validation,'asset_validation':{k:v['pass'] for k,v in assets.items()},
            'web_draw_calls':web['web_audit']['draw_calls'],'web_triangles':web['web_audit']['triangles'],
            'scope':manifest['scope'],'renderer':data['renderer'],'gpu_verified':False,
            'limitations':['O2 blocked by O0; Kit not installed or launched','M0609 placeholder only','CAD variant is a native-size assumed design envelope; default is exact web representation','DOM labels/panels and dynamic entities are not static USD geometry']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--usd',type=Path,default=ROOT/'exports/usd/cnotta_campus.usda')
    parser.add_argument('--snapshot',type=Path,default=ROOT/'docs/autopilot/local/usd-web.json')
    parser.add_argument('--dashboard',type=Path,default=ROOT/'docs/autopilot/local/usd-dashboard.json')
    parser.add_argument('--output',type=Path,default=ROOT/'docs/autopilot/gates/o1.json')
    args=parser.parse_args()
    report=validate(args.usd,args.snapshot,args.dashboard)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k in ('pass','checks','bbox_max_error_m','dashboard_bbox_max_error_m','web_draw_calls')},indent=2))
    raise SystemExit(0 if report['pass'] else 1)
