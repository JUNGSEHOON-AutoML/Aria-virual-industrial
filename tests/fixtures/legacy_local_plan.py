# Frozen pre-refactor reference for request/intent regression only.
import json, os, urllib.request
from pathlib import Path
class Legacy:
    def _local_plan(self, text):
        root = Path(__file__).resolve().parents[3]
        config = json.loads((root / 'mcp_config.json').read_text())
        model = config.get('models', {}).get('chat_ko', 'llama3.1')
        base = os.environ.get('OLLAMA_API_BASE', 'http://localhost:11434').rstrip('/')
        context = self.service.call('get_factory_model')
        payload = dict(model=model, stream=False, format='json', options=dict(temperature=0, num_predict=500),
            messages=[dict(role='system', content='Return JSON only. intent: bottleneck|improve|status|run|pause|change|unknown. '
                'For change return tool (create_component, update_component, connect_components, delete_component) and args. '
                'Updates require id and changes; creates require component with id, kind, position. '
                'Allowed kinds: Source, Conveyor, Buffer, Machine, Inspection, Diverter, Sink. Never apply changes. '
                'Factory: ' + json.dumps(context)), dict(role='user', content=text)])
        req = urllib.request.Request(base + '/api/chat', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=min(12, self.timeout)) as response:
                plan = json.loads(json.loads(response.read(1000000))['message']['content'])
            if plan.get('intent') == 'change':
                if plan.get('tool') not in ('create_component', 'update_component', 'connect_components', 'delete_component'):
                    raise ValueError('Invalid change tool')
                return plan, model
            if plan.get('intent') not in ('bottleneck', 'improve', 'status', 'run', 'pause'):
                return 'unknown', model
            return plan['intent'], model
        except Exception as exc:
            return 'unknown', 'local model unavailable or invalid plan: ' + str(exc)[:140]
