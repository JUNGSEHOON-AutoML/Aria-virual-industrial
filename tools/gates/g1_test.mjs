import assert from 'node:assert/strict'
import fs from 'node:fs'
import {indexTimeline,indexedAt,createClock,permit,pathAt} from '../../frontend/src/motion/core.mjs'
const registry=JSON.parse(fs.readFileSync(new URL('../../configs/ambient_motion.json',import.meta.url)))
assert.equal(permit(registry,'missing','source','sim'),false)
assert.equal(permit(registry,'replay.parts','fake','sim'),false)
assert.equal(permit(registry,'replay.parts','api:/api/dt/runs/{id}/timeline#parts','sim'),true)
assert.equal(permit({...registry,motions:registry.motions.map(x=>({...x,enabled:false}))},'replay.parts','api:/api/dt/runs/{id}/timeline#parts','sim'),false)
const timeline={parts:Array.from({length:400},(_,i)=>({part_id:String(i),born:i%100,exit_time:i%7?i%100+3:null,verdict:i%2?'NG':'OK',inspection_time:i%100+1}))}
const index=indexTimeline(timeline)
for(let t=0;t<=110;t+=.5)assert.deepEqual(indexedAt(timeline,index,t),timeline.parts.filter(p=>p.born<=t&&(p.exit_time==null||t<p.exit_time)))
const positions=[]
for(const speed of [1,10,60]){const c=createClock(0);c.rate(speed);c.play(true);c.tick(0);c.tick(2000/speed);assert.equal(c.read(),2);positions.push(pathAt([[0,0,0],[5,0,0],[5,0,5]],0,10,c.read()).position);c.play(false);c.tick(100000);assert.equal(c.read(),2)}
assert.deepEqual(positions[0],positions[1]);assert.deepEqual(positions[1],positions[2])
for(let t=0;t<=10;t+=.01){const {position:[x,y,z]}=pathAt([[0,0,0],[5,0,0],[5,0,5]],0,10,t);assert.equal(y,0);assert.ok((x>=0&&x<=5&&z===0)||(x===5&&z>=0&&z<=5))}
const {compilePath,samplePath}=await import('../../frontend/src/motion/core.mjs')
const route=compilePath([[0,0,0],[5,0,0],[5,0,5]],0,10,{radius:1,turnRate:Math.PI/2,step:.02})
for(let i=1;i<route.samples.length;i++){const a=route.samples[i-1],b=route.samples[i];assert.ok(Math.abs(b.yaw-a.yaw)/(b.time-a.time)<=Math.PI/2+1e-8)}
assert.deepEqual(samplePath(route,0).position,[0,0,0]);assert.deepEqual(samplePath(route,10).position,[5,0,5])
console.log(JSON.stringify({pass:true,index_samples:221,speeds:[1,10,60],same_time_position_diff:0,unregistered_denied:true,paused_position_diff:0,path_outliers:0}))
