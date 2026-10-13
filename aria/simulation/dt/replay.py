"""Control inputs contain predictions only. Ground truth is joined by evaluation.py."""
import csv,math,random,statistics,time
from pathlib import Path
from ..des.engine import Engine

FIELDS=('image_id','image_sha256','bundle_id','selector','bank_k','score','threshold','verdict')

class ReplayCatalog:
    def __init__(self,path,seed,*,schedule=None):
        with Path(path).open() as f:
            self.rows=[{k:r[k] for k in FIELDS} for r in csv.DictReader(f)]
        if not self.rows or len({r['image_id'] for r in self.rows})!=len(self.rows):raise ValueError('Nonempty unique prediction IDs required')
        for r in self.rows:
            r['score']=float(r['score']);r['threshold']=float(r['threshold']);r['bank_k']=int(r['bank_k'])
            if not all(math.isfinite(r[k]) for k in ('score','threshold')):raise ValueError('Nonfinite prediction')
            if r['verdict']!=('NG' if r['score']>r['threshold'] else 'OK'):raise ValueError('Prediction and threshold disagree')
        self.by_id={r['image_id']:r for r in self.rows}
        self.schedule=schedule
        if schedule is not None and (not schedule or any(i not in self.by_id for i in schedule)):raise ValueError('Invalid source image schedule')
        self.order=list(range(len(self.rows)));random.Random(seed).shuffle(self.order)
    def row(self,serial):
        if self.schedule is not None:
            if not 1<=serial<=len(self.schedule):raise ValueError('Source schedule exhausted')
            return self.by_id[self.schedule[serial-1]]
        return self.rows[self.order[(serial-1)%len(self.order)]]

class MedianSampler:
    """Counterfactual constant median, explicitly derived from measured samples."""
    def __init__(self,sampler):self.sampler=sampler
    def reset(self):self.sampler.reset()
    def sample(self):
        r=self.sampler.sample();p=self.sampler.profile
        r['latency_ms']={'total':statistics.median(p.total_ms),**{k:statistics.median(v) for k,v in p.stages_ms.items()}}
        r['profile_sample_index']=None;r['sampling_policy']='constant_median';return r

class ReplayEngine(Engine):
    def __init__(self,model,catalog,*,event_sink=None,constant_median=False,oracle=None):
        self.catalog=catalog;self.part_metadata={};self.dt_sequence=0;self.output=event_sink;self.oracle=oracle
        if any(c.id=='REINSPECTION' for c in model.components):
            if oracle is None:raise ValueError('Policy B requires reinspect_oracle')
            oracle.validate_images([r['image_id'] for r in catalog.rows])
        super().__init__(model,inspect=self.inspect_replay,event_sink=None)
        if constant_median:self.latency_samplers={k:MedianSampler(v) for k,v in self.latency_samplers.items()}
    def reset(self):
        self.part_metadata={};self.dt_sequence=0
        super().reset()
        if self.offline_buffer is not None:self.nodes[self.offline_buffer]['states'].setdefault('WAITING',0.)
    @property
    def offline_buffer(self):
        config=self.model.layout.get('offline_reinspection')
        return config['buffer'] if config and config.get('capacity')=='unbounded' else None
    def _slot_counts(self,node):
        if node['c'].id==self.offline_buffer:return (0,len(node['jobs']))
        return super()._slot_counts(node)
    def _transfer_jobs(self,node):
        if node['c'].id==self.offline_buffer:return node['jobs'][:1]
        return super()._transfer_jobs(node)
    def _has_capacity(self,node):
        if node['c'].id==self.offline_buffer:return True
        return super()._has_capacity(node)
    def _state(self,node):
        if node['c'].id==self.offline_buffer:
            node['states'].setdefault('WAITING',0.)
            return 'WAITING' if node['jobs'] else 'IDLE'
        return super()._state(node)
    def metrics(self):
        result=super().metrics()
        if self.offline_buffer:
            r=result['resources'][self.offline_buffer]
            r.update(capacity=None,capacity_mode='unbounded',offline=True,blocks_main_line=False,waiting_slot_time=r['blocked_slot_time'],blocked_slot_time=0.)
        return result
    def _admit(self,n,part,previous=None):
        if n['c'].kind=='Source':
            row=self.catalog.row(part['serial'])
            self.part_metadata[part['id']]={'image_id':row['image_id'],'image_sha256':row['image_sha256'],'born':part['born']}
            part.update(image_id=row['image_id'])
        return super()._admit(n,part,previous)
    def inspect_replay(self,component,part):
        row=self.catalog.row(part['serial'])
        if component.id=='REINSPECTION':
            return dict(image_id=row['image_id'],image_sha256=row['image_sha256'],
                        **self.oracle.inspect(image_id=row['image_id'],part_id=part['id']))
        return dict(row,mode='replay',source='ai_replay',inspection_source='saved_prediction')
    def emit(self,kind,**payload):
        super().emit(kind,**payload)
        if self.output:
            self.dt_sequence+=1
            e=dict(self.history[-1],**self.part_metadata.get(payload.get('part'),{}))
            e.update(event_seq=self.dt_sequence,sim_time=round(self.now,6),wall_ns=time.monotonic_ns(),sim=1,run_id=self.run_token)
            if payload.get('part') is not None:e['part_id']=payload['part']
            self.output(e)
