"""Packaging gate: fresh local clone, provided pilot data, full tests and golden."""
import json,os,socket,subprocess,sys,tempfile
from pathlib import Path
from .common import ROOT,emit
out=ROOT/'docs/autopilot/local';checks={}
clone=Path(tempfile.mkdtemp(prefix='cnotta-fresh-'))/'repo'
r=subprocess.run(['git','clone','--shared','--no-hardlinks','--branch','dt-cnotta',str(ROOT),str(clone)],text=True,capture_output=True)
if r.returncode:raise RuntimeError(r.stderr)
(clone/'frontend/node_modules').symlink_to(ROOT/'frontend/node_modules',target_is_directory=True)
env=os.environ.copy();ports=[]
for _ in range(2):
 with socket.socket() as s:s.bind(('127.0.0.1',0));ports.append(s.getsockname()[1])
env.update(CNOTTA_PYTHON=sys.executable,CNOTTA_NODE=os.environ.get('CNOTTA_NODE',str(Path(sys.executable).parent/'node')),CNOTTA_PILOT=str(ROOT/'docs/validation/aria_dt_20261013_03/des_pilot30'),CNOTTA_P1=str(ROOT/'docs/validation/aria_dt_20261012_02/p1_verified'),CNOTTA_API_PORT=str(ports[0]),CNOTTA_WEB_PORT=str(ports[1]))
r=subprocess.run(['bash','scripts/demo.sh','--check'],cwd=clone,env=env,text=True,capture_output=True,timeout=180)
first=r
if r.returncode==0:r=subprocess.run(['bash','scripts/demo.sh','--check'],cwd=clone,env=env,text=True,capture_output=True,timeout=180)
(out/'m6-fresh-clone.txt').write_text(first.stdout+first.stderr+r.stdout+r.stderr)
checks['fresh_clone']={'pass':r.returncode==0,'clone':str(clone),'returncode':r.returncode,'immediate_restart_pass':first.returncode==r.returncode==0,'output':r.stdout+r.stderr,'dependencies':'existing isolated Python and linked local node_modules; no network','data':'original verified pilot/P1 read-only paths'}
tests=(out/'m6-tests.txt').read_text();golden=(out/'m6-golden.txt').read_text();build=(out/'m6-build.txt').read_text();recording=json.loads((out/'recording.json').read_text())
checks['backend_tests']={'pass':'163 passed' in tests and 'failed' not in tests,'summary':tests.splitlines()[-1]}
checks['golden']={'pass':'diff 0' in golden,'output':golden.strip()}
checks['cpu_build']={'pass':'built in' in build,'output':build[-1500:]}
checks['recording']={'pass':recording['duration_seconds']>=60 and not recording['errors'],**recording}
checks['protected_sources']={'pass':not subprocess.check_output(['git','diff','dt-dashboard-p6','--','aria/simulation/dt','AGENTS.md','TOOLS.md','SKILL.md','docs/validation'],cwd=ROOT).strip()}
result=emit('m6',checks,scope='pilot demo; M5 pending full experiment; actual GPU unverified')
raise SystemExit(0 if result['pass'] else 1)
