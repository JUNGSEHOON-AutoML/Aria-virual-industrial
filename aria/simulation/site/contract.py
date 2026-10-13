"""Static canonical demo contract. Metres / seconds / radians, web Y-up.

This site is synthetic, not a measured representation of a real factory.
No runtime trucks, shipments, or pallets are persisted in this definition.
"""
from typing import Literal
from pydantic import Field, model_validator
from ..des.model import Contract, FactoryModel

class SpatialEntity(Contract):
    id: str
    kind: str
    parent_id: str | None = None
    position: tuple[float,float,float]
    size: tuple[float,float,float] = (1,1,1)
    label: str = ''

class TransportEdge(Contract):
    id: str
    source: str
    target: str
    modes: list[Literal['truck','forklift']]
    bidirectional: bool = True

class SiteDefinition(Contract):
    schema_version: str = 'aria.site.v1'
    synthetic: Literal[True] = True
    units: str = 'metres, seconds, radians; Y up'
    sites: list[SpatialEntity]
    zones: list[SpatialEntity]
    buildings: list[SpatialEntity]
    assets: list[SpatialEntity]
    roads: list[SpatialEntity]
    transport_nodes: list[SpatialEntity]
    transport_edges: list[TransportEdge]
    docks: list[SpatialEntity]
    staging_areas: list[SpatialEntity]
    vehicle_types: list[dict]
    workpiece_types: list[dict]
    shipment_types: list[dict]
    visualization_assets: list[dict]
    process_connections: list[dict]
    logistics_connections: list[dict]
    production_origin: tuple[float,float,float]
    source_component: str | None
    cameras: dict[str,dict]

    @model_validator(mode='after')
    def validate_references(self):
        entities=self.sites+self.zones+self.buildings+self.assets+self.roads+self.transport_nodes+self.docks+self.staging_areas
        ids=[e.id for e in entities]
        if len(ids)!=len(set(ids)):raise ValueError('Canonical spatial IDs must be unique')
        if len(self.sites)!=1:raise ValueError('This demo supports one site')
        known=set(ids);nodes={n.id for n in self.transport_nodes}
        for e in entities:
            if e.parent_id and e.parent_id not in known:raise ValueError('Unknown parent: '+e.parent_id)
        parents={e.id:e.parent_id for e in entities}
        for key in parents:
            seen=set();p=key
            while p:
                if p in seen:raise ValueError('Spatial hierarchy cycle')
                seen.add(p);p=parents[p]
        for e in self.transport_edges:
            if e.source not in nodes or e.target not in nodes or e.source==e.target:raise ValueError('Unknown/invalid transport edge')
        if self.source_component and self.source_component not in known:raise ValueError('Unknown production binding')
        for link in self.logistics_connections+self.process_connections:
            if link['source'] not in known or link['target'] not in known:raise ValueError('Unknown canonical graph endpoint')
        return self

def build_site(model: FactoryModel):
    def ent(id,kind,pos,size=(1,1,1),parent='SITE-DEMO-01',label=''):
        return dict(id=id,kind=kind,position=pos,size=size,parent_id=parent,label=label or id)
    origin=(26,0,-24)
    components=model.components
    xs=[c.position[0]+origin[0] for c in components];zs=[c.position[2]+origin[2] for c in components]
    prod_center=((min(xs)+max(xs))/2,0,(min(zs)+max(zs))/2)
    prod_size=(max(32,max(xs)-min(xs)+10),8,max(28,max(zs)-min(zs)+12))
    nodes={'GATE-01':(-59,0,16),'ROAD-N01':(-46,0,16),'YARD-WAIT-01':(-46,0,5),'ROAD-N02':(-8,0,16),'ROAD-N03':(44,0,16),'EXIT-01':(64,0,16),'DOCK-A01-N':(-32,0,-4),'DOCK-A02-N':(-20,0,-4),'DOCK-B01-N':(44,0,-4),'STAGING-IN-01-N':(-10,0,-12),'PRODUCTION-IN-01-N':(11,0,-24),'FG-01-N':(39,0,-19),'STAGING-OUT-01-N':(47,0,-12),'FORK-HOME-N':(-8,0,-4),'FORK-JUNCTION-N':(4,0,-12),'FORK-EAST-N':(40,0,-12)}
    pairs=[('GATE-01','ROAD-N01','truck'),('ROAD-N01','YARD-WAIT-01','truck'),('YARD-WAIT-01','ROAD-N02','truck'),('ROAD-N01','ROAD-N02','truck'),('ROAD-N02','ROAD-N03','truck'),('ROAD-N03','EXIT-01','truck'),('ROAD-N02','DOCK-A01-N','truck'),('ROAD-N02','DOCK-A02-N','truck'),('ROAD-N03','DOCK-B01-N','truck'),('DOCK-A01-N','STAGING-IN-01-N','forklift'),('DOCK-A02-N','STAGING-IN-01-N','forklift'),('STAGING-IN-01-N','FORK-HOME-N','forklift'),('FORK-HOME-N','FORK-JUNCTION-N','forklift'),('FORK-JUNCTION-N','PRODUCTION-IN-01-N','forklift'),('FORK-JUNCTION-N','FORK-EAST-N','forklift'),('FG-01-N','FORK-EAST-N','forklift'),('FORK-EAST-N','STAGING-OUT-01-N','forklift'),('STAGING-OUT-01-N','DOCK-B01-N','forklift')]
    zones=[ent('ZONE-INBOUND','zone',(-39,0,1),(30,.1,23),label='Inbound yard'),ent('ZONE-PRODUCTION','zone',prod_center,prod_size,label='Production'),ent('ZONE-OUTBOUND','zone',(46,0,0),(23,.1,25),label='Outbound yard')]
    buildings=[ent('WAREHOUSE-01','warehouse',(-26,0,-24),(36,8,28),label='Warehouse'),ent('PRODUCTION-01','production',prod_center,prod_size,'ZONE-PRODUCTION',label='Production building')]
    assets=[ent('CELL-01','cell',prod_center,(28,4,15),'PRODUCTION-01','Production cell')]+[ent(c.id,c.kind,(c.position[0]+origin[0],c.position[1],c.position[2]+origin[2]),parent='CELL-01',label=c.name or c.id) for c in components]
    docks=[ent('DOCK-A01','inbound_dock',nodes['DOCK-A01-N'],(5,.12,10),'ZONE-INBOUND'),ent('DOCK-A02','inbound_dock',nodes['DOCK-A02-N'],(5,.12,10),'ZONE-INBOUND'),ent('DOCK-B01','outbound_dock',nodes['DOCK-B01-N'],(5,.12,10),'ZONE-OUTBOUND')]
    staging=[ent('STAGING-IN-01','inbound_staging',nodes['STAGING-IN-01-N'],(8,.12,7),'WAREHOUSE-01'),ent('FG-01','finished_goods',nodes['FG-01-N'],(7,.12,7),'PRODUCTION-01'),ent('STAGING-OUT-01','outbound_staging',nodes['STAGING-OUT-01-N'],(7,.12,7),'ZONE-OUTBOUND'),ent('REJECT-HOLD-01','reject_hold',(39,0,-29),(6,.12,5),'PRODUCTION-01')]
    def cam(target,distance):return {'target':target,'distance':distance}
    source=next((c.id for c in components if c.id=='SOURCE' and c.kind=='Source'),next((c.id for c in components if c.kind=='Source'),None))
    quality=next((a.position for a in [SpatialEntity(**e) for e in assets] if a.kind=='Inspection'),prod_center)
    return SiteDefinition(sites=[ent('SITE-DEMO-01','site',(0,0,-8),(138,.2,84),None,'ARIA Demo Campus')],zones=zones,buildings=buildings,assets=assets,roads=[ent('ROAD-MAIN','road',(0,0,16),(132,.05,8))],transport_nodes=[ent(k,'transport_node',v) for k,v in nodes.items()],transport_edges=[dict(id=f'EDGE-{i:02}',source=a,target=b,modes=[m]) for i,(a,b,m) in enumerate(pairs)],docks=docks,staging_areas=staging,vehicle_types=[dict(id='truck',speed_mps=6),dict(id='forklift',speed_mps=3)],workpiece_types=[dict(id='demo-part')],shipment_types=[dict(id='demo-batch',parts_per_pallet=3,max_shipments=3)],visualization_assets=[dict(id='campus-procedural',source='generated synthetic geometry',lod='site shells / lazy cell detail')],process_connections=[e.model_dump() for e in model.connections],logistics_connections=([dict(source='PRODUCTION-IN-01-N',target=source,relation='external_material_admission')] if source else [])+[dict(source=e.target,target='FG-01' if e.condition=='OK' else 'REJECT-HOLD-01',relation='actual_'+e.condition+'_exit') for e in model.connections if e.condition in ('OK','NG','SKIPPED') and any(c.id==e.target and c.kind=='Sink' for c in components)],production_origin=origin,source_component=source,cameras={'SITE_OVERVIEW':cam((0,0,-8),136),'INBOUND_YARD':cam((-33,0,1),55),'WAREHOUSE':cam((-26,2,-24),64),'PRODUCTION':cam(prod_center,53),'QUALITY_CELL':cam(quality,14),'OUTBOUND_YARD':cam((44,0,-5),48)})
