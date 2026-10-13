"""Prepare the current policy-A plan. Full DES execution awaits user confirmation."""
import argparse
import hashlib
import json
from pathlib import Path

from aria.simulation.dt.plan import condition_key, des_plan, posthoc_variants

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PILOT = ROOT / 'docs/validation/aria_dt_20261013_03/des_pilot30'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def reusable_runs(pilot, p1):
    """Validate saved A artifacts and current P1/line inputs before planning reuse."""
    protocol = json.loads((pilot / 'protocol.json').read_text())
    reuse = {}
    for c in protocol['plan']:
        if c['policy'] != 'A':
            continue
        rid = hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:16]
        folder = pilot / 'runs' / rid
        done = json.loads((folder / 'complete.json').read_text())
        if done['lock']['config'] != c:
            raise ValueError('Pilot configuration mismatch')
        for name, expected in done['hashes'].items():
            path = (folder / name).resolve()
            if not path.is_relative_to(folder.resolve()) or sha(path) != expected:
                raise ValueError('Pilot artifact mismatch: ' + str(path))
        base = p1 / c['class_name']
        for path in (base / c['selector'] / 'predictions.csv',
                     base / c['selector'] / 'latency_profile_faiss_gpu.json',
                     base / 'gt_labels.csv', ROOT / 'configs/line_profile.yaml'):
            if done['lock']['inputs'].get(str(path.resolve())) != sha(path):
                raise ValueError('Pilot input changed: ' + str(path))
        key = condition_key(c)
        if key in reuse:
            raise ValueError('Duplicate reusable condition')
        reuse[key] = dict(path=str(folder.resolve()), complete_sha256=sha(folder / 'complete.json'),
                          historical_source_hash=done['lock']['source_hash'])
    if len(reuse) != 15:
        raise ValueError('Expected 15 reusable policy-A pilot runs')
    return reuse


def build_plan(reuse=None):
    reuse = reuse or {}
    conditions = des_plan()
    if set(reuse) - {condition_key(c) for c in conditions}:
        raise ValueError('Reuse inventory contains conditions outside current plan')
    jobs = []
    for c in conditions:
        job = dict(config=c, reuse=reuse.get(condition_key(c)))
        job['action'] = 'reuse' if job['reuse'] else 'pending_confirmation'
        jobs.append(job)
    views = [v for c in conditions for v in posthoc_variants(c)]
    return dict(schema_version=3, sim=1, status='awaiting_user_confirmation',
                full_execution_authorized=False, new_DES_executed=0,
                baseline_A_total=2700, cap_check_total=270, unique_DES_total=2970,
                baseline_A_reuse=len(reuse), new_DES_pending=2970-len(reuse),
                actual_B_DES=0, posthoc_B_baseline=2700, posthoc_OFAT=1620,
                workers=2, threads_per_worker_max=4, horizon_s=3600, warmup_s=600,
                defect_rate=.05, defect_rate_source='assumed',
                cap_speed_m_s=2., cap_speed_source='assumed',
                seed0_cap_probe_count=9, seed0_probe_included_in_270=True,
                normalization='per 1000 main-line departures in [600,3600], including HOLD',
                cost_ratios=[5,20,100],
                gates=['explicit user confirmation', 'measured cap probe budget <=8h',
                       'storage estimate with 15% reserve plus 2 GiB', '15-pair posthoc parity'],
                jobs=jobs, posthoc_views=views)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--p1', type=Path, required=True)
    parser.add_argument('--pilot-results', type=Path, default=DEFAULT_PILOT)
    parser.add_argument('--execute', action='store_true', help='Reserved; currently blocked pending confirmation')
    args = parser.parse_args()
    if args.execute:
        parser.error('Full DES execution is not authorized. Generate and review the plan first.')
    if args.out.exists():
        parser.error('Output already exists; preserve it and choose a new path')
    plan = build_plan(reusable_runs(args.pilot_results.resolve(), args.p1.resolve()))
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'execution_plan.json').write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k:v for k,v in plan.items() if k not in ('jobs', 'posthoc_views')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
