import {useEffect,useRef,useState} from 'react'
import {createClock} from './core.mjs'
export function useReplayClock() {
  const clock=useRef(null);if(!clock.current)clock.current=createClock()
  const [,update]=useState(0),c=clock.current
  useEffect(()=>c.subscribe(()=>update(n=>n+1)),[c])
  useEffect(()=>{let frame;const tick=now=>{c.tick(now);for(const listener of c.frames||[])listener();frame=requestAnimationFrame(tick)};frame=requestAnimationFrame(tick);return()=>cancelAnimationFrame(frame)},[c])
  return {clock:c,time:c.read(),setTime:t=>c.seek(t),playing:c.playing,setPlaying:v=>c.play(v),speed:c.speed,setSpeed:v=>c.rate(v)}
}
export function subscribeFrame(clock,fn){clock.frames??=new Set();clock.frames.add(fn);return()=>clock.frames.delete(fn)}
