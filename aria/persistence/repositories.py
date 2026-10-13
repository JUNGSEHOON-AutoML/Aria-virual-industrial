"""No connection is made at module import; memory mode is explicit and volatile."""
import copy
import math
import threading
from pathlib import Path
from .contracts import digest,PersistenceFault
SECTIONS=('sites','zones','buildings','assets','roads','transport_nodes','docks','staging_areas')

def planar(position):
    if len(position)!=3 or not all(math.isfinite(float(x)) for x in position):raise ValueError('Expected finite metre x,y,z')
    return (float(position[0]),float(position[2])),float(position[1])

class InMemoryEventStore:
    mode='memory'
    def __init__(self):self.rows={};self.contexts={};self.lock=threading.RLock()
    def append(self,events,contexts):
        with self.lock:
            for e in events:
                old=self.rows.get((e['run_id'],e['sequence']))
                if old and old['content_hash']!=e['content_hash']:raise PersistenceFault('Event identity collision')
            self.contexts.update(copy.deepcopy(contexts))
            for e in events:self.rows[(e['run_id'],e['sequence'])]=copy.deepcopy(e)
    def read(self,run_id,after=0,limit=1000):
        with self.lock:return copy.deepcopy(sorted([e for (r,s),e in self.rows.items() if r==run_id and s>after],key=lambda e:e['sequence'])[:limit])
    def close(self):pass

class MemorySpatialRepository:
    def __init__(self,definition):self.definition=copy.deepcopy(definition);self.entities={e['id']:e for k in SECTIONS for e in definition[k]}
    def section(self,k):return copy.deepcopy(self.definition[k])
    def get_site(self):return self.section('sites')[0]
    def get_zone(self,id):return next((e for e in self.section('zones') if e['id']==id),None)
    def get_assets_in_zone(self,id):
        result=[]
        for e in self.definition['assets']:
            node=e
            while node:
                if node['id']==id:result.append(copy.deepcopy(e));break
                node=self.entities.get(node.get('parent_id'))
        return result
    def get_nearby_assets(self,position,radius):
        xy,_=planar(position)
        if not math.isfinite(radius) or radius<0:raise ValueError('Invalid radius')
        return [dict(e,distance_m=math.dist(xy,planar(e['position'])[0]),distance_kind='horizontal') for e in self.section('assets') if math.dist(xy,planar(e['position'])[0])<=radius]
    def get_transport_nodes(self):return self.section('transport_nodes')
    def get_transport_edges(self):return self.section('transport_edges')
    def get_docks(self):return self.section('docks')
    def get_staging_areas(self):return self.section('staging_areas')

class PostgresEventStore:
    mode='postgres'
    def __init__(self,dsn,spatial=True):self.dsn=dsn;self.spatial=spatial
    def connect(self):
        import psycopg
        return psycopg.connect(self.dsn,connect_timeout=2,options='-c statement_timeout=5000')
    def migrate(self,spatial=True):
        root=Path(__file__).resolve().parents[2]
        with self.connect() as c:
            c.execute((root/'migrations/001_history.sql').read_text())
            if spatial:c.execute((root/'migrations/002_spatial.sql').read_text())
    def append(self,events,contexts):
        from psycopg.types.json import Jsonb
        with self.connect() as c:
            for ctx in contexts.values():
                key=(ctx['site_id'],ctx['twin_revision'],ctx['site_definition_hash'])
                inserted=c.execute('INSERT INTO aria_twin_revisions(site_id,twin_revision,site_definition_hash,definition,model) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING site_id',(*key,Jsonb(ctx['definition']),Jsonb(ctx['model']))).fetchone()
                existing=c.execute('SELECT definition,model FROM aria_twin_revisions WHERE site_id=%s AND twin_revision=%s AND site_definition_hash=%s',key).fetchone()
                if digest(existing[0])!=digest(ctx['definition']) or digest({k:v for k,v in existing[1].items() if k!='seed'})!=digest({k:v for k,v in ctx['model'].items() if k!='seed'}):raise PersistenceFault('Static revision reused for a different model')
                if inserted and self.spatial:self._spatial(c,ctx)
                c.execute('INSERT INTO aria_runs VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(ctx['run_id'],*key,ctx['seed'],ctx['started_at']))
            for e in events:
                ctx=contexts[e['run_id']]
                if any(e[k]!=ctx[k] for k in ('site_id','twin_revision','site_definition_hash')):raise PersistenceFault('Event revision mismatch')
                cols=list(e);values=[Jsonb(e[k]) if k=='payload' else e[k] for k in cols]
                c.execute('INSERT INTO aria_events('+','.join(cols)+') VALUES('+','.join(['%s']*len(cols))+') ON CONFLICT DO NOTHING',values)
                old=c.execute('SELECT content_hash FROM aria_events WHERE run_id=%s AND sequence=%s',(e['run_id'],e['sequence'])).fetchone()
                if not old or old[0]!=e['content_hash']:raise PersistenceFault('Event identity collision')
    def _spatial(self,c,ctx):
        from psycopg.types.json import Jsonb
        d=ctx['definition'];key=(ctx['site_id'],ctx['twin_revision'],ctx['site_definition_hash'])
        for section in SECTIONS:
            for e in d[section]:
                (x,z),y=planar(e['position'])
                c.execute('INSERT INTO aria_spatial_entities VALUES(%s,%s,%s,%s,%s,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s),0),%s,%s) ON CONFLICT DO NOTHING',(*key,e['id'],section,e['kind'],e.get('parent_id'),x,z,y,Jsonb(e)))
        nodes={n['id']:n for n in d['transport_nodes']}
        for e in d['transport_edges']:
            a,_=planar(nodes[e['source']]['position']);b,_=planar(nodes[e['target']]['position'])
            c.execute('INSERT INTO aria_spatial_entities VALUES(%s,%s,%s,%s,%s,%s,NULL,ST_MakeLine(ST_MakePoint(%s,%s),ST_MakePoint(%s,%s)),0,%s) ON CONFLICT DO NOTHING',(*key,e['id'],'transport_edges','transport_edge',*a,*b,Jsonb(e)))
    def read(self,run_id,after=0,limit=1000):
        from psycopg.rows import dict_row
        with self.connect() as c:
            c.row_factory=dict_row
            rows=c.execute('SELECT * FROM aria_events WHERE run_id=%s AND sequence>%s ORDER BY sequence LIMIT %s',(run_id,after,limit)).fetchall()
            for e in rows:e['wall_time']=e['wall_time'].isoformat()
            return rows
    def close(self):pass

class PostgresSpatialRepository(MemorySpatialRepository):
    def __init__(self,store,site_id,revision,definition_hash):
        self.store=store;self.key=(site_id,revision,definition_hash)
        with store.connect() as c:
            row=c.execute('SELECT definition FROM aria_twin_revisions WHERE site_id=%s AND twin_revision=%s AND site_definition_hash=%s',self.key).fetchone()
        if not row:raise KeyError('Unknown static revision')
        super().__init__(row[0])
    def get_nearby_assets(self,position,radius):
        xy,_=planar(position)
        if not math.isfinite(radius) or radius<0:raise ValueError('Invalid radius')
        with self.store.connect() as c:
            rows=c.execute("SELECT metadata,ST_Distance(geom,ST_MakePoint(%s,%s)) FROM aria_spatial_entities WHERE site_id=%s AND twin_revision=%s AND site_definition_hash=%s AND section='assets' AND ST_DWithin(geom,ST_MakePoint(%s,%s),%s) ORDER BY entity_id",(*xy,*self.key,*xy,radius)).fetchall()
        return [dict(e,distance_m=float(distance),distance_kind='horizontal') for e,distance in rows]
