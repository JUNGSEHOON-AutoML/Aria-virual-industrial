"""Content-addressed, bounded FreeCAD job service. No user-supplied scripts."""
import hashlib,json,os,subprocess,tempfile,threading
from pathlib import Path
from pydantic import BaseModel,ConfigDict,Field

class CNCParameters(BaseModel):
 model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
 width_mm:float=Field(default=2500,ge=1800,le=3000)
 depth_mm:float=Field(default=1900,ge=1400,le=2100)
 height_mm:float=Field(default=2600,ge=2200,le=3000)

class CADService:
 def __init__(self,root):
  self.root=Path(root);self.directory=self.root/'outputs'/'cad-assets';self.lock=threading.Lock()
  self.runtime=Path(os.environ.get('ARIA_FREECAD_RUNTIME',str(self.root/'outputs/cad-runtime/squashfs-root')))
 def status(self):
  return dict(available=(self.runtime/'usr/bin/python').is_file() and (self.runtime/'AppRun').is_file(),engine='FreeCAD',scope='CNC body generation and static solid checks')
 def asset(self,aid):
  if len(aid)!=24 or any(c not in '0123456789abcdef' for c in aid):raise ValueError('Invalid CAD asset ID')
  p=self.directory/aid
  if not (p/'report.json').is_file():raise FileNotFoundError('CAD asset not generated')
  return dict(id=aid,report=json.loads((p/'report.json').read_text()),files={n:f'/api/factory/cad/assets/{aid}/{n}' for n in ('mesh.json','cnc.FCStd','cnc.step','report.json')})
 def build(self,parameters):
  p=CNCParameters.model_validate(parameters).model_dump()
  worker=Path(__file__).with_name('worker.py')
  aid=hashlib.sha256(json.dumps(p,sort_keys=True).encode()+worker.read_bytes()+b'freecad-1.1.3').hexdigest()[:24]
  if (self.directory/aid/'report.json').is_file():return self.asset(aid)
  if not self.status()['available']:raise RuntimeError('FreeCAD runtime unavailable; run tools/install_freecad.py')
  if not self.lock.acquire(blocking=False):raise RuntimeError('A CAD job is already running; retry when it completes')
  try:
   self.directory.mkdir(parents=True,exist_ok=True)
   with tempfile.TemporaryDirectory(prefix='job-',dir=self.directory) as tmp:
    tmp=Path(tmp);request=tmp/'request.json';target=tmp/'artifact'
    request.write_text(json.dumps(dict(parameters=p,output=str(target))))
    env=os.environ.copy();env.update(ARIA_CAD_REQUEST=str(request),PYTHONPATH=str(self.runtime/'usr/lib'),QT_QPA_PLATFORM='offscreen',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    try:
     result=subprocess.run([str(self.runtime/'AppRun'),'python',str(worker)],env=env,cwd=tmp,capture_output=True,text=True,timeout=60)
    except subprocess.TimeoutExpired as e:raise RuntimeError('FreeCAD exceeded the 60 second job budget') from e
    if result.returncode!=0:raise RuntimeError('FreeCAD generation failed: '+result.stderr[-1200:])
    report=json.loads((target/'report.json').read_text())
    if not report['all_solids_valid']:raise RuntimeError('FreeCAD generated invalid solids')
    target.rename(self.directory/aid)
   return self.asset(aid)
  finally:self.lock.release()
