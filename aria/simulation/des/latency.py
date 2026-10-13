"""Pinned offline latency samples. No detector execution or GT in this module."""
import hashlib
import json
import random
from pathlib import Path
from typing import Literal
from pydantic import Field, model_validator
from .model import Contract

PROFILE_ROOT = Path(__file__).resolve().parents[3] / 'config' / 'latency_profiles'

class LatencyProfile(Contract):
    schema_version: Literal[1] = 1
    source: Literal['measured', 'synthetic_test']
    bundle_id: str = Field(min_length=1)
    selector: Literal['ccifps', 'coreset', 'random_same_k', 'synthetic_test']
    bank_k: int = Field(ge=1)
    hardware: str = Field(min_length=1)
    warmup: int = Field(ge=0)
    total_ms: list[float] = Field(min_length=1, max_length=100000)
    stages_ms: dict[str, list[float]] = Field(default_factory=dict)

    @model_validator(mode='after')
    def samples(self):
        import math
        if any(not math.isfinite(v) or not 0 < v <= 3600000 for v in self.total_ms):
            raise ValueError('total_ms must be finite, positive, and <= one hour')
        if set(self.stages_ms) - {'pre', 'feat', 'search', 'post'}:
            raise ValueError('Unknown latency stage')
        for values in self.stages_ms.values():
            if len(values) != len(self.total_ms) or any(not math.isfinite(v) or v < 0 for v in values):
                raise ValueError('Stage samples must be finite, nonnegative and aligned with total_ms')
        if self.source == 'measured':
            if len(self.total_ms) < 1000 or self.warmup < 50:
                raise ValueError('Measured profiles require >= 1000 samples after >= 50 warmups')
            if set(self.stages_ms) != {'pre', 'feat', 'search', 'post'} or self.selector == 'synthetic_test':
                raise ValueError('Measured profiles require all four stages and a real selector')
        elif self.selector != 'synthetic_test':
            raise ValueError('Synthetic profiles cannot impersonate a measured selector')
        return self

class ProfileSampler:
    def __init__(self, component, seed):
        relative = Path(component.latency_profile)
        # Public model paths are always repository-relative. Only this directory is readable.
        prefix = Path('config/latency_profiles')
        if relative.is_absolute() or not relative.is_relative_to(prefix):
            raise ValueError('Latency profile must be under config/latency_profiles/')
        path = (PROFILE_ROOT / relative.relative_to(prefix)).resolve()
        if not path.is_relative_to(PROFILE_ROOT.resolve()):
            raise ValueError('Latency profile escaped its allowed directory')
        with path.open('rb') as f:
            raw = f.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError('Latency profile exceeds 16 MiB')
        self.sha256 = hashlib.sha256(raw).hexdigest()
        if self.sha256 != component.latency_profile_sha256:
            raise ValueError('Latency profile SHA-256 mismatch')
        self.profile = LatencyProfile.model_validate_json(raw)
        self.seed = int.from_bytes(hashlib.sha256(f'aria-latency-v1:{seed}:{component.id}'.encode()).digest(), 'big')
        self.reset()

    def reset(self):
        self.rng = random.Random(self.seed)

    def sample(self):
        p = self.profile
        i = self.rng.randrange(len(p.total_ms))
        return dict(latency_ms=dict(total=p.total_ms[i], **{k:v[i] for k,v in p.stages_ms.items()}),
                    latency_source='profile', profile_source=p.source, profile_sha256=self.sha256,
                    profile_sample_index=i, bundle_id=p.bundle_id, selector=p.selector,
                    bank_k=p.bank_k, hardware=p.hardware)
