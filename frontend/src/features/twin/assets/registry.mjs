export class AssetRegistry {
 constructor(entries){this.entries=new Map();for(const a of entries){
  for(const k of ['asset_id','uri','format','version','hash','unit','up_axis','origin','bounds','provenance','license','lod_policy','instancing_policy','fallback'])if(!(k in a))throw Error(`Missing asset metadata ${k}`)
  if(this.entries.has(a.asset_id)||!['procedural','cad','urdf','glb','gltf'].includes(a.format)||!['m','mm','cm'].includes(a.unit)||!['Y','Z'].includes(a.up_axis))throw Error('Invalid asset binding '+a.asset_id)
  this.entries.set(a.asset_id,Object.freeze(a))
 }
 for(const a of entries){const seen=new Set();let current=a;while(current?.fallback){if(seen.has(current.asset_id))throw Error('Cyclic asset fallback');seen.add(current.asset_id);current=this.entries.get(current.fallback);if(!current)throw Error('Unknown fallback')}}
 }
 resolve(id){const a=this.entries.get(id);if(!a)throw Error('Unknown visual_asset_id: '+id);return a}
 fallback(id){const a=this.resolve(id);return a.fallback?this.resolve(a.fallback):null}
}
export function canonicalInstanceId(binding,index){if(!binding.componentId||!Number.isInteger(index)||index<0||index>=binding.count)throw Error('Invalid instance identity');return binding.componentId}
export function fenceBoxes(length){
 const rows=[],n=Math.max(1,Math.ceil(length/1.2)),add=(position,size,color)=>rows.push({position,size,color})
 for(let i=0;i<=n;i++)add([i*length/n-length/2,1,0],[.07,2,.07],'#dba31c')
 for(const y of [.15,1.9])add([0,y,0],[length,.055,.055],'#dba31c')
 for(let i=0;i<Math.ceil(length/.18);i++)add([-length/2+i*.18,1,0],[.012,1.65,.014],'#424c4d')
 for(let i=0;i<9;i++)add([0,.3+i*.18,0],[length,.012,.014],'#424c4d')
 return rows
}
export function palletBoxes(totes){
 const rows=[],add=(position,size,color)=>rows.push({position,size,color})
 for(const z of [-.5,0,.5])add([0,.09,z],[1.2,.18,.13],'#8a7150')
 for(const x of [-.48,-.24,0,.24,.48])add([x,.23,0],[.2,.1,1.2],'#b49a70')
 if(totes)for(const level of [0,1]){const y=.3+level*.32;add([0,y+.05,0],[1.05,.1,1.05],'#728d9b');for(const z of [-.51,.51])add([0,y+.16,z],[1.05,.32,.04],'#829da9');for(const x of [-.51,.51])add([x,y+.16,0],[.04,.32,1.05],'#829da9')}
 return rows
}
