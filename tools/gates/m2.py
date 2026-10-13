import json,subprocess,sys
from tools.gates.common import ROOT,emit
def main():
 r=json.loads((ROOT/'docs/autopilot/local/browser.json').read_text());b=r['replay'];s=b['snapshot'];samples=b['ten_x_samples']
 test=subprocess.run([sys.executable,'-m','pytest','tests/test_cnotta_api.py','-q'],cwd=ROOT,text=True,capture_output=True)
 (ROOT/'docs/autopilot/local/m2-tests.txt').write_text(test.stdout+test.stderr)
 return emit('m2',{'same_time_inventory':{'pass':s['ids']==s['expected'],'screen':len(s['ids']),'timeline':len(s['expected']),'time':s['time']},'pause':{'pass':b['paused_positions_equal']},'ten_x_order':{'pass':all(x['ids']==x['expected'] for x in samples) and all(a['time']<=z['time'] for a,z in zip(samples,samples[1:])) and samples[-1]['time']>s['time'],'times':[x['time'] for x in samples]},'api_tests':{'pass':test.returncode==0,'output':test.stdout.strip()},'console':{'pass':not r['errors'],'errors':r['errors']}},run_id=b['run_id'])
if __name__=='__main__':raise SystemExit(0 if main()['pass'] else 1)
