import json,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def emit(m,checks,**extra):
 result={'milestone':m,'pass':all(x['pass'] for x in checks.values()),'checks':checks,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),**extra}
 p=ROOT/f'docs/autopilot/gates/{m}.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n');print(json.dumps(result,ensure_ascii=False));return result
