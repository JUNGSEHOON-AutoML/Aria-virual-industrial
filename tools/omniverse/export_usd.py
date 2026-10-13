"""Convert the shared web scene snapshot to portable OpenUSD on CPU only."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATHS = json.loads((Path(__file__).parent/'sources.json').read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def triples(values):
    return [Gf.Vec3f(*values[i:i+3]) for i in range(0, len(values), 3)]


def matrix(values):
    # Three column-major flattened elements = Gf row-vector matrix rows.
    return Gf.Matrix4d(*values)


def new_stage(path, root_name='World'):
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = Usd.Stage.CreateNew(str(path)) if not path.exists() else Usd.Stage.Open(str(path))
    stage.GetRootLayer().Clear()  # Only this tool's generated USD output.
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, 1)
    root = UsdGeom.Xform.Define(stage, '/'+root_name)
    stage.SetDefaultPrim(root.GetPrim())
    return stage


def save(stage, path):
    stage.GetRootLayer().Save()
    # OpenUSD emits a final empty line; normalize only our generated text files.
    path.write_text(path.read_text().rstrip()+'\n')


def material(stage, path, values):
    mat = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, path+'/PreviewSurface')
    shader.CreateIdAttr('UsdPreviewSurface')
    for key, value, typ in [('diffuseColor', Gf.Vec3f(*values['linear']), Sdf.ValueTypeNames.Color3f),
                            ('emissiveColor', Gf.Vec3f(*values['emissive']), Sdf.ValueTypeNames.Color3f),
                            ('roughness', values['roughness'], Sdf.ValueTypeNames.Float),
                            ('metallic', values['metallic'], Sdf.ValueTypeNames.Float),
                            ('opacity', values['opacity'], Sdf.ValueTypeNames.Float)]:
        shader.CreateInput(key, typ).Set(value)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), 'surface')
    mat.GetPrim().SetCustomDataByKey('source_srgb', values['srgb'])
    return mat


def mesh(stage, path, geometry, mat):
    obj = UsdGeom.Mesh.Define(stage, path)
    points = triples(geometry['points'])
    indices = geometry['indices']
    if len(indices) % 3 or any(i < 0 or i >= len(points) for i in indices):
        raise ValueError('Invalid triangle indices at '+path)
    obj.CreatePointsAttr(points)
    obj.CreateFaceVertexCountsAttr([3] * (len(indices)//3))
    obj.CreateFaceVertexIndicesAttr(indices)
    obj.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    obj.CreateDoubleSidedAttr(True)
    obj.CreateExtentAttr(UsdGeom.PointBased.ComputeExtent(points))
    if geometry.get('normals'):
        obj.CreateNormalsAttr(triples(geometry['normals']))
        obj.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    UsdShade.MaterialBindingAPI.Apply(obj.GetPrim()).Bind(mat)
    return obj


def decode_cad_glb(path):
    """Read the repository's simple FreeCAD GLB envelope; fail on other formats.

    It already stores metres, despite dims.json describing its bbox in mm.
    Do not silently apply another /1000 or ignore transforms/sparse accessors.
    """
    raw = path.read_bytes()
    magic, version, size = struct.unpack_from('<III', raw)
    if magic != 0x46546C67 or version != 2 or size != len(raw):
        raise ValueError('Invalid GLB header')
    offset, chunks = 12, {}
    while offset < len(raw):
        length, kind = struct.unpack_from('<II', raw, offset)
        chunks[kind] = raw[offset+8:offset+8+length]
        offset += 8 + length
    doc, binary = json.loads(chunks[0x4E4F534A]), chunks[0x004E4942]
    if doc['nodes'] != [{'mesh': 0}] or len(doc['meshes']) != 1 or len(doc['meshes'][0]['primitives']) != 1:
        raise ValueError('Unsupported CAD GLB graph; explicit converter required')
    prim = doc['meshes'][0]['primitives'][0]
    if prim.get('mode', 4) != 4:
        raise ValueError('Only triangle CAD envelopes supported')
    def accessor(index):
        a = doc['accessors'][index]
        if 'sparse' in a:
            raise ValueError('Sparse accessor unsupported')
        view = doc['bufferViews'][a['bufferView']]
        if view.get('buffer', 0) != 0:
            raise ValueError('External GLB buffer unsupported')
        typ = {5126: 'f', 5125: 'I', 5123: 'H'}[a['componentType']]
        count = {'VEC3': 3, 'SCALAR': 1}[a['type']]
        fmt = '<'+typ*count
        stride = view.get('byteStride', struct.calcsize(fmt))
        start = view.get('byteOffset', 0) + a.get('byteOffset', 0)
        return [x for i in range(a['count']) for x in struct.unpack_from(fmt, binary, start+i*stride)]
    return {'points': accessor(prim['attributes']['POSITION']), 'indices': accessor(prim['indices'])}


def cad_assets(output, tokens):
    manifests = {}
    for part in ('conveyor', 'inspection_booth', 'diverter'):
        source = ROOT/'assets/cad'/part/'dt_v1'
        dims = json.loads((source/'dims.json').read_text())
        hashes = {name: digest(source/name) for name in ('model.step', 'model.glb')}
        if any(sha != dims['files'][name] for name, sha in hashes.items()):
            raise ValueError('CAD provenance hash mismatch: '+part)
        geometry = decode_cad_glb(source/'model.glb')
        points = triples(geometry['points'])
        lo, hi = UsdGeom.PointBased.ComputeExtent(points)
        sizes = [float(hi[i]-lo[i]) for i in range(3)]
        expected = [dims[k]/1000 for k in ('length_mm', 'height_mm', 'width_mm')]
        error = max(abs(a-b) for a,b in zip(sizes, expected))
        if error > .00001:
            raise ValueError(f'CAD units/dimensions mismatch {part}: {sizes} vs {expected}')
        # Native dimensions; center XZ at zero, rest on Y=0, no scaling to web.
        for i in range(0, len(geometry['points']), 3):
            geometry['points'][i] -= float((lo[0]+hi[0])/2)
            geometry['points'][i+1] -= float(lo[1])
            geometry['points'][i+2] -= float((lo[2]+hi[2])/2)
        path = output.parent/'assets'/(part+'.usda')
        stage = new_stage(path, 'Asset')
        rgb = [int(tokens['equip-frame'].lstrip('#')[i:i+2], 16)/255 for i in (0,2,4)]
        linear = [c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in rgb]
        mat = material(stage, '/Asset/Materials/Frame', dict(linear=linear, srgb=tokens['equip-frame'], emissive=[c*.38 for c in linear], roughness=.85, metallic=0., opacity=1.))
        mesh(stage, '/Asset/Geometry', geometry, mat)
        stage.GetDefaultPrim().SetCustomDataByKey('cad_provenance', json.dumps({'source': str(source.relative_to(ROOT)), 'files': hashes, 'dims_sha256': digest(source/'dims.json'), 'meaning': dims['meaning']}))
        save(stage, path)
        manifests[part] = {'reference': 'assets/'+path.name, 'source_step': str((source/'model.step').relative_to(ROOT)), 'sha256': hashes, 'dims_sha256': digest(source/'dims.json'), 'dimensions_m': sizes, 'dimension_error_m': error}
    return manifests


def export(snapshot, output):
    data = json.loads(snapshot.read_text())
    if data.get('source_hashes') != {p: digest(ROOT/p) for p in SOURCE_PATHS}:
        raise ValueError('Stale prefab/token/SVG capture; recapture before exporting')
    layout = json.loads((ROOT/SOURCE_PATHS[0]).read_text())
    if data['layout'] != layout or data['units'] != 'm' or data['upAxis'] != 'Y':
        raise ValueError('Stale layout or unsupported coordinate contract')
    if data.get('errors') or data.get('http_errors') or data.get('api_requests'):
        raise ValueError('Unclean static capture')
    tokens = json.loads((ROOT/'frontend/src/brand/cnotta.tokens.json').read_text())
    assets = cad_assets(output, tokens)
    stage = new_stage(output)
    UsdGeom.Xform.Define(stage, '/World/Campus')
    mats = [material(stage, f'/World/Materials/M_{i}', value) for i, value in enumerate(data['materials'])]
    world_matrices = {'/World/Campus': Gf.Matrix4d(1)}
    for node in data['nodes']:
        path = node['path']
        parent = str(Sdf.Path(path).GetParentPath())
        world = matrix(node['matrix'])
        local = world * world_matrices[parent].GetInverse()
        if node['kind'] == 'group':
            obj = UsdGeom.Xform.Define(stage, path)
            obj.GetPrim().SetCustomDataByKey('web_metadata', json.dumps(node['metadata'], ensure_ascii=False))
            if node['metadata'].get('siteId'):
                obj.GetPrim().SetCustomDataByKey('site_id', node['metadata']['siteId'])
        else:
            obj = mesh(stage, path, data['geometries'][node['geometry']], mats[node['material']])
        UsdGeom.Xformable(obj).AddTransformOp().Set(local)
        world_matrices[path] = world

    # Preserve the exact web representation by default. CAD is an explicit
    # native-size design-envelope variant, not a silently stretched replacement.
    cad_variants = []
    for node in data['nodes']:
        part = node.get('metadata', {}).get('cadPart')
        if not part:
            continue
        prim = stage.GetPrimAtPath(node['path'])
        children = list(prim.GetChildren())
        box = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_]).ComputeLocalBound(prim).ComputeAlignedRange()
        center = (box.GetMin()+box.GetMax())/2
        variants = prim.GetVariantSets().AddVariantSet('representation')
        variants.AddVariant('web')
        variants.AddVariant('cad_envelope')
        variants.SetVariantSelection('cad_envelope')
        with variants.GetVariantEditContext():
            for child in children:
                stage.OverridePrim(child.GetPath()).SetActive(False)
            cad = UsdGeom.Xform.Define(stage, node['path']+'/CAD')
            cad.GetPrim().GetReferences().AddReference(assets[part]['reference'], '/Asset')
            cad.AddTranslateOp().Set(Gf.Vec3d(center[0], 0, center[2]))
            cad.GetPrim().SetCustomDataByKey('assumed_placement', 'native-size envelope at shared web component XZ center, floor Y=0; not mechanical validation')
        variants.SetVariantSelection('web')
        cad_variants.append(node['path'])
    manifest = {'schema': 1, 'scope': data['scope'], 'sources': {p: digest(ROOT/p) for p in SOURCE_PATHS},
                'snapshot_sha256': digest(snapshot), 'snapshot_bounds': data['bounds'], 'world_bounds': data['worldBounds'],
                'cad_assets': assets, 'cad_variants': cad_variants,
                'geometry_count': len(data['geometries']), 'mesh_count': sum(n['kind']=='mesh' for n in data['nodes']),
                'material_count': len(mats), 'renderer': data['renderer'],
                'm0609': 'placeholder only; no verified URDF-to-USD conversion tool used',
                'representation': 'default web; cad_envelope variant references hash-verified STEP-derived GLB converted to USD; native dimensions, not production assembly'}
    stage.GetRootLayer().customLayerData = {'generator': 'CNOTTA shared Three.js prefabs -> usd-core CPU', 'manifest': 'manifest.json', 'sourceScope': data['scope']}
    save(stage, output)
    manifest['usd_sha256'] = digest(output)
    (output.parent/'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+'\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=ROOT/'docs/autopilot/local/usd-web.json')
    parser.add_argument('--output', type=Path, default=ROOT/'exports/usd/cnotta_campus.usda')
    args = parser.parse_args()
    result = export(args.snapshot, args.output)
    print(json.dumps({k:result[k] for k in ('mesh_count','material_count','m0609')}, ensure_ascii=False))
