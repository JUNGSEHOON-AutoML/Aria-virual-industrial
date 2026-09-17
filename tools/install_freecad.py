"""Install pinned official FreeCAD AppImage under ignored outputs/cad-runtime."""
import hashlib,json,os,subprocess,urllib.request
from pathlib import Path
root=Path.cwd()/'outputs'/'cad-runtime';root.mkdir(parents=True,exist_ok=True)
url='https://github.com/FreeCAD/FreeCAD/releases/download/1.1.3/FreeCAD_1.1.3-Linux-x86_64-py311.AppImage'
expected='3a853eb69ee595f779f2255dbf80a765926981d8ff68903cefee4dfb03a8f5ef'
p=root/'FreeCAD-1.1.3.AppImage'
if not p.exists():
 print('Downloading official FreeCAD 1.1.3 (821 MB)',flush=True)
 urllib.request.urlretrieve(url,p)
with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest() if hasattr(hashlib,'file_digest') else hashlib.sha256(f.read()).hexdigest()
assert digest==expected,'SHA256 mismatch'
p.chmod(0o755)
if not (root/'squashfs-root').is_dir():
 with (root/'extraction.log').open('w') as log:subprocess.run([str(p),'--appimage-extract'],cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True)
(root/'provenance.json').write_text(json.dumps(dict(version='1.1.3',url=url,sha256=digest),indent=2))
print('Verified and extracted:',root,flush=True)
