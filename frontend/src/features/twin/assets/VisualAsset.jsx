import {Component,Suspense,lazy,useLayoutEffect,useMemo,useRef} from 'react'
import * as THREE from 'three'
import manifest from '../../../../../config/assets/registry.json'
import {AssetRegistry,fenceBoxes,palletBoxes} from './registry.mjs'
export const assets=new AssetRegistry(manifest)
function Boxes({rows}){
 const mesh=useRef(),matrix=useMemo(()=>new THREE.Object3D(),[]),color=useMemo(()=>new THREE.Color(),[])
 useLayoutEffect(()=>{rows.forEach((r,i)=>{matrix.position.set(...r.position);matrix.scale.set(...r.size);matrix.rotation.set(0,0,0);matrix.updateMatrix();mesh.current.setMatrixAt(i,matrix.matrix);mesh.current.setColorAt(i,color.set(r.color))});mesh.current.instanceMatrix.needsUpdate=true;mesh.current.instanceColor.needsUpdate=true;mesh.current.computeBoundingSphere()},[rows,matrix,color])
 return <instancedMesh ref={mesh} args={[undefined,undefined,rows.length]} castShadow receiveShadow><boxGeometry/><meshStandardMaterial metalness={.25} roughness={.48}/></instancedMesh>
}
class AssetBoundary extends Component {state={failed:false};static getDerivedStateFromError(){return {failed:true}};render(){return this.state.failed?this.props.fallback:this.props.children}}
const GLB=lazy(()=>import('./GLBAsset'))
export default function VisualAsset({visual_asset_id,at=[0,0,0],rotation=0,length=3,totes=false,fallback=null}){
 const asset=assets.resolve(visual_asset_id)
 const rows=useMemo(()=>asset.asset_id==='aria.fence'?fenceBoxes(length):asset.asset_id==='aria.pallet'?palletBoxes(totes):[],[asset,length,totes])
 const resolvedFallback=fallback||(asset.fallback?<VisualAsset visual_asset_id={asset.fallback} length={length} totes={totes}/>:null)
 const child=rows.length?<Boxes rows={rows}/>:['glb','gltf'].includes(asset.format)?<AssetBoundary key={asset.asset_id+asset.hash} fallback={resolvedFallback}><Suspense fallback={resolvedFallback}><GLB asset={asset}/></Suspense></AssetBoundary>:resolvedFallback
 return <group position={at} rotation={[0,rotation,0]} userData={{visual_asset_id,profileCategory:asset.asset_id==='aria.fence'?'fence':asset.asset_id==='aria.pallet'?'pallet':asset.format,sourceModule:'AssetRegistry.'+asset.asset_id}}>{child}</group>
}
