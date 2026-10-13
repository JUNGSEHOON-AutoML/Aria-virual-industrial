"""Downstream-only TRANSFER program. The DES inspection controller is unchanged.

Joint limits/FK come from the existing robot module. Authored poses and timing
are assumptions, not recorded hardware control or a collision/safety proof.
"""
import math
from aria.simulation.des.robot import JOINTS, POSES, fk, tool_point, validate


def program(transfer_seconds=0.5, *, pick=None, transfer=None, place=None):
    if not math.isfinite(transfer_seconds) or transfer_seconds <= 0:
        raise ValueError('TRANSFER duration must be finite and positive')
    targets = {
        'home': list(POSES['home']), 'pick': list(pick if pick is not None else POSES['pick']),
        'transfer': list(transfer if transfer is not None else [0, math.radians(10), math.radians(75), 0, math.radians(95), 0]),
        'place': list(place if place is not None else POSES['place']),
    }
    for q in targets.values():
        validate(q)
    rows, clock, previous = [], 0., targets['home']
    for stage, name, hold in [('MOVE_PICK','pick',0),('GRIP','pick',.6),
                              ('MOVE_TRANSFER','transfer',0),('TRANSFER','transfer',transfer_seconds),
                              ('MOVE_PLACE','place',0),('RELEASE','place',.6),('RETURN_HOME','home',0)]:
        q = targets[name]
        duration = hold or max(1.5, max(1.875*abs(b-a)/j['velocity'] for a,b,j in zip(previous,q,JOINTS)))
        rows.append(dict(stage=stage,start=clock,duration=duration,from_q=list(previous),target=list(q)))
        previous,clock=q,clock+duration
    return rows,clock


def sample(elapsed, *, object_id, transfer_seconds=.5, stopped=False, **poses):
    if not isinstance(object_id,str) or not object_id:
        raise ValueError('A source object ID is required')
    if not math.isfinite(elapsed):
        raise ValueError('Elapsed time must be finite')
    rows,total=program(transfer_seconds,**poses)
    elapsed=max(0.,min(elapsed,total))
    row=next((r for r in rows if elapsed<r['start']+r['duration']),rows[-1])
    u=max(0.,min(1.,(elapsed-row['start'])/row['duration']))
    blend=10*u**3-15*u**4+6*u**5
    velocity=0. if stopped else (30*u*u-60*u**3+30*u**4)/row['duration']
    q=[a+(b-a)*blend for a,b in zip(row['from_q'],row['target'])]
    dq=[(b-a)*velocity for a,b in zip(row['from_q'],row['target'])]
    frames,tool=fk(q)
    attached=row['stage'] in ('MOVE_TRANSFER','TRANSFER','MOVE_PLACE')
    release=next(r['start'] for r in rows if r['stage']=='RELEASE')
    fixture=rows[4]['target'] if elapsed>=release else rows[0]['target']
    object_tcp=tool_point(tool) if attached else tool_point(fk(fixture)[1])
    return dict(program='TRANSFER',stage=row['stage'],elapsed=elapsed,duration=total,
                joints=q,velocity=dq,tcp=tool_point(tool),frames=[m.T.flatten().tolist() for m in frames],
                tool_frame=tool.T.flatten().tolist(),object_id=object_id,object_tcp=object_tcp,
                attached_object_id=object_id if attached else None,attached=attached,
                gripper='CLOSED' if attached else 'OPEN',stopped=stopped,tag='assumed',
                source='downstream object-ready event; no DES write-back')


def grade_program(grade, transfer_seconds=.5):
    """Assumed, distinct grade pallet fixtures; never change inspection poses."""
    if grade not in ('A', 'B', 'C'):
        raise ValueError('Unknown roll grade')
    place=list(POSES['place']);place[0]+={'A':-.4,'B':0.,'C':.4}[grade]
    return program(transfer_seconds,place=place)


def schedule(events, transfer_seconds=.5):
    """One task per source event; serialize each actor's queue without feedback."""
    _,duration=program(transfer_seconds)
    seen=set();free={};tasks=[]
    for event in sorted(events,key=lambda e:(e['time'],e['id'])):
        if event['id'] in seen:
            raise ValueError('Duplicate source event')
        if not math.isfinite(event['time']) or event['time']<0 or not event.get('object_id'):
            raise ValueError('Invalid source event')
        seen.add(event['id']);actor=event['actor'];start=max(event['time'],free.get(actor,0.))
        if 'grade' in event:
            _,duration=grade_program(event['grade'],transfer_seconds)
        else:
            _,duration=program(transfer_seconds)
        tasks.append(dict(id='TRANSFER:'+event['id'],source_event=event['id'],source_time=event['time'],
                          object_id=event['object_id'],kind=event['kind'],actor=actor,start=start,end=start+duration,
                          wait=start-event['time'],tag='assumed',**({'grade':event['grade']} if 'grade' in event else {})))
        free[actor]=start+duration
    return tasks
