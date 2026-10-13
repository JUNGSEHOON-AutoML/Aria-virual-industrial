import React from 'react'
import {Boxes} from './Geometry'
import {laneZ} from './layout'
import T from '../brand/cnotta.tokens.json'
// Only the selected hall loads these local furnishings. Process evidence is unchanged.
export default function Interior({site}){return <group name="lazy-hall-interior">{site.lanes.map((model,i)=><group key={model} position={[0,0,laneZ(site,i)]}><Boxes color={T.equip} items={[[[12.5,.85,-1.5],[3,.1,1]],[[11.2,.4,-1.5],[.12,.8,.85]],[[13.8,.4,-1.5],[.12,.8,.85]],[[12.5,1.2,-1.75],[.6,.5,.1]]]}/><Boxes color={T.human} items={[[[12.5,1,-.4],[.4,.6,.25]]]}/><Boxes color={T['text-2']} items={[[[12.4,.38,-.4],[.12,.7,.12]],[[12.6,.38,-.4],[.12,.7,.12]],[[12.5,1.5,-.4],[.23,.23,.23]]]}/></group>)}</group>}
