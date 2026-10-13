import {useEffect,useRef,useState} from 'react'

// The server owns time. No wall-clock extrapolation or client-generated parts.
export function useLive(enabled){
 const store=useRef({snapshot:null,listeners:new Set()}),[snapshot,setSnapshot]=useState(null),[connected,setConnected]=useState(false),[error,setError]=useState(''),[pending,setPending]=useState(false)
 useEffect(()=>{
  if(!enabled)return
  let socket,retry,stopped=false,lastUI=0
  const connect=()=>{
   socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/api/live/ws`)
   socket.onopen=()=>{setConnected(true);setError('')}
   socket.onmessage=e=>{
    const data=JSON.parse(e.data);store.current.snapshot=data
    store.current.listeners.forEach(fn=>fn())
    if(performance.now()-lastUI>250){setSnapshot(data);lastUI=performance.now()}
   }
   socket.onerror=()=>setError('Live 연결을 확인하고 있습니다.')
   socket.onclose=()=>{setConnected(false);if(!stopped)retry=setTimeout(connect,1500)}
  };connect()
  return ()=>{stopped=true;clearTimeout(retry);socket?.close();setConnected(false)}
 },[enabled])
 const command=async(path,body={})=>{
  setPending(true);setError('')
  try{
   const response=await fetch(`/api/live/${path}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
   const data=await response.json();if(!response.ok)throw Error(data.detail||'Live 요청 실패')
   return data
  }catch(e){setError(e.message)}finally{setPending(false)}
 }
 useEffect(()=>{window.__live={...window.__live,store:store.current,connected,command}},[connected])
 return {store,snapshot,connected,error,pending,command}
}
