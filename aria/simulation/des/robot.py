"""URDF-derived M0609 kinematics and bounded joint-space virtual controller.

Official geometry/limits; authored pick/inspect/place program. Not recorded
hardware motion, a Doosan controller emulator, or dynamics/collision validation.
"""
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np

SOURCE=Path(__file__).resolve().parents[3]/'assets/robots/doosan_m0609'
ROOT=ET.parse(SOURCE/'m0609.urdf').getroot()
JOINTS=[]
for j in ROOT.findall('joint'):
    if j.get('type')!='revolute':continue
    JOINTS.append(dict(name=j.get('name'),xyz=[float(x) for x in j.find('origin').get('xyz').split()],
        rpy=[float(x) for x in j.find('origin').get('rpy').split()],
        **{k:float(v) for k,v in j.find('limit').attrib.items()}))
POSES={k:np.deg2rad(v).tolist() for k,v in dict(home=[0,0,90,0,90,0],pick=[35,45,90,0,45,0],inspect=[0,20,90,0,70,0],place=[-35,45,90,0,45,0]).items()}

def transform(xyz,rpy):
    r,p,y=rpy;cr,sr=math.cos(r),math.sin(r);cp,sp=math.cos(p),math.sin(p);cy,sy=math.cos(y),math.sin(y)
    out=np.eye(4)
    out[:3,:3]=[[cy*cp,cy*sp*sr-sy*cr,cy*sp*cr+sy*sr],[sy*cp,sy*sp*sr+cy*cr,sy*sp*cr-cy*sr],[-sp,cp*sr,cp*cr]]
    out[:3,3]=xyz
    return out
ORIGINS=[transform(j['xyz'],j['rpy']) for j in JOINTS]

def validate(q):
    if len(q)!=6 or any(not math.isfinite(v) or not j['lower']<=v<=j['upper'] for v,j in zip(q,JOINTS)):
        raise ValueError('Joint target outside official URDF limits')

def fk(q):
    validate(q);m=np.eye(4);frames=[m.copy()]
    for origin,a in zip(ORIGINS,q):
        m=m@origin@transform([0,0,0],[0,0,a]);frames.append(m.copy())
    tool=m@transform([0,0,0],[math.pi,-math.pi/2,0])
    return frames,tool

def tool_point(flange):
    # Authored 120 mm gripper TCP relative to the official URDF tool0 flange.
    return (flange[:3,3]+flange[:3,2]*.12).tolist()

def program(processing_time):
    # Each move uses a zero-end-velocity quintic profile. Peak s' is 1.875.
    rows=[];previous=POSES['home'];clock=0.
    for stage,target,hold in [('MOVE_PICK','pick',0),('GRIP','pick',.6),('MOVE_INSPECT','inspect',0),('INSPECT','inspect',processing_time),('MOVE_PLACE','place',0),('RELEASE','place',.6),('RETURN_HOME','home',0)]:
        q=POSES[target];validate(q)
        duration=hold or max(1.5,max(1.875*abs(b-a)/j['velocity'] for a,b,j in zip(previous,q,JOINTS)))
        rows.append(dict(stage=stage,start=clock,duration=duration,from_q=list(previous),target=list(q)))
        clock+=duration;previous=q
    return rows,clock

def sample(processing_time,elapsed,stopped=False):
    rows,total=program(processing_time);elapsed=max(0.,min(elapsed,total))
    row=next((r for r in rows if elapsed<r['start']+r['duration']),rows[-1])
    t=min(1.,max(0.,(elapsed-row['start'])/row['duration']));blend=10*t**3-15*t**4+6*t**5
    velocity=(30*t*t-60*t**3+30*t**4)/row['duration'] if not stopped else 0.
    q=[a+(b-a)*blend for a,b in zip(row['from_q'],row['target'])]
    dq=[(b-a)*velocity for a,b in zip(row['from_q'],row['target'])]
    frames,tcp=fk(q)
    attached=row['stage'] in ('MOVE_INSPECT','INSPECT','MOVE_PLACE')
    return dict(model='m0609',stage=row['stage'],elapsed=elapsed,duration=total,stopped=stopped,
        joints=q,target=row['target'],velocity=dq,tcp=tool_point(tcp),
        frames=[m.T.flatten().tolist() for m in frames],tool_frame=tcp.T.flatten().tolist(),
        gripper='CLOSED' if attached else 'OPEN',attached=attached,
        target_error_rad=max(abs(a-b) for a,b in zip(q,row['target'])),
        controller='joint-space quintic virtual controller',feedback='simulated kinematic state')

def model_info():
    return dict(model='M0609',joints=JOINTS,poses=POSES,
        fixtures={k:tool_point(fk(q)[1]) for k,q in POSES.items()},
        source=json.loads((SOURCE/'source.json').read_text()),
        limits='URDF position and velocity limits; no dynamics or collision solver')


def self_test(q, elapsed):
    validate(q)
    t=min(1.,max(0.,elapsed/4))
    # Smooth out-and-back wrist test, zero endpoint velocity.
    amp=min(.08,JOINTS[5]['upper']-q[5])
    offset=amp*math.sin(math.pi*t)**2
    test=list(q);test[5]+=offset
    frames,tcp=fk(test)
    return dict(model='m0609',stage='MAINTENANCE_SELF_TEST',elapsed=min(4.,elapsed),duration=4.,stopped=False,
        joints=test,target=q,velocity=[0.,0.,0.,0.,0.,amp*math.pi/4*math.sin(2*math.pi*t)],
        tcp=tool_point(tcp),frames=[m.T.flatten().tolist() for m in frames],tool_frame=tcp.T.flatten().tolist(),
        gripper='TEST',attached=False,target_error_rad=abs(offset),controller='isolated virtual wrist test',feedback='simulated kinematic state')
