import hashlib
import json
from datetime import datetime, timezone
from typing import Protocol

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def utcnow():return datetime.now(timezone.utc).isoformat()

class PersistenceFault(RuntimeError):pass

class EventStore(Protocol):
    def append(self,events,contexts): ...
    def read(self,run_id,after=0,limit=1000): ...
    def close(self): ...

class SpatialRepository(Protocol):
    def get_site(self): ...
    def get_assets_in_zone(self,zone_id): ...
    def get_nearby_assets(self,position,radius): ...

def envelope(event,context):
    asset=event.get('component');entities={e['id']:e for section in ('sites','zones','buildings','assets','roads','transport_nodes','docks','staging_areas') for e in context['definition'][section]}
    zone=None;node=entities.get(asset)
    while node:
        if node['kind']=='zone':zone=node['id'];break
        node=entities.get(node.get('parent_id'))
    result=dict(event_id=event['id'],run_id=context['run_id'],twin_revision=context['twin_revision'],site_definition_hash=context['site_definition_hash'],sequence=event['sequence'],simulation_time=event['time'],wall_time=utcnow(),site_id=context['site_id'],zone_id=zone,asset_id=asset,shipment_id=event.get('shipment_id'),workpiece_id=event.get('part'),event_type=event['type'],severity='error' if 'error' in event['type'] else 'warning' if event['type']=='shipment_on_hold' or event.get('state') in ('DOWN','MAINTENANCE') or event.get('event')=='failure' else 'info',payload=event,correlation_id=event.get('shipment_id') or event.get('part'),causation_id=event.get('causation_id'))
    result['content_hash']=digest(result)
    return result
