import * as THREE from 'three'
// Count projected equipment fragments using a dedicated software-rendered mask.
export function panelCoverage(scene,camera,gl,width,height){
 const names=new Set(['conveyor','vision-booth','robot-cell','edge-rack','waiting-rack','diverter']);
 const maskScene=new THREE.Scene();maskScene.background=new THREE.Color('black');maskScene.overrideMaterial=new THREE.MeshBasicMaterial({color:'white'});
 scene.updateMatrixWorld(true);scene.traverse(o=>{if(!names.has(o.name))return;for(let a=o.parent;a;a=a.parent)if(names.has(a.name))return;const copy=o.clone(true);copy.matrix.copy(o.matrixWorld);copy.matrixAutoUpdate=false;maskScene.add(copy)});
 const target=new THREE.WebGLRenderTarget(width,height),previous=gl.getRenderTarget();gl.setRenderTarget(target);gl.render(maskScene,camera);const pixels=new Uint8Array(width*height*4);gl.readRenderTargetPixels(target,0,0,width,height,pixels);gl.setRenderTarget(previous);gl.render(scene,camera);target.dispose();maskScene.overrideMaterial.dispose();
 const panels=[...document.querySelectorAll('[data-panel]')].map(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom}});let equipment=0,covered=0;
 for(let y=0;y<height;y++)for(let x=0;x<width;x++){if(pixels[((height-y-1)*width+x)*4]<128)continue;equipment++;if(panels.some(r=>x>=r.x&&x<r.right&&y>=r.y&&y<r.bottom))covered++}
 return {equipment_pixels:equipment,covered_pixels:covered,ratio:equipment?covered/equipment:null,panels,method:'binary render mask of conveyors, vision booth, robot cell, cabinet, racks and diverter'};
}
