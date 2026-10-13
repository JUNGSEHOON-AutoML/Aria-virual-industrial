import {useEffect,useRef,useState} from 'react'
export function useTimelineIndexes(timelines){
 const [indexes,setIndexes]=useState({}),worker=useRef(),sent=useRef(new Map())
 useEffect(()=>{const w=new Worker(new URL('./timeline.worker.js',import.meta.url),{type:'module'});worker.current=w;sent.current.clear();w.onmessage=({data})=>{if(data.error)console.error(data.error);else setIndexes(old=>({...old,[data.id]:data.index}))};return()=>{w.terminate();worker.current=null}},[])
 useEffect(()=>{for(const [id,timeline] of Object.entries(timelines)){if(sent.current.get(id)===timeline)continue;sent.current.set(id,timeline);worker.current.postMessage({id,timeline})}},[timelines])
 return indexes
}
