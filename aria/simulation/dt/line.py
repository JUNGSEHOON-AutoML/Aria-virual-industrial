"""Tagged engineering assumptions. No optimization based on model outcomes."""
import math,json,hashlib
from pathlib import Path
import yaml
from ..des.model import Component,Connection,FactoryModel,Simulation

UNITS={'pitch_m':'m','sensor_distance_m':'m','actuator_s':'s','reinspection_s':'s','mtbf_s':'s','mttr_s':'s','buffer_capacity':'parts','handling_s':'s','defect_rate':'probability'}

def load_profile(path):
    data=yaml.safe_load(Path(path).read_text());out={}
    if set(data['parameters'])!=set(UNITS):raise ValueError('Missing or extra line parameters')
    for name,row in data['parameters'].items():
        if row.get('source') not in ('datasheet','measured','assumed','cad'):raise ValueError('Missing source tag')
        if row.get('unit')!=UNITS[name] or not row.get('reference'):raise ValueError('Unit/reference required')
        v=row['value']
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0:raise ValueError('Invalid parameter')
        if row['source']=='cad':
            binding=row.get('cad_binding',{});root=Path(__file__).resolve().parents[3]
            path=(root/binding.get('path','')).resolve()
            if not path.is_relative_to(root/'assets/cad') or not path.is_file():raise ValueError('Invalid CAD binding')
            if hashlib.sha256(path.read_bytes()).hexdigest()!=binding.get('sha256'):raise ValueError('CAD metadata hash mismatch')
            dims=json.loads(path.read_text())
            if dims['unit']!='mm' or row['unit']!='m':raise ValueError('CAD conversion requires mm to m')
            for file,h in dims['files'].items():
                artifact=path.parent/file
                if not artifact.resolve().is_relative_to(path.parent) or hashlib.sha256(artifact.read_bytes()).hexdigest()!=h:raise ValueError('CAD asset hash mismatch')
            if abs(v-dims[binding['field']]/1000)>1e-9:raise ValueError('CAD value disagrees with line profile')
        if name=='defect_rate' and (v>1 or row['source']!='assumed'):raise ValueError('defect_rate must be assumed probability')
        out[name]=v
    for row in data.get('human_reinspection',{}).values():
        if row.get('source')!='assumed' or not row.get('reference'):raise ValueError('Human model must be tagged assumed')
    return out,data

def make_line(parameters,profile_path,profile_sha,*,seed,cell,speed,policy='A',reinspection_s=30):
    p=parameters
    if policy not in ('A','B'):raise ValueError('Unknown inspection policy')
    if cell not in ('inline','robot') or speed<=0:raise ValueError('Unknown cell or speed')
    deadline=p['sensor_distance_m']/speed-p['actuator_s']
    if deadline<=0:raise ValueError('Nonpositive sorting deadline')
    common=dict(inspection_mode='ccifps',latency_mode='profile',latency_profile=profile_path,latency_profile_sha256=profile_sha)
    items=[Component(id='SOURCE',kind='Source',capacity=1,interarrival=p['pitch_m']/speed,position=(-3,0,0)),
           Component(id='BUFFER',kind='Buffer',capacity=int(p['buffer_capacity']),position=(-1.5,0,0)),
           Component(id='AI-INSPECTION',kind='Inspection',position=(0,0,0),handling_time_s=p['handling_s'],
                     inspection_deadline_s=deadline if cell=='inline' else None,robot_model='m0609' if cell=='robot' else '',
                     mtbf=p['mtbf_s'],mttr=p['mttr_s'],**common),
           Component(id='DIVERTER',kind='Diverter',position=(1.5,0,0)),
           Component(id='REINSPECTION',kind='Inspection',inspection_mode='ccifps',processing_time=reinspection_s,position=(3,0,1.5)),
           Component(id='GOOD-SINK',kind='Sink',position=(4.5,0,0)),
           Component(id='REJECT-SINK',kind='Sink',position=(4.5,0,1.5)),
           Component(id='HOLD-SINK',kind='Sink',position=(3,0,-1.5))]
    if policy=='A':items=[c for c in items if c.id!='REINSPECTION']
    else:items.append(Component(id='REINSPECTION_BUFFER',kind='Buffer',capacity=1,position=(2,0,1.5)))
    links=[Connection(source=a,target=b) for a,b in [('SOURCE','BUFFER'),('BUFFER','AI-INSPECTION'),('AI-INSPECTION','DIVERTER')]]
    links += [Connection(source='DIVERTER',target=dst,condition=v) for v,dst in [('OK','GOOD-SINK'),('NG','REJECT-SINK' if policy=='A' else 'REINSPECTION_BUFFER'),('SKIPPED','HOLD-SINK')]]
    if policy=='B':links.append(Connection(source='REINSPECTION_BUFFER',target='REINSPECTION'))
    if policy=='B':links += [Connection(source='REINSPECTION',target=dst,condition=v) for v,dst in [('OK','GOOD-SINK'),('NG','REJECT-SINK'),('SKIPPED','HOLD-SINK')]]
    return FactoryModel(id='aria-dt-comparison',seed=seed,components=items,connections=links,simulation=Simulation(duration=3600),layout={'source_sampling':{'mode':'seeded_replacement','defect_rate':p['defect_rate'],'source':'assumed'},'offline_reinspection':{'buffer':'REINSPECTION_BUFFER','capacity':'unbounded','blocks_main_line':False} if policy=='B' else None})
