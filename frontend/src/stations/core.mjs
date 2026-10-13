import {upperBound} from '../motion/core.mjs'

export function equipmentAt(rows,t){
 const row=rows[Math.max(0,upperBound(rows,t,'start')-1)]
 if(!row||t<row.start)return {distance:0,speed:0,state:'UNKNOWN',lamp:'STOP'}
 return {...row,distance:row.distance+Math.max(0,Math.min(t,row.end)-row.start)*row.speed}
}
export function pulseAt(rows,t,key,seconds){
 const n=upperBound(rows,t,key),row=rows[n-1]
 return !!row&&row[key]!=null&&t>=row[key]&&t<row[key]+seconds
}
export function stationPosition(part,t,cls,config){
 const begin=part.trigger,end=part.arrival??part.exit??begin
 const f=end>begin?Math.max(0,Math.min(1,(t-begin)/(end-begin))):0
 if(cls==='screw'){
  const d=config.screw,a=d.trigger_angle+(d.nozzle_angle-d.trigger_angle)*f
  return {position:[d.center[0]+d.radius_m*Math.cos(a),d.center[1],d.center[2]+d.radius_m*Math.sin(a)],yaw:-a}
 }
 const d=config[cls],target=cls==='carpet'?d.marker:d.eject
 return {position:d.trigger.map((v,i)=>v+(target[i]-v)*f),yaw:0}
}
export function inspectionState(data,t){
 if(!data)return {lamp:'STOP',distance:0,rollerAngle:0,flash:false,sensor:false,eject:false,mark:false,verdict:null}
 const eq=equipmentAt(data.equipment,t),seconds=data.geometry.motion.pulse_seconds
 const triggered=data.parts,arrivals=data.arrivals||[],decisions=data.decisions||[]
 const n=upperBound(decisions,t,'decision'),last=decisions[n-1]
 const at=arrivals[upperBound(arrivals,t,'arrival')-1]
 return {...eq,rollerAngle:eq.distance/data.geometry.motion.roller_radius_m,
  sensor:pulseAt(triggered,t,'trigger',seconds),flash:pulseAt(triggered,t,'trigger',seconds),
  arrive:!!at&&pulseAt(arrivals,t,'arrival',seconds),
  route:at?.route??null,
  eject:!!at&&at.route==='NG'&&pulseAt(arrivals,t,'arrival',seconds),
  hold:!!at&&at.route==='HOLD'&&pulseAt(arrivals,t,'arrival',seconds),
  mark:!!at&&at.verdict==='NG'&&at.decision!=null&&at.decision<=at.arrival&&pulseAt(arrivals,t,'arrival',seconds),
  verdict:last?.verdict??null,lastDecision:last?.id??null,lastArrival:at?.id??null}
}
export function prepareStation(data){
 return {...data,byId:new Map(data.parts.map(p=>[p.id,p])),
  decisions:data.parts.filter(p=>p.decision!=null).sort((a,b)=>a.decision-b.decision),
  arrivals:data.parts.filter(p=>p.arrival!=null).sort((a,b)=>a.arrival-b.arrival)}
}
export function transferState(rows,t){
 const total=rows.at(-1).start+rows.at(-1).duration,time=Math.max(0,Math.min(total,t))
 const row=rows.find(r=>time<r.start+r.duration)||rows.at(-1),u=Math.max(0,Math.min(1,(time-row.start)/row.duration)),f=10*u**3-15*u**4+6*u**5
 const attached=['MOVE_TRANSFER','TRANSFER','MOVE_PLACE'].includes(row.stage)
 const released=time>=rows.find(r=>r.stage==='RELEASE').start
 return {joints:row.from_q.map((v,i)=>v+(row.target[i]-v)*f),stage:row.stage,attached,gripper:attached?'CLOSED':'OPEN',fixture:released?rows[4].target:rows[0].target}
}
