import json,re,subprocess
from tools.gates.common import ROOT,emit
def main():
 t=json.loads((ROOT/'frontend/src/brand/cnotta.tokens.json').read_text());flat={**{f'brand.{k}':v for k,v in t['brand'].items()},**{k:v for k,v in t.items() if k!='brand'}}
 required={'brand.ink','brand.primary','brand.primary-100','brand.primary-200','surface','floor','line','equip','equip-frame','cardboard','human','foliage','ok','ng','hold','text-2'}
 files=[p for folder in ['frontend/src/cnotta','frontend/src/brand','frontend/public/brand'] for p in (ROOT/folder).rglob('*') if p.is_file() and p.name!='cnotta.tokens.json']
 hits=[str(p.relative_to(ROOT)) for p in files if re.search(r'#[0-9a-fA-F]{3,8}\b',p.read_text())]
 return emit('m0',{'schema':{'pass':set(flat)==required and all(re.fullmatch(r'#[0-9A-F]{6}',v) for v in flat.values()),'tokens':len(flat)},'hardcoded_colors':{'pass':not hits,'files':hits,'scope':'active CNOTTA UI, brand and logo; historical D0 excluded'},'branch':{'pass':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='dt-cnotta'},'files':{'pass':all((ROOT/p).exists() for p in ['AGENTS.override.md','docs/autopilot/DECISIONS.md','docs/autopilot/BLOCKERS.md','docs/autopilot/PROGRESS.md','frontend/public/brand/cnotta-mark.svg'])}})
if __name__=='__main__':raise SystemExit(0 if main()['pass'] else 1)
