import {useEffect,useRef,useState} from 'react'
import {useReplayClock} from '../motion/clock'
export function useCampusReplay(enabled=true){
 const [catalog,setCatalog]=useState(null),[timelines,setTimelines]=useState({}),[kpis,setKpis]=useState({}),[error,setError]=useState('')
 const clockState=useReplayClock(),{clock,time,setTime,playing,setPlaying,speed,setSpeed}=clockState;const [illustrate,setIllustrate]=useState(true)
 const current=useRef(time);current.current=time
 useEffect(()=>{if(!enabled)return;const c=new AbortController();async function refresh(){try{const response=await fetch('/api/dt/campus',{signal:c.signal});if(!response.ok)throw Error('캠퍼스 실행 목록 읽기 실패');setCatalog(await response.json())}catch(e){if(e.name!=='AbortError')setError(e.message)}}refresh();const timer=setInterval(refresh,30000);return()=>{c.abort();clearInterval(timer)}},[enabled])
 const ids=(catalog?.sites.flatMap(s=>s.lanes.filter(l=>l.run).map(l=>l.run.run_id))||[]).sort().join(',')
 useEffect(()=>{if(!enabled||!ids)return;const c=new AbortController();let alive=true
  // Sequential reads cap server memory pressure during experiment execution.
  async function read(){for(const id of ids.split(',')){if(c.signal.aborted)break;try{const response=await fetch(`/api/dt/runs/${id}/timeline`,{signal:c.signal});if(!response.ok)throw Error(`저장 실행 검증 실패: ${id}`);const data=await response.json();if(alive)setTimelines(x=>({...x,[id]:data}))}catch(e){if(e.name!=='AbortError'&&alive)setError(e.message)}}}read();return()=>{alive=false;c.abort()}
 },[ids,enabled])
 useEffect(()=>{if(!enabled||!ids)return;const c=new AbortController();let timer,last=-1,alive=true
  async function poll(){const collected={};const t=Math.floor(clock.read());if(t!==last){last=t;for(const id of ids.split(',')){if(c.signal.aborted)break;try{const response=await fetch(`/api/dt/runs/${id}/kpi?t=${t}`,{signal:c.signal});if(!response.ok)throw Error('KPI 검증 실패');const data=await response.json();collected[id]=data}catch(e){if(e.name!=='AbortError'&&alive)setError(e.message)}}if(alive)setKpis(collected)}if(alive)timer=setTimeout(poll,1500)}poll();return()=>{alive=false;c.abort();clearTimeout(timer)}
 },[ids,enabled])
 return {clock,catalog,timelines,kpis,error,time,setTime,playing,setPlaying,speed,setSpeed,illustrate,setIllustrate,timeline:Object.values(timelines)[0]}
}
