import importlib.util
from pathlib import Path
import numpy as np
import pytest
spec=importlib.util.spec_from_file_location('dt_search',Path(__file__).parents[1]/'tools/dt_exact_search.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_chunked_cosine_matches_full_matrix_and_earliest_tie():
    rng=np.random.default_rng(4); bank=rng.normal(size=(29,8)).astype('float32');bank[15]=bank[0]
    query=np.vstack([bank[0],rng.normal(size=(16,8))]).astype('float32')
    score,idx=m.NumpyExact(bank,3,7)(query)
    full=m.normalized(query) @ m.normalized(bank).T
    np.testing.assert_allclose(score,1-full.max(1),atol=1e-6)
    assert idx[0]==0

def test_invalid_cosine_input_is_rejected():
    for x in [np.zeros((1,8)),np.full((1,8),np.nan)]:
        with pytest.raises(ValueError):m.normalized(x)

def test_gate_fails_on_verdict_change_even_within_score_tolerance():
    def a(q):return np.array([.5]),np.array([0])
    def b(q):return np.array([.500001]),np.array([0])
    result=m.parity(a,b,[None],.5)
    assert not result['passed'] and result['verdict_changes']==1
