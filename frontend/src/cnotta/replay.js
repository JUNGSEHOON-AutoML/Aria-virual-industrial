// Time advances a saved timeline; this module never creates events or verdicts.
export const activeAt=(parts,t)=>parts.filter(p=>p.born<=t&&(p.exit_time==null||t<p.exit_time))
export const queueAt=(queue,t)=>{let n=0;for(const q of queue){if(q.time>t)break;n=q.count}return n}
export const STATIONS={SOURCE:[-10,.85,0],BUFFER:[-7,.85,0],'AI-INSPECTION':[-3.6,.85,0],DIVERTER:[-.7,.85,0],'GOOD-SINK':[6.3,.85,-1.8],'REJECT-SINK':[6.6,.85,4.4],'HOLD-SINK':[6.3,.85,1.8]}
export function positionAt(p,t){const e=p.entries;let current=0;while(current+1<e.length&&e[current+1].time<=t)current++;const a=e[current];if(!a)return STATIONS.SOURCE;const b=e[current+1];const start=STATIONS[a.component]||STATIONS.BUFFER; // A dwell remains at its recorded station; instantaneous transfers never acquire invented travel time.
 if(!b||b.time<=a.time||a.component==='AI-INSPECTION'||a.component==='BUFFER')return start
 const end=STATIONS[b.component]||start;const f=Math.max(0,Math.min(1,(t-a.time)/(b.time-a.time)));return start.map((v,i)=>v+(end[i]-v)*f)
}
