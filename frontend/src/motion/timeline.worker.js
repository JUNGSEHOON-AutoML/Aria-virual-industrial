import {indexTimeline} from './core.mjs'
self.onmessage=({data})=>{try{self.postMessage({id:data.id,index:indexTimeline(data.timeline)})}catch(error){self.postMessage({id:data.id,error:error.message})}}
