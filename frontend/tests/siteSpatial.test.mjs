import test from 'node:test'
import assert from 'node:assert/strict'
import {ancestry,siteAnchor,needsProductionDetail} from '../src/features/site/spatial.js'
const d={sites:[{id:'SITE',position:[0,0,0]}],zones:[{id:'ZONE',parent_id:'SITE'}],buildings:[{id:'PRODUCTION-01',parent_id:'ZONE'}],assets:[{id:'CELL',parent_id:'PRODUCTION-01'},{id:'MACHINE',parent_id:'CELL',position:[26,0,-24]}]}
test('hierarchy is canonical and preserves all five drill-down levels',()=>assert.deepEqual(ancestry(d,'MACHINE').map(n=>n.id),['SITE','ZONE','PRODUCTION-01','CELL','MACHINE']))
test('vehicle and shipment camera focus comes from actual runtime pose',()=>{const r={trucks:[{id:'T',position:[1,0,2]}],shipments:[{id:'S',pallet_id:'P'}],pallets:[{id:'P',position:[5,0,6]}]};assert.deepEqual(siteAnchor(d,r,'T'),[1,0,2]);assert.deepEqual(siteAnchor(d,r,'S'),[5,0,6]);assert.equal(siteAnchor(d,r,'missing'),null)})
test('heavy cell detail is absent at site scope and enabled at production/asset scope',()=>{assert.equal(needsProductionDetail(d,null,'SITE_OVERVIEW'),false);assert.equal(needsProductionDetail(d,'MACHINE',null),true);assert.equal(needsProductionDetail(d,null,'QUALITY_CELL'),true)})
