"""Fixed FreeCAD worker: validated dimensions in mm, CAD Z-up -> ARIA Y-up."""
import json,os,time
from pathlib import Path
import FreeCAD as App
import Part

def build(request):
 start=time.perf_counter();p=request['parameters'];out=Path(request['output']);out.mkdir(parents=True,exist_ok=True)
 w,d,h=p['width_mm'],p['depth_mm'],p['height_mm'];t=140
 doc=App.newDocument('ARIA_CNC');items=[]
 def box(x,y,z,a,b,c):return Part.makeBox(a,b,c,App.Vector(x,y,z))
 def add(name,shape,color):
  obj=doc.addObject('PartDesign::Feature',name);obj.Label=name;obj.Shape=shape;items.append((obj,color));return obj
 master=doc.addObject('App::FeaturePython','Dimensions')
 for key,value in p.items():master.addProperty('App::PropertyLength',key,'Dimensions');setattr(master,key,value)
 add('Base',box(-w/2,-d/2,0,w,d,250),'#197c86')
 add('RearWall',box(-w/2,d/2-t,250,w,t,h-250),'#c5d1d4')
 add('LeftWall',box(-w/2,-d/2,250,t,d-t,h-250),'#dce3e5')
 add('RightWall',box(w/2-t,-d/2,250,t,d-t,h-250),'#dce3e5')
 add('Roof',box(-w/2+t,-d/2,h-t,w-2*t,d-t,t),'#edf1ef')
 frame=box(-w/2+t,-d/2,250,w-2*t,65,h-250-t)
 opening=box(-w*.29,-d/2-1,780,w*.58,67,h-1050)
 add('FrontFrame',frame.cut(opening),'#aebdc2')
 add('Bed',box(-w*.31,-d*.29,450,w*.62,d*.58,180),'#485e6c')
 table=box(-w*.27,-d*.26,630,w*.54,d*.52,80)
 for i in range(5):table=table.cut(box(-w*.22+i*w*.11,-d*.27,690,24,d*.54,25))
 add('SlottedTable',table,'#becbd0')
 add('SpindleHousing',box(-150,0,h-850,300,330,500),'#527480')
 add('Spindle',Part.makeCylinder(70,230,App.Vector(0,140,h-1080)),'#bdcbd0')
 add('Tool',Part.makeCylinder(22,120,App.Vector(0,140,h-1200)),'#f0bd37')
 add('Console',box(w*.32,-d/2-90,h*.56,w*.11,90,h*.24),'#354d5b')
 add('Display',box(w*.335,-d/2-95,h*.65,w*.08,5,h*.1),'#22b8bd')
 for i in range(3):add('Button'+str(i),Part.makeCylinder(18,8,App.Vector(w*.34+i*55,-d/2-98,h*.6),App.Vector(0,-1,0)),'#ed9850' if i==2 else '#758d97')
 doc.recompute();meshes=[];validation=[];interference=[]
 for obj,color in items:
  shape=obj.Shape;vertices,faces=shape.tessellate(3.0)
  meshes.append(dict(name=obj.Name,color=color,positions=[v for pt in vertices for v in (pt.x/1000,pt.z/1000,-pt.y/1000)],indices=[i for face in faces for i in face]))
  validation.append(dict(name=obj.Name,valid=shape.isValid(),solids=len(shape.Solids),volume_mm3=shape.Volume))
 for i,(a,_) in enumerate(items):
  for b,_ in items[i+1:]:
   overlap=a.Shape.common(b.Shape).Volume
   if overlap>1e-3:interference.append(dict(a=a.Name,b=b.Name,overlap_mm3=overlap))
 compound=Part.makeCompound([obj.Shape for obj,_ in items]);bounds=compound.BoundBox
 doc.saveAs(str(out/'cnc.FCStd'));compound.exportStep(str(out/'cnc.step'))
 (out/'mesh.json').write_text(json.dumps(dict(units='m',up_axis='Y',meshes=meshes),separators=(',',':')))
 report=dict(engine='FreeCAD',version='.'.join(App.Version()[:3]),parameters=p,units='mm',cad_up_axis='Z',web_up_axis='Y',parts=len(items),triangles=sum(len(m['indices'])//3 for m in meshes),all_solids_valid=all(v['valid'] and v['solids']>0 for v in validation),validation=validation,static_interferences=interference,envelope_mm=dict(width=bounds.XLength,depth=bounds.YLength,height=bounds.ZLength),elapsed_seconds=time.perf_counter()-start,scope='CNC body only; static BRep overlaps; no robot swept-volume or motion safety validation')
 (out/'report.json').write_text(json.dumps(report,indent=2));App.closeDocument(doc.Name)
if __name__=='__main__':build(json.loads(Path(os.environ['ARIA_CAD_REQUEST']).read_text()))
