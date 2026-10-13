import React,{useMemo,useEffect,useLayoutEffect,useRef} from 'react'
import {useFrame,useLoader,useThree} from '@react-three/fiber'
import {Html,Detailed} from '@react-three/drei'
import * as THREE from 'three'
import {mergeGeometries} from 'three/examples/jsm/utils/BufferGeometryUtils.js'
import {SVGLoader} from 'three/examples/jsm/loaders/SVGLoader.js'
import T from '../brand/cnotta.tokens.json'
import {allowed} from '../motion/registry'
import {BRAND_ASSETS} from '../brand/identity'
import {Site} from '../cnotta/Site'
import {layout,hallSize,laneZ,seededDecorations} from './layout'

// Repeated static boxes share one draw call per material. Entries are local prefab coordinates.
export function Boxes({items,color,name,...props}){
 const geometry=useMemo(()=>{const gs=items.map(([p,s,ry=0])=>{const g=new THREE.BoxGeometry(...s);g.rotateY(ry);g.translate(...p);return g});const g=mergeGeometries(gs);gs.forEach(x=>x.dispose());return g},[items])
 useEffect(()=>()=>geometry?.dispose(),[geometry]);if(!geometry)return null
 return <mesh name={name} geometry={geometry} {...props}><meshStandardMaterial color={color} roughness={.85} emissive={color} emissiveIntensity={.38}/></mesh>
}
export function Instances({items,color,type='box',name}){
 const mesh=useRef();const {invalidate}=useThree()
 useLayoutEffect(()=>{const d=new THREE.Object3D();items.forEach(([p,s,ry=0],i)=>{d.position.fromArray(p);d.scale.fromArray(s);d.rotation.set(0,ry,0);d.updateMatrix();mesh.current.setMatrixAt(i,d.matrix)});mesh.current.count=items.length;mesh.current.instanceMatrix.needsUpdate=true;invalidate()},[items,invalidate])
 return <instancedMesh ref={mesh} name={name} args={[undefined,undefined,Math.max(1,items.length)]} frustumCulled={false}>{type==='tree'?<sphereGeometry args={[.5,8,6]}/>:<boxGeometry/>}<meshStandardMaterial color={color} roughness={.85} emissive={color} emissiveIntensity={.38}/></instancedMesh>
}
function useLogo(url){
 const svg=useLoader(SVGLoader,url,loader=>{const parse=loader.parse.bind(loader);loader.parse=s=>parse(s.replaceAll('currentColor',T.brand.ink))})
 return useMemo(()=>{const shapes=svg.paths.flatMap(path=>SVGLoader.createShapes(path));const g=new THREE.ExtrudeGeometry(shapes,{depth:3,bevelEnabled:false,curveSegments:8});g.computeBoundingBox();const b=g.boundingBox.clone(),size=b.getSize(new THREE.Vector3());g.translate(-(b.min.x+b.max.x)/2,-(b.min.y+b.max.y)/2,0);g.scale(1/size.x,1/size.x,1/size.x);g.computeBoundingBox();return {geometry:g,ratio:size.y/size.x}},[svg])
}
export function Logo({width=10,name='roof-wordmark',...props}){
 const mark=useLogo(BRAND_ASSETS.mark),word=useLogo(BRAND_ASSETS.wordmark)
 const markW=width*.16,gap=width*.04,wordW=width-markW-gap
 return <group {...props} userData={{brandWidth:width}}>
  <mesh name="roof-mark" position={[-width/2+markW/2,0,0]} scale={[markW,-markW,markW]} geometry={mark.geometry}><meshStandardMaterial color={T.brand.primary} emissive={T.brand.primary} emissiveIntensity={.4} roughness={.8} transparent/></mesh>
  <mesh name={name} position={[width/2-wordW/2,0,0]} scale={[wordW,-wordW,wordW]} geometry={word.geometry} userData={{glyphHeight:wordW*word.ratio}}><meshStandardMaterial color={T.brand.ink} emissive={T.brand.ink} emissiveIntensity={.4} roughness={.8} transparent/></mesh>
 </group>
}
function Roof({site,focused,onEnter}){
 const ref=useRef(),fade=useRef(1),{invalidate}=useThree();const {width,depth}=hallSize(site)
 useEffect(()=>{ref.current.userData.opacity=fade.current;invalidate()},[focused,invalidate])
 useFrame((_,dt)=>{if(!allowed('view.roof_fade'))return;const target=focused?0:1;if(Math.abs(fade.current-target)<.001)return;fade.current=THREE.MathUtils.clamp(fade.current+(target?1:-1)*dt/.8,0,1);ref.current.visible=fade.current>0;ref.current.userData.opacity=fade.current;ref.current.traverse(o=>{if(o.material){o.material.transparent=true;o.material.opacity=fade.current;o.material.depthWrite=fade.current>.99}});invalidate()})
 return <group ref={ref} name={'roof-'+site.id} position={[0,layout.design.roof_height,0]} onClick={e=>{e.stopPropagation();onEnter(site.id)}}>
  <Boxes color={T.floor} items={[[[0,-1.2,-depth/2],[width,2.4,.3]],[[0,-1.4,depth/2],[width,2.8,.3]],[[-width/2,-1.2,0],[.3,2.4,depth]],[[width/2,-1.2,0],[.3,2.4,depth]]]}/>
  <Boxes color={T.brand['primary-200']} items={[-.33,0,.33].map(x=>[[width*x,-.95,depth/2+.16],[6,.65,.04]])}/>
  <mesh name="roof-panel"><boxGeometry args={[width+.3,.28,depth+.3]}/><meshStandardMaterial color={T['equip-frame']} emissive={T['equip-frame']} emissiveIntensity={.4} roughness={.9}/></mesh>
  <Logo width={width*layout.design.roof_brand_width_ratio} rotation={[-Math.PI/2,0,0]} position={[0,.15,1]} name={'wordmark-'+site.id}/>
  <Boxes color={T.floor} items={[[[-width*.3,.4,-depth*.36],[3,.5,1.8]],[[width*.3,.4,-depth*.36],[3,.5,1.8]],...[-.4,.4].map(z=>[[0,.19,depth*z],[width-.5,.04,.07]])]} />
 </group>
}
export function Hall({site,focused,onEnter,children}){
 const {width,depth}=hallSize(site),h=layout.design.wall_height
 const shell=useMemo(()=>[[[0,.04,0],[width,.08,depth]],[[0,h/2,-depth/2],[width,h,.3]],[[-width/2,h/2,0],[.3,h,depth]],[[width/2,h/2,0],[.3,h,depth]],[[0,1,depth/2],[width,2,.3]]],[width,depth,h])
 const trim=useMemo(()=>[[[0,h,-depth/2],[width,.14,.38]],[[0,2,depth/2],[width,.18,.38]],...[-.32,.32].flatMap(x=>[[[width*x,1,depth/2+.16],[3.8,2,.08]]]),[[-width/2,h,0],[.38,.14,depth]],[[width/2,h,0],[.38,.14,depth]]],[width,depth,h])
 return <Site origin={site.origin} rotation={site.rotation} lanes={site.lanes}><group name={site.id} userData={{hall:true,dimensions:[width,depth]}}>
  <Boxes name="hall-shell" color={T.floor} items={shell} receiveShadow onClick={e=>{e.stopPropagation();onEnter(site.id)}}/>
  <Boxes name="hall-trim" color={T.brand.ink} items={trim}/><Boxes color={T['equip-frame']} items={[-.32,.32].map(x=>[[width*x,.92,depth/2+.22],[3.2,1.8,.06]])}/>
  <Html position={[0,3,depth/2+.3]} center zIndexRange={[8,1]}><button className="hall-sign" data-hall-name={site.id} onClick={()=>onEnter(site.id)}><small>CNOTTA</small> {site.number}공장 · {site.class.toUpperCase()}</button></Html>
  {children}<Roof site={site} focused={focused} onEnter={onEnter}/>
 </group></Site>
}
// A lane is a shared semantic prefab for both the web and the CPU USD export.
function EquipmentLane({site,index,live}){
 const model=site.lanes[index]
 const shapes=useMemo(()=>{
  const feet=[],racks=[]
  for(const x of [-11,-8,-5,-2,1])for(const z of [-.4,.4])feet.push([[x,.3,z],[.12,.6,.12]])
  for(const x of [12,14.7]){for(const y of [.22,.95,1.68])racks.push([[x,y,1.9],[2.1,.08,.9]]);for(const dx of [-1,1])racks.push([[x+dx,.95,1.9],[.06,1.9,.9]])}
  return {feet,racks}
 },[])
 return <group name={'Lane_'+model} position={[0,0,laneZ(site,index)]} userData={{selector:model,laneIndex:index}}>
  <group name="MainConveyor" userData={{cadPart:'conveyor'}}>
   <Boxes color={T['equip-frame']} items={[[[-5,.63,0],[14,.14,1.05]]]}/>
   <Boxes color={T.brand.primary} items={[[[-5,.72,0],[14,.045,.8]]]}/>
   <Boxes color={T.brand.ink} items={shapes.feet}/>
  </group>
  <group name="Booth" userData={{cadPart:'inspection_booth'}}>
   {!(live&&model==='ccifps')&&<Boxes color={T['equip-frame']} items={[[[-3.6,1.5,-.5],[1.2,.16,.4]],[[-3.6,1,-.67],[1.2,1,.14]],[[-4.15,1,.45],[.1,1,.1]],[[-3.05,1,.45],[.1,1,.1]]]}/>}
  </group>
  <group name="Diverter" userData={{cadPart:'diverter'}}>
   <Boxes color={T['equip-frame']} items={[-1.4,0,1.4].map(z=>[[6,.63,z],[7,.14,.75]])}/>
   <Boxes color={T.brand.primary} items={[-1.4,0,1.4].map(z=>[[6,.72,z],[7,.045,.56]])}/>
  </group>
  <group name="Reinspection">
   <Boxes name="waiting-racks" color={T['text-2']} items={shapes.racks}/>
   <Boxes color={T.brand['primary-200']} items={[[[12.4,.091,1.6],[6.4,.014,3.3]]]}/>
  </group>
 </group>
}
export function LaneEquipment({site,live=false}){
 const {width,depth}=hallSize(site)
 return <group name={'lanes-'+site.id}>
  {site.lanes.map((model,index)=><EquipmentLane key={model} site={site} index={index} live={live}/>)}
  <Boxes color={T.line} items={[[[-width/2+1,.1,0],[.08,.02,depth-2]]]} />
 </group>
}
export function Landscape(){
 const decor=useMemo(()=>{const trees=seededDecorations();const pallets=[],boxes=[],posts=[]
  const yard=layout.sites.find(s=>s.kind==='logistics_yard')
  for(let i=0;i<12;i++){const x=yard.origin[0]-12+(i%6)*4,z=yard.origin[1]-4+Math.floor(i/6)*6;pallets.push([[x,.15,z],[2.5,.3,2]]);for(let j=0;j<3;j++)boxes.push([[x+(j%2-.5)*1.1,.85+Math.floor(j/2)*1.2,z],[1,1.1,1.3]])}
  for(let x=layout.bounds.min[0];x<=layout.bounds.max[0];x+=4)posts.push([[x,.8,layout.bounds.min[1]],[.1,1.6,.1]])
  return {trees:trees.map(([x,z])=>[[x,2,z],[1.8,2.8,1.8]]),trunks:trees.map(([x,z])=>[[x,.7,z],[.18,1.4,.18]]),pallets,boxes,posts}},[])
 const roads=useMemo(()=>layout.roads.flatMap(points=>points.slice(1).map((b,i)=>{const a=points[i],dx=b[0]-a[0],dz=b[1]-a[1];return [[(a[0]+b[0])/2,.015,(a[1]+b[1])/2],[Math.hypot(dx,dz),.03,layout.road_width],-Math.atan2(dz,dx)]})),[])
 return <group name="decorative-campus">
  <mesh rotation={[-Math.PI/2,0,0]} position={[(layout.bounds.min[0]+layout.bounds.max[0])/2,-.02,(layout.bounds.min[1]+layout.bounds.max[1])/2]}><planeGeometry args={[600,600]}/><meshBasicMaterial color={T.surface}/></mesh>
  <Boxes color={T.line} items={roads}/><Boxes color={T.floor} items={layout.roads.flatMap(points=>points.slice(1).flatMap((b,i)=>{const a=points[i],dx=b[0]-a[0],dz=b[1]-a[1],length=Math.hypot(dx,dz);return Array.from({length:Math.floor(length/5)},(_,n)=>{const f=(n+.5)*5/length;return [[a[0]+dx*f,.035,a[1]+dz*f],[2,.02,.09],-Math.atan2(dz,dx)]})}))}/><Instances name="decorative-trees" items={decor.trees} color={T.foliage} type="tree"/><Instances name="decorative-trunks" items={decor.trunks} color={T['text-2']}/><Instances name="decorative-pallets" items={decor.pallets} color={T.cardboard}/><Instances name="decorative-boxes" items={decor.boxes} color={T.cardboard}/><Instances name="decorative-fence" items={decor.posts} color={T['text-2']}/>
  {layout.sites.filter(s=>s.kind!=='inspection_hall').map(site=><Site key={site.id} origin={site.origin} rotation={site.rotation}><group name={'decorative-'+site.id}><Boxes color={T.floor} items={[[[0,.04,0],[site.size[0],.08,site.size[1]]]]}/>{site.kind==='robot_cell'?<><Boxes color={T['equip-frame']} items={[[[0,1.5,-site.size[1]/2],[site.size[0],3,.3]],[[-site.size[0]/2,1.5,0],[.3,3,site.size[1]]],[[0,3.1,-site.size[1]/4],[site.size[0],.2,site.size[1]/2]]]}/><Detailed distances={[0,170]}><Boxes color={T.brand.ink} items={[[[0,.6,0],[3,1.2,3]],[[0,1.8,0],[.7,2,.7]],[[1.2,2.8,0],[2.7,.6,.6]],[[2.5,2.2,0],[.4,1.4,.4]]]}/><Boxes color={T.brand.ink} items={[[[0,1.2,0],[3,2.4,3]]]}/></Detailed></>:<><Boxes color={T['equip-frame']} items={[[[7,1.7,5],[9,2.7,3]],[[12,1.2,5],[2,1.8,3]]]}/><Instances name="decorative-wheels" color={T.brand.ink} type="tree" items={[4,10,12].flatMap(x=>[3.6,6.4].map(z=>[[x,.55,z],[1,1,.4]]))}/></>}<Html position={[0,.2,site.size[1]/2+1.8]} center><span className="campus-place">{site.name}{site.decorative?' · 장식':' · 대기'}</span></Html></group></Site>)}
  <Site origin={layout.entrance.origin} rotation={layout.entrance.rotation}><group name="entrance-pillar"><Boxes color={T.brand.ink} items={[[[0,2,0],[1,4,.8]],[[0,4.2,0],[5.8,1.3,.8]]]}/><Html position={[0,4.2,.45]} center><span className="entrance-sign"><img src={BRAND_ASSETS.mark} alt=""/>CNOTTA</span></Html></group></Site>
 </group>
}
