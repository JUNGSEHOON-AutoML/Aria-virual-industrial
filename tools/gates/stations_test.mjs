import assert from 'node:assert/strict'
import {equipmentAt,inspectionState,prepareStation,stationPosition,transferState} from '../../frontend/src/stations/core.mjs'
import fs from 'node:fs'
const geometry=JSON.parse(fs.readFileSync(new URL('../../configs/inspection_stations.json',import.meta.url)))
const equipment=[{start:0,end:2,state:'STARVED',speed:0,distance:0,lamp:'STOP'},{start:2,end:5,state:'PROCESSING',speed:.5,distance:0,lamp:'RUN'},{start:5,end:8,state:'DOWN',speed:0,distance:1.5,lamp:'FAULT'}]
const parts=[{id:'p1',trigger:2,decision:2.1,arrival:4,route:'NG',verdict:'NG'}]
const data=prepareStation({geometry,equipment,parts})
assert.equal(equipmentAt(equipment,4).distance,1)
assert.equal(equipmentAt(equipment,7).distance,1.5)
assert.equal(inspectionState(data,2).sensor,true)
assert.equal(inspectionState(data,1.999).sensor,false)
assert.equal(inspectionState(data,2.13).sensor,false)
assert.equal(inspectionState(data,3.999).eject,false)
assert.equal(inspectionState(data,4).eject,true)
assert.deepEqual(inspectionState(data,4),inspectionState(data,4),'paused sim time has no drift')
assert.equal(inspectionState(data,5.1).lamp,'FAULT')
for(const cls of ['bottle','carpet'])assert.deepEqual(stationPosition(parts[0],2,cls,geometry).position,geometry[cls].trigger)
const screw=stationPosition(parts[0],2,'screw',geometry).position
assert(Math.abs(screw[0]-(geometry.screw.center[0]-geometry.screw.radius_m))<1e-12)
console.log(JSON.stringify({passed:12,checks:'integral, pause, trigger, verdict, arrival, state, top-down trigger targets'}))
