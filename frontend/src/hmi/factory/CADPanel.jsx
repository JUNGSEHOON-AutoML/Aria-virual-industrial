import { useEffect,useState } from 'react'
import { factoryApi,useFactory } from './factoryStore'
export default function CADPanel({ component }) {
 const [dimensions,setDimensions]=useState({width_mm:2500,depth_mm:1900,height_mm:2600})
 const [asset,setAsset]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[available,setAvailable]=useState(null)
 useEffect(()=>{let live=true;setAsset(null);setError('');factoryApi('/cad/status').then(s=>{if(live)setAvailable(s.available)}).catch(e=>{if(live)setError(e.message)})
  if(component.cad_asset)factoryApi(`/cad/assets/${component.cad_asset}`).then(a=>{if(live){setAsset(a);setDimensions(a.report.parameters)}}).catch(e=>{if(live)setError(e.message)})
  return()=>{live=false}
 },[component.id,component.cad_asset])
 const build=async()=>{setBusy(true);setError('');try{
  const r=await factoryApi('/cad/build',{component:component.id,parameters:dimensions});setAsset(r.asset);useFactory.setState({proposal:r.proposal})
 }catch(e){setError(e.message)}finally{setBusy(false)}}
 return <section className="cad-panel"><h4>FREECAD · CNC BODY</h4><small>{available===null?'Checking CAD runtime…':available?'FreeCAD ready':'FreeCAD runtime unavailable'}</small>
  {Object.entries(dimensions).map(([k,v])=><label key={k}>{k.replace('_mm','')} (mm)<input aria-label={`CAD ${k}`} type="number" step="50" value={v} onChange={e=>setDimensions({...dimensions,[k]:Number(e.target.value)})}/></label>)}
  <button disabled={busy||!available} onClick={build}>{busy?'Generating CAD…':'Generate CAD & review'}</button>
  {error&&<p role="alert">{error}</p>}
  {asset&&<><small>{component.cad_asset===asset.id?'APPLIED':'PREVIEW · approval pending'}<br/>{asset.report.parts} solids · {asset.report.triangles} triangles<br/>Valid: {String(asset.report.all_solids_valid)} · Static overlaps: {asset.report.static_interferences.length}</small><div>{['cnc.FCStd','cnc.step','report.json'].map(n=><a key={n} href={asset.files[n]} download style={{display:'block'}}>{n} ↓</a>)}</div></>}
  <small>CNC 본체만 생성합니다. 공정 시간과 로봇 동작은 별도로 설정하며, 로봇 경로 안전성 검증은 포함하지 않습니다.</small>
 </section>
}
