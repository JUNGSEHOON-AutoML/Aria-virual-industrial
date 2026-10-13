// Pure deterministic sampling: speed changes the clock, never a path or event.
export function permit(registry, id, source, clock) {
  const m = registry.motions.find(row => row.id === id)
  return registry.default_action === 'deny' && !!m?.enabled && m.kind === 'event' && !!m.source && !!m.clock && m.source === source && m.clock === clock
}
export function upperBound(rows, t, key) {
  let lo=0,hi=rows.length
  while(lo<hi){const mid=(lo+hi)>>>1;if(rows[mid][key]<=t)lo=mid+1;else hi=mid}
  return lo
}
export function indexTimeline(timeline) {
  // Sweep line creates active-set checkpoints once in the Worker, not each frame.
  const events=timeline.parts.flatMap((p,i)=>[{time:p.born,i,add:true},...(p.exit_time==null?[]:[{time:p.exit_time,i,add:false}])]).sort((a,b)=>a.time-b.time||Number(a.add)-Number(b.add))
  const active=new Set(),checkpoints=[]
  for(let i=0;i<events.length;i++){
    const e=events[i];if(e.add)active.add(e.i);else active.delete(e.i)
    if(i%128===127||i===events.length-1)checkpoints.push({time:e.time,index:i,active:[...active]})
  }
  return {events,checkpoints,inspections:timeline.parts.filter(p=>p.verdict==='NG'&&p.inspection_time!=null).map(p=>({time:p.inspection_time})).sort((a,b)=>a.time-b.time)}
}
export function indexedAt(timeline,index,t) {
  if(!index)return []
  const at=upperBound(index.events,t,'time'),checkpoint=Math.floor(at/128)-1
  const base=checkpoint>=0?index.checkpoints[checkpoint]:null
  const active=new Set(base?.active||[])
  for(let n=base?base.index+1:0;n<at;n++){const e=index.events[n];if(e.add)active.add(e.i);else active.delete(e.i)}
  return [...active].sort((a,b)=>a-b).map(i=>timeline.parts[i]).filter(p=>p.born<=t&&(p.exit_time==null||p.exit_time>t))
}
export const ease = f => {const u=Math.max(0,Math.min(1,f));return u*u*(3-2*u)}
export function pathAt(points,start,end,t) {
  if(!points.length)throw Error('Empty motion path')
  const lengths=points.slice(1).map((p,i)=>Math.hypot(...p.map((v,k)=>v-points[i][k])))
  let distance=lengths.reduce((a,b)=>a+b,0)*ease(end>start?(t-start)/(end-start):1)
  for(let i=0;i<lengths.length;i++){
    if(distance<=lengths[i]||i===lengths.length-1){const f=lengths[i]?Math.max(0,Math.min(1,distance/lengths[i])):0;return {position:points[i].map((v,k)=>v+(points[i+1][k]-v)*f),yaw:Math.atan2(points[i+1][0]-points[i][0],points[i+1][2]-points[i][2])}}
    distance-=lengths[i]
  }
  return {position:[...points[0]],yaw:0}
}
export function createClock(initial=600,horizon=3600) {
  let time=initial,playing=false,speed=1,last=null
  const listeners=new Set()
  const notify=()=>listeners.forEach(f=>f())
  return {read:()=>time,get playing(){return playing},get speed(){return speed},
    seek(t){if(!Number.isFinite(t))return;time=Math.max(0,Math.min(horizon,t));last=null;notify()},
    play(value){playing=!!value;last=null;notify()},rate(value){if(![1,10,60].includes(value))throw Error('Invalid replay speed');speed=value;last=null;notify()},
    tick(now){if(playing&&last!=null){time=Math.min(horizon,Math.round((time+Math.max(0,now-last)*speed/1000)*1e9)/1e9);if(time===horizon)playing=false}last=now;return time},
    subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn)},notify}
}
// Compile rounded corners and bounded tangent-following headings on the sim clock.
// Geometry/turn rate are authored assumptions; event start/end are preserved.
export function compilePath(points,start,end,{radius,turnRate,step}) {
 if(!(radius>0&&turnRate>0&&step>0&&end>=start))throw Error('Invalid path assumptions')
 const rounded=[points[0]]
 for(let i=1;i<points.length-1;i++){
  const a=points[i-1],b=points[i],c=points[i+1],ab=Math.hypot(...b.map((v,k)=>v-a[k])),bc=Math.hypot(...c.map((v,k)=>v-b[k])),cut=Math.min(radius,ab/2,bc/2)
  if(!cut){rounded.push(b);continue}
  const p=b.map((v,k)=>v+(a[k]-v)*cut/ab),q=b.map((v,k)=>v+(c[k]-v)*cut/bc)
  rounded.push(p)
  for(let n=1;n<=12;n++){const f=n/12;rounded.push(b.map((v,k)=>(1-f)**2*p[k]+2*(1-f)*f*v+f*f*q[k]))}
 }
 rounded.push(points.at(-1));const count=Math.max(1,Math.ceil((end-start)/step)),samples=[]
 for(let i=0;i<=count;i++){
  const time=start+(end-start)*i/count,s=pathAt(rounded,start,end,time),previous=samples.at(-1)
  if(previous){const delta=Math.atan2(Math.sin(s.yaw-previous.yaw),Math.cos(s.yaw-previous.yaw)),bound=turnRate*(time-previous.time);s.yaw=previous.yaw+Math.max(-bound,Math.min(bound,delta))}
  samples.push({time,...s})
 }
 return {points:rounded,start,end,samples,assumed:{radius,turnRate,step}}
}
export function samplePath(path,time){
 const n=upperBound(path.samples,time,'time'),a=path.samples[Math.max(0,n-1)],b=path.samples[Math.min(n,path.samples.length-1)]
 const f=b.time>a.time?Math.max(0,Math.min(1,(time-a.time)/(b.time-a.time))):0
 return {position:a.position.map((v,k)=>v+(b.position[k]-v)*f),yaw:a.yaw+(b.yaw-a.yaw)*f}
}
