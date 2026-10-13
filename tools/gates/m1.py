import json,math
import numpy as np
from PIL import Image
from tools.gates.common import ROOT,emit

def main():
 p=ROOT/'docs/autopilot/local';r=json.loads((p/'browser.json').read_text());a=r['audit'];im=np.asarray(Image.open(p/'m1.png').convert('RGB'));t=json.loads((ROOT/'frontend/src/brand/cnotta.tokens.json').read_text())
 rgb=lambda s:np.array([int(s[i:i+2],16) for i in (1,3,5)])
 samples={}
 for k,xy in a['samples'].items():
  x,y=map(round,xy);valid=0<=x<im.shape[1] and 0<=y<im.shape[0];pixel=im[y,x] if valid else np.array([-999]*3);delta=abs(pixel-rgb(t[k]));samples[k]={'xy':[x,y],'rgb':pixel.tolist(),'max_error':int(delta.max()),'pass':bool(valid and max(delta)<=6)}
 b=a['processBounds'];fill=max(0,b[2]-b[0])*max(0,b[3]-b[1]);hsv=np.asarray(Image.open(p/'m1.png').convert('HSV'));primary=float(np.mean((hsv[:,:,0]>=155)&(hsv[:,:,0]<=183)&(hsv[:,:,1]>=70)&(hsv[:,:,2]>=70)))
 overlap=[]
 for i,l in enumerate(a['lanes']):
  for j,rack in enumerate(a['racks']):
   if all(min(l['max'][k],rack['max'][k])-max(l['min'][k],rack['min'][k])>.01 for k in [0,2]):overlap.append([i,j])
 floating=[o for o in a['grounded'] if abs(o['min'][1])>.02]
 return emit('m1',{'surface_pixels':{'pass':all(v['pass'] for v in samples.values()),'samples':samples},'lane_rack_overlap':{'pass':not overlap,'pairs':overlap},'ground_contact':{'pass':not floating,'violations':floating,'scope':'assembly AABB, tolerance .02m'},'viewport_fill':{'pass':fill>=.7,'ratio':fill,'metric':'clipped projected process-area bounding rectangle / viewport'},'primary_area':{'pass':primary<=.1,'ratio':primary,'metric':'primary hue family including shaded pixels (HSV H 155..183, S>=70,V>=70)'},'console':{'pass':not r['errors'],'errors':r['errors']}},hardware_GPU_verified=False)
if __name__=='__main__':raise SystemExit(0 if main()['pass'] else 1)
