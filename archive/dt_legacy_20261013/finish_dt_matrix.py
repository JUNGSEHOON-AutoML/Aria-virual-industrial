"""One-shot completion hook for an already authorized, running DES matrix."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--pid',type=int,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();out=a.out.resolve();status=out/'postprocess_status.json';start=time.time()
 def record(state,**kw):
  tmp=status.with_suffix('.tmp');tmp.write_text(json.dumps(dict(state=state,started_unix=start,updated_unix=time.time(),**kw),indent=2));tmp.replace(status)
 record('waiting_for_matrix',pid=a.pid)
 while not (out/'completion.json').exists():
  try:os.kill(a.pid,0)
  except ProcessLookupError:
   record('matrix_exited_without_completion');subprocess.run([sys.executable,str(ROOT/'tools/report_dt_status.py')],cwd=ROOT);return 1
  time.sleep(30)
 record('verifying_and_aggregating')
 with (out/'postprocess.log').open('w') as log:
  rc=subprocess.call([sys.executable,str(ROOT/'tools/summarize_dt.py'),'--out',str(out)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
  if rc:record('postprocess_failed',returncode=rc);return rc
  rc=subprocess.call([sys.executable,str(ROOT/'tools/report_dt_status.py')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
  record('complete' if rc==0 else 'report_failed',returncode=rc)
 return rc
if __name__=='__main__':raise SystemExit(main())
