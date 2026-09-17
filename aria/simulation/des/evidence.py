"""Bounded inspection artifacts: detector output is not a 3D reconstruction."""
import hashlib
import json
import re
import threading
from pathlib import Path
import numpy as np
from PIL import Image

class EvidenceStore:
    def __init__(self, root):
        self.root=Path(root)
        self.directory=self.root/'outputs/factory-evidence'
        self.lock=threading.RLock()

    def save(self,image,result,metadata):
        source=Path(image).read_bytes()
        raw=np.asarray(result.get('heatmap'),dtype=np.float32)
        if raw.ndim!=2 or not raw.size or not np.isfinite(raw).all():
            raise ValueError('Detector did not return a finite 2D anomaly map')
        key=hashlib.sha256(source+raw.tobytes()+json.dumps(metadata,sort_keys=True).encode()).hexdigest()[:32]
        with self.lock:
            folder=self.directory/key;folder.mkdir(parents=True,exist_ok=True)
            im=Image.open(image).convert('RGB');width,height=im.size
            display=im.copy();display.thumbnail((768,768));display.save(folder/'original.png')
            lo,hi=float(raw.min()),float(raw.max())
            heat=(raw-lo)/max(hi-lo,1e-9)
            heat=np.asarray(Image.fromarray(heat).resize(display.size,Image.Resampling.BILINEAR))
            color=np.zeros((*heat.shape,3),dtype=np.float32);color[:,:,0]=255;color[:,:,1]=160*(1-heat)
            alpha=heat[:,:,None]*.65
            overlay=np.asarray(display)*(1-alpha)+color*alpha
            Image.fromarray(np.uint8(overlay.clip(0,255))).save(folder/'overlay.png')
            y,x=np.unravel_index(int(raw.argmax()),raw.shape)
            record=dict(id=key,**metadata,source_image=str(image),source_sha256=hashlib.sha256(source).hexdigest(),
                original_size=[width,height],map_shape=list(raw.shape),map_min=lo,map_max=hi,
                peak_uv=[(int(x)+.5)/raw.shape[1],(int(y)+.5)/raw.shape[0]],
                peak_pixel=[round((int(x)+.5)*width/raw.shape[1]),round((int(y)+.5)*height/raw.shape[0])],
                localization='2D detector patch response; no measured depth',
                heatmap_scale='per-image min/max for display, not a calibrated segmentation threshold',
                original_url=f'/api/factory/evidence/{key}/original.png',overlay_url=f'/api/factory/evidence/{key}/overlay.png')
            (folder/'metadata.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
            # Bound retained disk artifacts. Expired IDs return 404, never a replacement sample.
            folders=sorted((p for p in self.directory.iterdir() if p.is_dir() and re.fullmatch('[0-9a-f]{32}',p.name)),key=lambda p:p.stat().st_mtime)
            import shutil
            for old in folders[:-200]:shutil.rmtree(old)
            return record

    def file(self,key,name):
        if not re.fullmatch('[0-9a-f]{32}',key) or name not in ('original.png','overlay.png','metadata.json'):
            raise ValueError('Invalid evidence asset')
        p=self.directory/key/name
        if not p.is_file():raise ValueError('Evidence missing or expired')
        return p
