"""Compare canonical DES runtime bytes to a pre-edit capture (never recapture)."""
import argparse,hashlib,json
from pathlib import Path
from aria.simulation.des import Engine, FactoryModel

def verify(baseline):
    golden=json.loads(Path(baseline).read_text());rows=[]
    encode=lambda x:json.dumps(x,sort_keys=True,separators=(',',':')).encode()
    for name,g in golden.items():
        events=[];e=Engine(FactoryModel.model_validate(g['model']),event_sink=events.append);m=e.run_until(600)
        now=dict(events=events,metrics=m,parts=e.snapshot()['parts']);old={k:g[k] for k in now}
        a,b=encode(old),encode(now)
        rows.append(dict(case=name,event_count=len(events),identical_bytes=a==b,
                         before_sha256=hashlib.sha256(a).hexdigest(),after_sha256=hashlib.sha256(b).hexdigest()))
    return dict(passed=all(r['identical_bytes'] for r in rows),cases=rows)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=verify(a.baseline);a.out.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 1)
