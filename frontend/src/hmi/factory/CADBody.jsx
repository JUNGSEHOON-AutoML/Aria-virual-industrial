import { useEffect, useState, useMemo } from 'react'
import { Html } from '@react-three/drei'
import * as THREE from 'three'

function Body({ part }) {
  const geometry=useMemo(()=>{
    const g=new THREE.BufferGeometry()
    g.setAttribute('position',new THREE.Float32BufferAttribute(part.positions,3))
    g.setIndex(part.indices);g.computeVertexNormals();return g
  },[part])
  useEffect(()=>()=>geometry.dispose(),[geometry])
  return <mesh geometry={geometry} castShadow receiveShadow><meshStandardMaterial color={part.color} metalness={.3} roughness={.45} flatShading /></mesh>
}
export default function CADBody({ asset, fallback }) {
  const [data,setData]=useState(null),[error,setError]=useState('')
  useEffect(()=>{
    const controller=new AbortController();setData(null);setError('')
    fetch(`/api/factory/cad/assets/${asset}/mesh.json`,{signal:controller.signal}).then(r=>{if(!r.ok)throw Error('CAD asset unavailable');return r.json()}).then(setData).catch(e=>{if(e.name!=='AbortError')setError(e.message)})
    return ()=>controller.abort()
  },[asset])
  return <>{data?data.meshes.map(p=><Body key={p.name} part={p}/>):fallback}
    <Html position={[0,3.15,0]} center zIndexRange={[12,0]}><div className="equipment-decal">{error|| (data?'FreeCAD · CNC':'Loading CAD…')}</div></Html>
  </>
}
