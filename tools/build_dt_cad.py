"""Run inside existing FreeCAD runtime. Parametric design dimensions, not measurements."""
import json,struct,hashlib,os
from pathlib import Path
import FreeCAD as App
import Part
ROOT=Path(os.environ['ARIA_DT_ROOT'])

def glb(shape,path):
    verts,faces=shape.tessellate(.5)
    # FreeCAD Z-up mm -> glTF Y-up metres, preserving handedness.
    xyz=[(v.x/1000,v.z/1000,-v.y/1000) for v in verts]
    pos=struct.pack('<'+'f'*3*len(xyz),*[n for v in xyz for n in v]);idx=struct.pack('<'+'I'*3*len(faces),*[i for f in faces for i in f]);blob=pos+idx
    lo=[min(v[i] for v in xyz) for i in range(3)];hi=[max(v[i] for v in xyz) for i in range(3)]
    doc={'asset':{'version':'2.0','generator':'ARIA FreeCAD dimension export'},'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'mesh':0}],
         'meshes':[{'primitives':[{'attributes':{'POSITION':0},'indices':1,'material':0}]}],
         'materials':[{'pbrMetallicRoughness':{'baseColorFactor':[.18,.40,.66,1],'metallicFactor':0,'roughnessFactor':.8}}],
         'buffers':[{'byteLength':len(blob)}],'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':len(pos),'target':34962},{'buffer':0,'byteOffset':len(pos),'byteLength':len(idx),'target':34963}],
         'accessors':[{'bufferView':0,'componentType':5126,'count':len(xyz),'type':'VEC3','min':lo,'max':hi},{'bufferView':1,'componentType':5125,'count':len(faces)*3,'type':'SCALAR'}]}
    j=json.dumps(doc,separators=(',',':')).encode();j+=b' '*((-len(j))%4);blob+=b'\0'*((-len(blob))%4)
    path.write_bytes(struct.pack('<4sII',b'glTF',2,12+8+len(j)+8+len(blob))+struct.pack('<I4s',len(j),b'JSON')+j+struct.pack('<I4s',len(blob),b'BIN\0')+blob)
    return [(hi[i]-lo[i])*1000 for i in range(3)]

for name,dims in [('conveyor',(2000,600,700)),('inspection_booth',(800,800,1500)),('diverter',(1000,600,700))]:
    out=ROOT/'assets/cad'/name/'dt_v1';out.mkdir(parents=True,exist_ok=False)
    doc=App.newDocument('ARIA_'+name);obj=doc.addObject('Part::Box','DesignEnvelope');obj.Length,obj.Width,obj.Height=dims;doc.recompute()
    assert obj.Shape.isValid() and len(obj.Shape.Solids)==1
    Part.export([obj],str(out/'model.step'));doc.saveAs(str(out/'model.FCStd'))
    actual=glb(obj.Shape,out/'model.glb');expected=[dims[0],dims[2],dims[1]];error=max(abs(a-b) for a,b in zip(actual,expected));assert error<=1
    report=dict(part=name,version='dt_v1',source='cad',meaning='assumed design dimensions; not datasheet or physical measurement',unit='mm',cad_axis='Z-up',glb_axis='Y-up',length_mm=dims[0],width_mm=dims[1],height_mm=dims[2],glb_bbox_xyz_mm=actual,bbox_max_error_mm=error,valid_solids=1,freecad_version='.'.join(App.Version()[:3]),files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()},scope='simple design envelopes, not mechanical/camera/robot safety validation')
    (out/'dims.json').write_text(json.dumps(report,indent=2));App.closeDocument(doc.Name);print(name,report,flush=True)
