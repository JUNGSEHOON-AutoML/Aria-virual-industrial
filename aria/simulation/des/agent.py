"""Bounded observe/plan/tool/evaluate agent. All claims are rendered from tools.

Known industrial requests work offline. Local Ollama routes other wording into
validated intents, never generates KPI numbers or executes arbitrary Python.
"""
import json
import os
import re
import time
import urllib.request
from pathlib import Path

class IndustrialAgent:
    def __init__(self, service, max_iterations=8, timeout=30):
        self.service = service
        self.max_iterations = max_iterations
        self.timeout = timeout

    def _intent(self, text):
        lower = text.lower()
        if any(w in lower for w in ('개선', '높여', '높일', '올려', '올릴', 'improve', 'optimiz', 'increase')):
            return 'improve', 'deterministic'
        if any(w in lower for w in ('병목', 'bottleneck')):
            return 'bottleneck', 'deterministic'
        if any(w in lower for w in ('상태', '지표', 'metric', 'status')):
            return 'status', 'deterministic'
        if any(w in lower for w in ('일시정지', 'pause')):
            return 'pause', 'deterministic'
        if any(w in lower for w in ('시작', '실행', 'resume', 'start simulation')):
            return 'run', 'deterministic'
        # Offline forms for common factory changes; all go through the same approval gate.
        if any(w in lower for w in ('기본 공장', 'demo factory')) and any(w in lower for w in ('만들', '설계', 'create', 'design')):
            from .model import demo_factory
            return dict(intent='change', tool='propose_factory_change', args=dict(model=demo_factory().model_dump(), reason='Create default factory')), 'deterministic'
        for c in self.service.call('list_components'):
            if c['id'].lower() in lower and any(w in lower for w in ('변경', '수정', '바꿔', '설정', 'set ', 'change')):
                fields = [('processing_time', r'(?:processing(?: time)?|처리\s*시간)\s*(?:을|를|:|=|to)?\s*(\d+(?:\.\d+)?)'),
                          ('capacity', r'(?:capacity|용량|병렬\s*수)\s*(?:을|를|:|=|to)?\s*(\d+)'),
                          ('speed', r'(?:speed|속도)\s*(?:을|를|:|=|to)?\s*(\d+(?:\.\d+)?)')]
                for field, pattern in fields:
                    match = re.search(pattern, lower)
                    if match:
                        value = int(match.group(1)) if field == 'capacity' else float(match.group(1))
                        return dict(intent='change', tool='update_component', args=dict(id=c['id'], changes={field:value})), 'deterministic'
        if any(w in lower for w in ('설계', '추가', '변경', '수정', 'create', 'add ', 'update', 'design')):
            return self._local_plan(text)
        return self._local_plan(text)

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

    def run(self, text):
        started = time.monotonic()
        trace = []
        def tool(name, args=None):
            if len(trace) >= self.max_iterations or time.monotonic() - started > self.timeout:
                raise ValueError('Agent iteration/time budget exceeded')
            result = self.service.call(name, args)
            trace.append(dict(tool=name, arguments=args or {}, result=result))
            return result
        try:
            intent, route = self._intent(text)
            proposal = None
            evidence = None
            if isinstance(intent, dict):
                proposal = tool(intent['tool'], intent.get('args', {}))
                answer = '공장 변경안을 만들었습니다. 변경 전후 설정을 검토한 뒤 Apply로 승인하세요.'
            elif intent == 'bottleneck':
                metrics = tool('get_simulation_metrics')
                if metrics['time'] < 30 or metrics['completed'] == 0:
                    scenario = tool('create_scenario', dict(name='Agent baseline'))
                    evidence = tool('run_scenario', dict(id=scenario['id'], duration=600))
                    ranked = evidence['bottlenecks']
                    prefix = '600초 별도 baseline 실험'
                else:
                    ranked = tool('get_bottleneck_analysis')
                    prefix = f"현재 {metrics['time']:.1f}초 계측"
                if ranked:
                    best = ranked[0]
                    answer = (f"{prefix} 기준 병목 후보는 {best['component']}입니다. "
                              f"가동률 {best['utilization'] * 100:.1f}%, 상류 평균 재공 {best['upstream_queue']:.2f}개, "
                              f"상류 평균 대기 {best['upstream_wait']:.2f}초입니다. 민감도는 개선 실험으로 확인할 수 있습니다.")
                else:
                    answer = '분석할 처리 설비가 없습니다.'
            elif intent == 'improve':
                model = tool('get_factory_model')
                baseline = tool('create_scenario', dict(name='Improvement baseline'))
                measured = tool('run_scenario', dict(id=baseline['id'], duration=600))
                candidates = [r for r in measured['bottlenecks'] if next(c for c in model['components'] if c['id'] == r['component'])['kind'] in ('Machine', 'Inspection')]
                if not candidates:
                    raise ValueError('No processing resource to optimize')
                cid = candidates[0]['component']
                c = next(c for c in model['components'] if c['id'] == cid)
                evidence = tool('run_parameter_sweep', dict(component=cid, duration=600,
                    parameters=dict(processing_time=[c['processing_time'], max(.01, c['processing_time'] * .8)],
                                    capacity=sorted(set([c['capacity'], min(100, c['capacity'] + 1)])))))
                best = evidence['candidates'][0]
                b = evidence['baseline']['metrics']['throughput_per_hour']
                a = best['metrics']['throughput_per_hour']
                gain = best['improvement_percent']
                target_match = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
                target = float(target_match.group(1)) if target_match else 10.
                if gain is not None and gain > 0:
                    proposal = tool('propose_factory_change', dict(model=best['model'], reason=f'{cid} measured parameter sweep',
                        expected=dict(baseline=b, candidate=a, improvement_percent=gain, horizon=600, seed=model['seed'])))
                outcome = '목표 충족' if gain is not None and gain >= target else '목표 미달'
                gain_text = f'{gain:+.1f}%' if gain is not None else 'baseline 처리량 0으로 비율 계산 불가'
                answer = f"동일 seed의 600초 실험 {len(evidence['candidates'])}개를 비교했습니다. {cid}: {b:.1f}/h → {a:.1f}/h ({gain_text}, {outcome}). 결과는 이 모델·seed·기간에 한정됩니다."
            elif intent == 'status':
                evidence = tool('get_simulation_metrics')
                answer = f"시뮬레이션 {evidence['time']:.1f}초, 처리량 {evidence['throughput_per_hour']:.1f}/h, WIP {evidence['wip']}개, 평균 리드타임 {evidence['lead_time']:.2f}초입니다."
            elif intent in ('run', 'pause'):
                tool('start_simulation' if intent == 'run' else 'pause_simulation')
                answer = '시뮬레이션을 시작했습니다.' if intent == 'run' else '시뮬레이션을 일시정지했습니다.'
            else:
                answer = '요청을 실행 가능한 계획으로 해석하지 못했습니다. “현재 병목을 분석해줘”, “처리량을 10% 개선해줘”, “현재 상태”를 사용할 수 있습니다. 공장 설계·변경은 로컬 모델 연결 또는 왼쪽 컴포넌트 도구를 사용하세요.'
            return dict(answer=answer, route=route, proposal=proposal, evidence=evidence, trace=trace,
                        elapsed=time.monotonic() - started)
        except Exception as exc:
            return dict(answer='요청을 완료하지 못했습니다: ' + str(exc), error=str(exc), trace=trace,
                        elapsed=time.monotonic() - started)
