"""Serialized factory tool boundary, durable scenarios and optimistic approvals."""
import itertools
import json
import threading
import time
import uuid
from pathlib import Path
from .engine import Engine
from .model import FactoryModel, Component, Connection, demo_factory
from .inspection import InspectionAdapter

class FactoryService:
    def __init__(self, directory, inspect=None):
        self.directory = Path(directory)
        self.lock = threading.RLock()
        self.inspect = inspect
        self.revision = 0
        self.proposals = {}
        self.scenarios = {}
        self.undo = []
        self.last_experiment = None
        self.storage_error = None
        model = demo_factory()
        path = self.directory / 'factory.json'
        if path.is_file():
            try:
                saved = json.loads(path.read_text())
                model = FactoryModel.model_validate(saved['model'])
                self.revision = saved.get('revision', 0)
                self.scenarios = saved.get('scenarios', {})
                for scenario in self.scenarios.values():
                    FactoryModel.model_validate(scenario['model'])
            except (ValueError, KeyError, TypeError) as exc:
                self.storage_error = f'Persisted factory not loaded: {exc}'
        self.engine = Engine(model, inspect)
        self.speed = model.simulation.speed

    def _persist(self):
        if self.storage_error:
            raise ValueError(self.storage_error + '; repair the saved file before writing')
        self.directory.mkdir(parents=True, exist_ok=True)
        temp = self.directory / 'factory.json.tmp'
        temp.write_text(json.dumps(dict(model=self.engine.model.model_dump(), revision=self.revision,
                                       scenarios=self.scenarios), ensure_ascii=False, indent=2))
        temp.replace(self.directory / 'factory.json')

    def snapshot(self):
        with self.lock:
            return dict(**self.engine.snapshot(), revision=self.revision, speed=self.speed,
                        storage_error=self.storage_error, proposals=list(self.proposals.values())[-30:])

    def _proposal(self, model, reason, expected=None):
        model = FactoryModel.model_validate(model)
        if len(self.proposals) >= 100:
            self.proposals.pop(next(iter(self.proposals)))
        proposal = dict(id=uuid.uuid4().hex, revision=self.revision, status='pending', reason=reason,
                        before=self.engine.model.model_dump(), after=model.model_dump(), expected=expected)
        self.proposals[proposal['id']] = proposal
        return proposal

    def call(self, name, args=None, human=False):
        args = args or {}
        with self.lock:
            model = self.engine.model.model_dump()
            if name == 'get_factory_model':
                return model
            if name == 'get_factory_state':
                return self.snapshot()
            if name == 'list_components':
                return model['components']
            if name == 'get_component':
                return next(c for c in model['components'] if c['id'] == args['id'])
            if name == 'validate_factory_model':
                m = FactoryModel.model_validate(args.get('model', model))
                return dict(valid=True, warnings=m.warnings())
            if name in ('create_component', 'update_component', 'delete_component', 'connect_components', 'propose_factory_change', 'undo_factory_change'):
                if name == 'create_component':
                    model['components'].append(Component.model_validate(args['component']).model_dump())
                elif name == 'update_component':
                    found = False
                    for i, c in enumerate(model['components']):
                        if c['id'] == args['id']:
                            if 'id' in args['changes'] and args['changes']['id'] != c['id']:
                                raise ValueError('Component IDs are immutable')
                            model['components'][i] = dict(c, **args['changes'])
                            found = True
                    if not found:
                        raise ValueError('Unknown component')
                elif name == 'delete_component':
                    if not any(c['id'] == args['id'] for c in model['components']):
                        raise ValueError('Unknown component')
                    model['components'] = [c for c in model['components'] if c['id'] != args['id']]
                    model['connections'] = [e for e in model['connections'] if args['id'] not in (e['source'], e['target'])]
                elif name == 'connect_components':
                    model['connections'].append(Connection.model_validate(args).model_dump())
                elif name == 'undo_factory_change':
                    if not self.undo:
                        raise ValueError('No change to undo in this session')
                    model = self.undo[-1]
                else:
                    model = args['model']
                return self._proposal(model, args.get('reason', name), args.get('expected'))
            if name in ('apply_factory_change', 'reject_factory_change'):
                if not human:
                    raise PermissionError('Only the explicit human approval endpoint may resolve a change')
                p = self.proposals[args['id']]
                if p['status'] != 'pending':
                    raise ValueError('Proposal already resolved')
                if name == 'reject_factory_change':
                    p['status'] = 'rejected'
                    return p
                if p['revision'] != self.revision:
                    raise ValueError('Factory changed since proposal; regenerate the proposal')
                old, revision = self.engine, self.revision
                self.engine = Engine(p['after'], self.inspect)
                self.revision += 1
                try:
                    self._persist()
                except Exception:
                    self.engine, self.revision = old, revision
                    raise
                self.undo.append(old.model.model_dump())
                self.undo = self.undo[-20:]
                self.last_experiment = None
                p['status'] = 'applied'
                self.speed = self.engine.model.simulation.speed
                return self.snapshot()
            if name in ('start_simulation', 'resume_simulation'):
                speed = str(args.get('speed', self.speed))
                if speed not in ('1', '2', '5', '20', 'MAX'):
                    raise ValueError('Unsupported simulation speed')
                if self.engine.now >= self.engine.model.simulation.duration:
                    raise ValueError('Simulation completed; reset before running again')
                self.speed = speed
                self.engine.status = 'running'
                return self.snapshot()
            if name == 'pause_simulation':
                self.engine.status = 'paused'
                return self.snapshot()
            if name == 'step_simulation':
                if self.engine.now < self.engine.model.simulation.duration:
                    if self.engine.heap and self.engine.heap[0][0] <= self.engine.model.simulation.duration:
                        self.engine.step()
                    else:
                        self.engine.run_until(self.engine.model.simulation.duration)
                return self.snapshot()
            if name == 'reset_simulation':
                self.engine.reset()
                return self.snapshot()
            if name == 'get_simulation_metrics':
                return self.engine.metrics()
            if name == 'get_bottleneck_analysis':
                rows = self.engine.bottlenecks()
                if self.last_experiment:
                    for row in rows:
                        if row['component'] == self.last_experiment['component']:
                            row['throughput_sensitivity'] = self.last_experiment['candidates'][0]['improvement_percent']
                return rows
            if name == 'create_scenario':
                if len(self.scenarios) >= 50:
                    raise ValueError('Scenario storage limit (50) reached')
                sid = uuid.uuid4().hex
                scenario = dict(id=sid, name=str(args.get('name', 'Scenario'))[:120],
                                model=FactoryModel.model_validate(args.get('model', model)).model_dump())
                self.scenarios[sid] = scenario
                try:
                    self._persist()
                except Exception:
                    del self.scenarios[sid]
                    raise
                return scenario
            if name == 'list_scenarios':
                return list(self.scenarios.values())
            if name == 'run_scenario':
                return self._simulate(self.scenarios[args['id']]['model'], args.get('duration'))
            if name == 'compare_scenarios':
                ids = args['ids']
                if not 1 <= len(ids) <= 12:
                    raise ValueError('Compare 1–12 scenarios')
                return [dict(id=sid, **self._simulate(self.scenarios[sid]['model'], args.get('duration'))) for sid in ids]
            if name == 'run_parameter_sweep':
                return self._sweep(args)
            raise ValueError('Unknown factory tool: ' + name)

    def _simulate(self, model, duration=None, deadline=None):
        validated = FactoryModel.model_validate(model)
        horizon = float(duration if duration is not None else validated.simulation.duration)
        if not 1 <= horizon <= 3600:
            raise ValueError('Experiment duration must be 1–3600 seconds')
        # Real inspection is possible, but repeated inference is not silently mocked.
        e = Engine(validated, self.inspect)
        metrics = e.run_until(horizon, deadline=deadline or time.monotonic() + 10)
        return dict(metrics=metrics, bottlenecks=e.bottlenecks(), seed=validated.seed, duration=horizon)

    def _sweep(self, args):
        model = self.engine.model.model_dump()
        cid = args['component']
        component = next((c for c in model['components'] if c['id'] == cid), None)
        if component is None:
            raise ValueError('Unknown sweep component')
        grid = args.get('parameters', {'processing_time': [component['processing_time'] * .8], 'capacity': [1, 2]})
        if not grid or any(k not in ('processing_time', 'capacity', 'speed', 'setup_time', 'mtbf', 'mttr') for k in grid):
            raise ValueError('Unsupported sweep parameter')
        combinations = 1
        for values in grid.values():
            if not isinstance(values, list) or not values:
                raise ValueError('Each parameter needs a nonempty list')
            combinations *= len(values)
        if combinations > 12:
            raise ValueError('At most 12 sweep candidates')
        duration = args.get('duration', 600)
        deadline = time.monotonic() + 15
        baseline = self._simulate(model, duration, deadline)
        results = []
        for values in itertools.product(*grid.values()):
            changes = dict(zip(grid, values))
            candidate = json.loads(json.dumps(model))
            next(c for c in candidate['components'] if c['id'] == cid).update(changes)
            result = self._simulate(candidate, duration, deadline)
            base = baseline['metrics']['throughput_per_hour']
            delta = (result['metrics']['throughput_per_hour'] / base - 1) * 100 if base else None
            results.append(dict(changes=changes, improvement_percent=delta, model=candidate, **result))
        results.sort(key=lambda r: r['metrics']['throughput_per_hour'], reverse=True)
        self.last_experiment = dict(component=cid, baseline=baseline, candidates=results)
        return self.last_experiment

    def tick(self, dt):
        with self.lock:
            if self.engine.status != 'running':
                return None
            increment = 10 if self.speed == 'MAX' else min(dt, 1.) * float(self.speed)
            horizon = min(self.engine.now + increment, self.engine.model.simulation.duration)
            try:
                self.engine.run_until(horizon, max_events=20000)
                if horizon >= self.engine.model.simulation.duration:
                    self.engine.status = 'completed'
            except Exception as exc:
                self.engine.status = 'error'
                self.engine.error = str(exc)
            return self.snapshot()

TOOL_NAMES = ('get_factory_model', 'get_factory_state', 'get_component', 'list_components',
    'create_component', 'update_component', 'delete_component', 'connect_components', 'validate_factory_model',
    'start_simulation', 'pause_simulation', 'resume_simulation', 'step_simulation', 'reset_simulation',
    'get_simulation_metrics', 'get_bottleneck_analysis', 'create_scenario', 'list_scenarios', 'run_scenario',
    'compare_scenarios', 'run_parameter_sweep', 'propose_factory_change', 'apply_factory_change',
    'reject_factory_change', 'undo_factory_change')
