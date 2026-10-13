import {useEffect,useRef,useState} from 'react'
import {prepareStation} from './core.mjs'

export function useStations(replay,focus,enabled=true){
 const [records,setRecords]=useState({}),[error,setError]=useState('')
 const ids=(replay.catalog?.sites.find(s=>s.id===focus)?.lanes.filter(l=>l.run).map(l=>l.run.run_id)||[]).join(',')
 const loaded=useRef(new Set())
 useEffect(()=>{if(!enabled||!ids)return;const controller=new AbortController()
  async function read(){for(const id of ids.split(',')){if(loaded.current.has(id))continue;try{
   const r=await fetch(`/api/dt/runs/${id}/stations`,{signal:controller.signal});if(!r.ok)throw Error('검사 스테이션 이벤트를 읽지 못했습니다.')
   const data=prepareStation(await r.json());if(!controller.signal.aborted){loaded.current.add(id);setRecords(old=>({...old,[id]:data}))}
  }catch(e){if(e.name!=='AbortError')setError(e.message)}}}
  read();return()=>controller.abort()
 },[ids,enabled])
 useEffect(()=>{window.__stations=window.__stations||{lanes:{}};window.__stations.records=records},[records])
 return {records,error}
}
