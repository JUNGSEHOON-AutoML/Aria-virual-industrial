import json
from pathlib import Path
import pytest

from tools import execute_dt_matrix as execution
from tools.summarize_policy_a import stats


def test_budget_rechecks_current_disk_after_cleanup(tmp_path):
    (tmp_path/'cost_gate.json').write_text(json.dumps(dict(estimated_total_seconds=24000,estimated_remaining_bytes=1000)))
    (tmp_path/'completion.json').write_text(json.dumps(dict(completed=9,new_DES_runs=9)))
    assert not execution.authorize_budget(tmp_path,0)['passed']
    assert execution.authorize_budget(tmp_path,3*1024**3)['passed']
    (tmp_path/'completion.json').write_text(json.dumps(dict(completed=8,new_DES_runs=8)))
    with pytest.raises(ValueError,match='Nine'):execution.authorize_budget(tmp_path,3*1024**3)


def test_posthoc_worker_creates_seven_auditable_views_without_des(tmp_path,monkeypatch):
    from aria.simulation.dt.plan import baseline
    config=next(c for c in baseline('bottle') if c['cell']=='inline' and c['speed']==.5 and c['latency_mode']=='profile')
    gt=tmp_path/'gt.csv';gt.write_text('image_id,is_defect\nn,0\nd,1\n')
    parts=[dict(part_id=f'p{i}',image_id=image,born=600.,mainline_exit_time=610.,inspection_time=610.,
                ai_verdict='NG',reinspection_queue_enter=None,reinspection_start=None,
                reinspection_time=None,reinspection_verdict=None,exit_time=610.,route='NG') for i,image in enumerate(['n','d'])]
    folder=tmp_path/'source';folder.mkdir();(folder/'complete.json').write_text('{}')
    monkeypatch.setattr(execution,'load_run',lambda *args:(config,parts,gt))
    result=execution.posthoc_job((config,str(folder),str(tmp_path),str(tmp_path/'out')))
    assert len(result['rows'])==7
    assert all(r['policy']=='B' and r['simulation_policy']=='A' for r in result['rows'])
    assert parts[0]['route']=='NG'
    for path in (tmp_path/'out/posthoc').glob('*/complete.json'):
        data=json.loads(path.read_text())
        assert data['new_DES_runs']==0
        for name,digest in data['hashes'].items():assert execution.sha(path.parent/name)==digest


def test_stats_uses_sample_t_interval_and_missing_values_remain_unavailable():
    assert stats([])['mean'] is None
    assert stats([1])['ci95_low'] is None
    row=stats(list(range(30)))
    assert row['n']==30 and row['mean']==14.5
    assert row['ci95_low']<14.5<row['ci95_high']
