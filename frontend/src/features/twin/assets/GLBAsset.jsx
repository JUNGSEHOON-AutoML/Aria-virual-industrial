import {useMemo} from 'react'
import {useLoader} from '@react-three/fiber'
import {GLTFLoader} from 'three/examples/jsm/loaders/GLTFLoader'
export default function GLB({asset}){const gltf=useLoader(GLTFLoader,asset.uri),scene=useMemo(()=>gltf.scene.clone(true),[gltf]);const scale={m:1,cm:.01,mm:.001}[asset.unit];return <group scale={scale} rotation={asset.up_axis==='Z'?[-Math.PI/2,0,0]:[0,0,0]}><primitive object={scene}/></group>}
