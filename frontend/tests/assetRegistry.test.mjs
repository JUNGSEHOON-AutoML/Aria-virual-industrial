import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import {AssetRegistry,fenceBoxes,palletBoxes,canonicalInstanceId} from '../src/features/twin/assets/registry.mjs'
const entries=JSON.parse(fs.readFileSync(new URL('../../config/assets/registry.json',import.meta.url)))
test('asset bindings validate metadata and unknown IDs',()=>{const r=new AssetRegistry(entries);assert.equal(r.resolve('aria.fence').unit,'m');assert.throws(()=>r.resolve('missing'));assert.throws(()=>new AssetRegistry([{asset_id:'bad'}]));assert.throws(()=>new AssetRegistry([...entries,entries[0]]))})
test('registered fallback resolves and unknown fallback is rejected',()=>{const a={...entries[0],asset_id:'glb-test',format:'glb',fallback:'aria.pallet'};assert.equal(new AssetRegistry([...entries,a]).fallback('glb-test').asset_id,'aria.pallet');assert.throws(()=>new AssetRegistry([{...a,fallback:'missing'}]))})
test('instance selections retain canonical engineering identity',()=>{for(let i=0;i<33;i++)assert.equal(canonicalInstanceId({componentId:'MACHINE-01',count:33},i),'MACHINE-01');assert.throws(()=>canonicalInstanceId({componentId:'M',count:2},2))})
test('instancing keeps original fence and pallet primitive dimensions',()=>{assert.equal(fenceBoxes(3).length,32);assert.equal(fenceBoxes(2.1).length,26);assert.equal(palletBoxes(false).length,8);assert.equal(palletBoxes(true).length,18);assert.deepEqual(fenceBoxes(3)[0],{position:[-1.5,1,0],size:[.07,2,.07],color:'#dba31c'});assert.equal(palletBoxes(true).filter(r=>r.size[1]===.32).length,8)})
