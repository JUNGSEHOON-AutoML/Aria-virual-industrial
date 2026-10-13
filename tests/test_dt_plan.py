import json
import subprocess
import sys
from pathlib import Path

import pytest

from aria.simulation.dt.plan import condition_key, des_plan, posthoc_variants
from tools.benchmark_dt import trial
from tools.run_dt_matrix import build_plan


def test_inventory_keeps_unique_capped_conditions_and_posthoc_only_b():
    plan = des_plan()
    assert len(plan) == len({condition_key(c) for c in plan}) == 2970
    assert all(c['policy'] == 'A' and c['defect_rate'] == .05 for c in plan)
    cap = [c for c in plan if c['scope'] == 'cap_check']
    assert len(cap) == 270
    assert len([c for c in cap if c['seed'] == 0]) == 9
    assert all(c['speed'] == 2 and c['cell'] == 'inline' and c['latency_mode'] == 'profile' for c in cap)
    assert all(not posthoc_variants(c) for c in cap)
    views = [v for c in plan for v in posthoc_variants(c)]
    assert len(views) == 4320
    assert sum(v['scope'] == 'sensitivity' for v in views) == 1620
    for v in views:
        changed = sum(v[k] != default for k, default in
                      [('sensitivity', 1), ('specificity', 1), ('reinspection_s', 30)])
        assert changed == (v['scope'] == 'sensitivity')


def test_b_trial_rejected_before_any_output(tmp_path):
    with pytest.raises(ValueError, match='posthoc only'):
        trial(({'policy': 'B'}, tmp_path, tmp_path / 'out', '', ''))
    assert not (tmp_path / 'out').exists()


def test_reuse_accounting_and_unknown_condition():
    plan = des_plan()
    reuse = {condition_key(c): {'path': 'saved'} for c in plan[:15]}
    summary = build_plan(reuse)
    assert summary['new_DES_pending'] == 2955
    assert summary['new_DES_executed'] == 0
    assert not summary['full_execution_authorized']
    with pytest.raises(ValueError, match='outside'):
        build_plan({('foreign',): {}})


def test_execute_gate_precedes_input_reads_and_output_creation(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-m', 'tools.run_dt_matrix', '--execute',
                             '--p1', str(tmp_path / 'missing'), '--out', str(tmp_path / 'out')],
                            cwd=root, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'not authorized' in result.stderr
    assert not (tmp_path / 'out').exists()
