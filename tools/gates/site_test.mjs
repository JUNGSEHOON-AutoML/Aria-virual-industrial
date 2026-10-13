import {build} from '../../frontend/node_modules/esbuild/lib/main.js'
import assert from 'node:assert/strict'
import {writeFile,mkdir} from 'node:fs/promises'
const destination=new URL('../../frontend/node_modules/.cache/cnotta-site-test.mjs',import.meta.url)
await mkdir(new URL('.',destination),{recursive:true})
const {outputFiles}=await build({entryPoints:[new URL('../../frontend/src/cnotta/Site.jsx',import.meta.url).pathname],bundle:true,write:false,format:'esm',platform:'node',jsx:'automatic',external:['react/jsx-runtime']})
await writeFile(destination,outputFiles[0].text)
const {Site}=await import(destination.href)
const lanes=['coreset','ccifps','random_same_k'];let received
const g=Site({origin:[48,40],rotation:Math.PI/2,lanes,children:xs=>{received=xs;return 'local geometry'}})
assert.deepEqual(g.props.position,[48,0,40]);assert.deepEqual(g.props.rotation,[0,Math.PI/2,0]);assert.equal(received,lanes);assert.equal(g.props.userData.lanes,lanes)
const base=Site({children:'one hall'});assert.deepEqual(base.props.position,[0,0,0]);assert.deepEqual(base.props.rotation,[0,0,0]);assert.equal(base.props.children,'one hall')
console.log(JSON.stringify({pass:true,checks:7,origin:g.props.position,rotation:g.props.rotation,lanes,scope:'M1 Site interface only; M7 multi-lane assembly pending'}))
