import assert from 'node:assert/strict'
import {positionAt,activeAt} from '../../frontend/src/cnotta/replay.js'
const p={part_id:'p',born:0,inspection_time:10,exit_time:10,entries:[{time:0,component:'BUFFER'},{time:5,component:'AI-INSPECTION'}]}
assert.notDeepEqual(positionAt(p,1,true),positionAt(p,2,true),'waiting interval visibly advances')
assert.notDeepEqual(positionAt(p,6,true),positionAt(p,7,true),'processing interval visibly advances')
assert.deepEqual(positionAt(p,6,false),positionAt(p,7,false),'recorded station mode unchanged')
assert.deepEqual(positionAt(p,6,true),positionAt(p,6,true),'pause deterministic')
assert.equal(activeAt([p],10).length,0,'no invented exit interval')
assert.equal(activeAt([p],9.999).length,1)
const zero={...p,inspection_time:5,exit_time:5}
assert(positionAt(zero,5,true).every(Number.isFinite),'instantaneous transitions stay finite')
console.log('7 motion assertions passed')
