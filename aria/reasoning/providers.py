"""Provider transport only. Tool policy remains independently validated by the agent."""
import json
import os
import urllib.request
from pathlib import Path
from typing import Protocol

class ReasoningProvider(Protocol):
    def plan(self,text,context,timeout=30): ...

class OllamaProvider:
    state='configured_local'
    def plan(self,text,context,timeout=30):
        root = Path(__file__).resolve().parents[2]
        config = json.loads((root / 'mcp_config.json').read_text())
        model = config.get('models', {}).get('chat_ko', 'llama3.1')
        base = os.environ.get('OLLAMA_API_BASE', 'http://localhost:11434').rstrip('/')
        payload = dict(model=model, stream=False, format='json', options=dict(temperature=0, num_predict=500),
            messages=[dict(role='system', content='Return JSON only. intent: bottleneck|improve|status|run|pause|change|unknown. '
                'For change return tool (create_component, update_component, connect_components, delete_component) and args. '
                'Updates require id and changes; creates require component with id, kind, position. '
                'Allowed kinds: Source, Conveyor, Buffer, Machine, Inspection, Diverter, Sink. Never apply changes. '
                'Factory: ' + json.dumps(context)), dict(role='user', content=text)])
        req = urllib.request.Request(base + '/api/chat', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=min(12, timeout)) as response:
                plan = json.loads(json.loads(response.read(1000000))['message']['content'])
            return plan,model
        except Exception as exc:
            return {'intent':'unknown'},'local model unavailable or invalid plan: '+str(exc)[:140]

class AnthropicProvider:
    # Optional boundary only. No credential discovery, requests or simulated replies.
    state='unavailable'
    def plan(self,text,context,timeout=30):
        return {'intent':'unknown'},'Anthropic provider unavailable; not configured or validated'

ALLOWED_INTENTS=frozenset(('bottleneck','improve','status','run','pause'))
ALLOWED_CHANGE_TOOLS=frozenset(('create_component','update_component','connect_components','delete_component'))
def validated_intent(plan):
    if not isinstance(plan,dict):raise ValueError('Invalid provider JSON object')
    if plan.get('intent')=='change':
        if plan.get('tool') not in ALLOWED_CHANGE_TOOLS:raise ValueError('Invalid change tool')
        if not isinstance(plan.get('args',{}),dict):raise ValueError('Invalid tool arguments')
        return plan
    return plan['intent'] if plan.get('intent') in ALLOWED_INTENTS else 'unknown'
