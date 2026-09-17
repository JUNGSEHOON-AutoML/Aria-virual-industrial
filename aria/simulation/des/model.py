"""Validated V1 factory contract. Seconds, metres, radians; finite DAG flows."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

KINDS = ('Source', 'Conveyor', 'Buffer', 'Machine', 'Inspection', 'Diverter', 'Sink')
STATES = ('IDLE', 'STARVED', 'PROCESSING', 'BLOCKED', 'DOWN', 'SETUP', 'MAINTENANCE')

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Component(Contract):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    kind: Literal['Source', 'Conveyor', 'Buffer', 'Machine', 'Inspection', 'Diverter', 'Sink']
    name: str = Field(default='', max_length=120)
    position: tuple[float, float, float] = (0, 0, 0)
    rotation: float = 0
    capacity: int = Field(default=1, ge=1, le=100)
    interarrival: float = Field(default=2, ge=.05, le=3600)
    batch_size: int = Field(default=1, ge=1, le=100)
    product_type: str = Field(default='part', max_length=100)
    processing_time: float = Field(default=3, ge=.01, le=3600)
    setup_time: float = Field(default=0, ge=0, le=3600)
    length: float = Field(default=2, ge=.01, le=100)
    speed: float = Field(default=.5, ge=.01, le=20)
    queue_discipline: Literal['FIFO', 'LIFO'] = 'FIFO'
    availability: float = Field(default=1, gt=0, le=1)
    mtbf: float = Field(default=0, ge=0, le=1e7)
    mttr: float = Field(default=20, ge=.01, le=3600)
    maintenance: bool = False
    inspection_mode: Literal['mock', 'patchcore', 'ccifps', 'combined'] = 'mock'
    defect_rate: float = Field(default=.12, ge=0, le=1)
    category: str = Field(default='bottle', pattern=r'^[A-Za-z0-9_-]+$')
    run_id: str = ''
    image_paths: list[str] = Field(default_factory=list, max_length=1000)
    threshold: float = Field(default=.5, ge=0)
    bank: str = ''
    cad_asset: str = Field(default='', pattern=r'^(|[0-9a-f]{24})$')

    @model_validator(mode='after')
    def check(self):
        if self.kind == 'Source' and self.batch_size > self.capacity:
            raise ValueError('Source capacity must accommodate its batch_size')
        if self.mtbf and self.mtbf < .05:
            raise ValueError('MTBF must be zero (disabled) or >= .05s')
        if any(abs(v) > 1000 for v in self.position):
            raise ValueError('Position is outside the 1000m workspace')
        return self

class Connection(Contract):
    source: str
    target: str
    condition: Literal['always', 'OK', 'NG', 'SKIPPED'] = 'always'

class Simulation(Contract):
    duration: float = Field(default=600, ge=1, le=3600)
    speed: Literal['1', '2', '5', '20', 'MAX'] = '1'

class FactoryModel(Contract):
    id: str = Field(default='factory-demo-01', pattern=r'^[A-Za-z0-9_-]{1,64}$')
    name: str = Field(default='ARIA Demo Factory', max_length=120)
    seed: int = Field(default=42, ge=0, le=2**32-1)
    components: list[Component] = Field(min_length=1, max_length=100)
    connections: list[Connection] = Field(default_factory=list, max_length=300)
    simulation: Simulation = Field(default_factory=Simulation)
    layout: dict = Field(default_factory=dict)

    @model_validator(mode='after')
    def graph(self):
        nodes = {c.id: c for c in self.components}
        if len(nodes) != len(self.components):
            raise ValueError('Component IDs must be unique')
        if sum(c.capacity for c in self.components) > 2000:
            raise ValueError('V1 supports at most 2000 total resource slots')
        edges = {i: [] for i in nodes}
        keys = set()
        for edge in self.connections:
            if edge.source not in nodes or edge.target not in nodes:
                raise ValueError('Connection references an unknown component')
            if nodes[edge.source].kind == 'Sink' or nodes[edge.target].kind == 'Source':
                raise ValueError('Sink cannot output and Source cannot receive')
            key = (edge.source, edge.condition)
            if key in keys:
                raise ValueError('Each output condition must have a single target')
            keys.add(key)
            edges[edge.source].append(edge.target)
        seen, active = set(), set()
        def visit(node):
            if node in active:
                raise ValueError('V1 supports acyclic factories; rework loops need V2')
            if node in seen:
                return
            active.add(node)
            for dest in edges[node]:
                visit(dest)
            active.remove(node)
            seen.add(node)
        for node in nodes:
            visit(node)
        return self

    def warnings(self):
        outputs = {e.source for e in self.connections}
        return [f'{c.id}: no output; products will block here' for c in self.components
                if c.kind != 'Sink' and c.id not in outputs]

def demo_factory():
    specs = [
        dict(id='SOURCE', kind='Source', capacity=5, position=(-12, 0, 0)),
        dict(id='CONVEYOR-01', kind='Conveyor', capacity=3, position=(-9, 0, 0)),
        dict(id='BUFFER-01', kind='Buffer', capacity=5, position=(-6, 0, 0)),
        dict(id='MACHINE-01', kind='Machine', processing_time=3, mtbf=300, mttr=20, position=(-3, 0, 0)),
        dict(id='CONVEYOR-02', kind='Conveyor', capacity=3, position=(0, 0, 0)),
        dict(id='AI-INSPECTION', kind='Inspection', processing_time=.7, position=(3, 0, 0)),
        dict(id='DIVERTER', kind='Diverter', position=(6, 0, 0)),
        dict(id='GOOD-SINK', kind='Sink', position=(9, 0, -2)),
        dict(id='REJECT-SINK', kind='Sink', position=(9, 0, 2)),
        dict(id='HOLD-SINK', kind='Sink', position=(9, 0, 5)),
    ]
    links = [Connection(source=a['id'], target=b['id']) for a, b in zip(specs[:6], specs[1:7])]
    links += [Connection(source='DIVERTER', target=t, condition=v)
              for t, v in [('GOOD-SINK', 'OK'), ('REJECT-SINK', 'NG'), ('HOLD-SINK', 'SKIPPED')]]
    return FactoryModel(components=[Component(**c) for c in specs], connections=links)
