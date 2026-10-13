import importlib.util
import json
from pathlib import Path
import pytest
from aria.reasoning.providers import OllamaProvider,AnthropicProvider,validated_intent
from aria.simulation.des.agent import IndustrialAgent
from aria.simulation.des.service import FactoryService

def legacy(service):
    p=Path(__file__).parent/'fixtures/legacy_local_plan.py';spec=importlib.util.spec_from_file_location('legacy_plan',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.__file__=str(Path(__file__).resolve().parents[1]/'aria/simulation/des/agent.py')
    obj=m.Legacy();obj.service=service;obj.timeout=30;return obj

@pytest.mark.parametrize('reply',[{'intent':'status'},{'intent':'bottleneck'},{'intent':'improve'},{'intent':'run'},{'intent':'pause'},{'intent':'unknown'},{'intent':'change','tool':'update_component','args':{'id':'MACHINE-01','changes':{'capacity':2}}},{'intent':'change','tool':'apply_factory_change','args':{}},'not-json'])
def test_exact_ollama_request_and_intent_behavior(reply,tmp_path,monkeypatch):
    import urllib.request
    calls=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):
            assert n==1000000
            return json.dumps({'message':{'content':reply if isinstance(reply,str) else json.dumps(reply)}}).encode()
    def fake(req,timeout):calls.append((req.full_url,json.loads(req.data),timeout));return Response()
    monkeypatch.setattr(urllib.request,'urlopen',fake)
    service=FactoryService(tmp_path);old=legacy(service)._local_plan('classify this request');new=IndustrialAgent(service)._local_plan('classify this request')
    assert new==old;assert calls[0]==calls[1]

def test_unavailable_and_forbidden_provider_cannot_apply(tmp_path,monkeypatch):
    import urllib.request
    def down(*a,**kw):raise ConnectionError('test offline')
    monkeypatch.setattr(urllib.request,'urlopen',down)
    s=FactoryService(tmp_path);a=IndustrialAgent(s)
    assert a._local_plan('unrecognized wording')[0]=='unknown'
    assert AnthropicProvider().state=='unavailable'
    assert IndustrialAgent(s,provider=AnthropicProvider())._local_plan('unrecognized')[0]=='unknown'
    class Hostile:
        def plan(self,*a):return {'intent':'change','tool':'apply_factory_change','args':{'id':'any'}},'malicious test'
    before=s.snapshot();answer=IndustrialAgent(s,provider=Hostile()).run('unrecognized wording')
    assert not answer.get('proposal');assert s.snapshot()==before
    with pytest.raises(ValueError):validated_intent({'intent':'change','tool':'run_command'})
    with pytest.raises(ValueError):validated_intent([])

def test_provider_proposal_still_requires_human_apply(tmp_path):
    class Provider:
        def plan(self,*a):return {'intent':'change','tool':'update_component','args':{'id':'MACHINE-01','changes':{'capacity':2}}},'test fixture'
    s=FactoryService(tmp_path);a=IndustrialAgent(s,provider=Provider());before=s.revision
    answer=a.run('unrecognized wording');assert answer['proposal'];assert s.revision==before
    with pytest.raises(PermissionError):s.call('apply_factory_change',{'id':answer['proposal']['id']})
