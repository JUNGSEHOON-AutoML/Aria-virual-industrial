"""Measure the nine authorized cap seed0 trials, then stop if time or storage gates fail."""
import argparse
import csv
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import shutil
import time
from concurrent.futures import ProcessPoolExecutor

from aria.simulation.dt.plan import CLASSES, SELECTORS, des_plan
from tools.benchmark_dt import trial, write, csvwrite
from tools.run_dt_matrix import ROOT, reusable_runs, sha


def gate_decision(total_seconds, remaining_bytes, free_bytes):
    if not all(math.isfinite(v) and v >= 0 for v in (total_seconds, remaining_bytes, free_bytes)):
        raise ValueError('Budget values must be finite and nonnegative')
    required = math.ceil(remaining_bytes * 1.15) + 2 * 1024**3
    return dict(time_gate_passed=total_seconds <= 8*3600,
                storage_gate_passed=free_bytes >= required,
                passed=total_seconds <= 8*3600 and free_bytes >= required,
                estimated_total_seconds=total_seconds, estimated_total_hours=total_seconds/3600,
                estimated_remaining_bytes=remaining_bytes, available_bytes=free_bytes,
                required_free_bytes=required, shortage_bytes=max(0, required-free_bytes))


def measured_trial(job):
    start = time.perf_counter()
    result = trial(job)
    folder = Path(job[2]) / 'runs' / result['run_id']
    return dict(result=result, end_to_end_worker_seconds=time.perf_counter()-start,
                raw_bytes=sum(p.stat().st_size for p in folder.iterdir() if p.is_file()))


def prepare_profiles(p1, out):
    profiles = {}
    completions = {}
    for cls in CLASSES:
        base = p1 / cls
        manifest = json.loads((base / 'complete.json').read_text())
        completions[cls] = sha(base / 'complete.json')
        for name, expected in manifest['files'].items():
            path = (base / name).resolve()
            if not path.is_relative_to(base.resolve()) or sha(path) != expected:
                raise ValueError('P1 artifact mismatch: ' + str(path))
        rel = Path('config/latency_profiles') / out.name / cls
        (ROOT / rel).mkdir(parents=True, exist_ok=False)
        for sel in SELECTORS:
            if not json.loads((base / sel / 'search_regression_faiss_gpu.json').read_text())['passed']:
                raise ValueError('P1 exact-search gate failed')
            shutil.copyfile(base / sel / 'latency_profile_faiss_gpu.json', ROOT / rel / (sel + '.json'))
        profiles[cls] = str(rel)
    return profiles, completions


def estimate(probes, probe_wall, pilot, posthoc_gate, free_bytes):
    with (pilot / 'scenario_results.csv').open() as source:
        baseline = [r for r in csv.DictReader(source) if r['policy'] == 'A']
    if len(baseline) != 15:
        raise ValueError('Expected fifteen baseline A cost references')
    gate = json.loads(posthoc_gate.read_text())
    if not gate['passed'] or gate['pairs'] != 15:
        raise ValueError('Posthoc 15-pair gate failed')
    overhead = max(1., sum(r['end_to_end_worker_seconds'] for r in probes) /
                   sum(r['result']['wall_seconds'] for r in probes))
    baseline_work = sum(float(r['wall_seconds']) * 179 for r in baseline) * overhead
    baseline_bytes = sum(sum(p.stat().st_size for p in (pilot/'runs'/r['run_id']).iterdir()
                             if p.is_file()) * 179 for r in baseline)
    # Each measured seed0 represents the other 29 seeds in its own class/model stratum.
    cap_work = sum(r['end_to_end_worker_seconds'] for r in probes) * 29
    cap_bytes = sum(r['raw_bytes'] for r in probes) * 29
    checks = gate['part_checks']
    post_work = sum((r['read_seconds']+r['compute_seconds']) * 180 for r in checks)
    post_bytes = sum(r['posthoc_output_bytes'] * 180 for r in checks)
    for r in checks:
        if r['cell'] == 'inline' and r['speed'] == .5:
            # Six OFAT views; the 10s service variant can produce up to 3x completions.
            post_work += (r['read_seconds']+r['compute_seconds']) * 90 * 8
            post_bytes += r['posthoc_output_bytes'] * 90 * 8
    total = probe_wall + (baseline_work + cap_work + post_work) / 2 * 1.25
    budget = gate_decision(total, baseline_bytes+cap_bytes+post_bytes, free_bytes)
    budget.update(baseline_remaining=2685, cap_remaining=261, probe_completed=9,
                  pending_DES=2946, posthoc_views=4320,
                  baseline_estimated_bytes=baseline_bytes, cap_estimated_remaining_bytes=cap_bytes,
                  posthoc_estimated_bytes=post_bytes, baseline_worker_seconds=baseline_work,
                  cap_remaining_worker_seconds=cap_work, posthoc_worker_seconds=post_work,
                  measured_probe_wall_seconds=probe_wall, measured_probe_bytes=sum(r['raw_bytes'] for r in probes),
                  measured_end_to_end_overhead_ratio=overhead,
                  time_reserve_fraction=.25, storage_reserve_fraction=.15, storage_fixed_reserve_bytes=2*1024**3,
                  method='Baseline: 15 saved A class/cell/speed strata x179; selector/mode cost proxy. Cap: 9 measured class/model strata x29. Posthoc: saved pair costs with conservative x3 for 10s OFAT. Two workers, 25% time reserve; estimates, not measured full completion.')
    return budget


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--p1', type=Path, required=True)
    parser.add_argument('--pilot', type=Path, required=True)
    parser.add_argument('--posthoc-gate', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    for name in ('p1', 'pilot', 'posthoc_gate', 'out'):
        setattr(args, name, getattr(args, name).resolve())
    if args.out.exists():
        parser.error('Choose a fresh output directory; existing data is preserved')
    reusable_runs(args.pilot, args.p1)
    args.out.mkdir(parents=True, exist_ok=False)
    profiles, completions = prepare_profiles(args.p1, args.out)
    sources = list((ROOT/'aria/simulation/dt').glob('*.py')) + list((ROOT/'aria/simulation/des').glob('*.py'))
    sources += [ROOT/'configs/line_profile.yaml', ROOT/'tools/benchmark_dt.py', Path(__file__)]
    hashes = {str(p.relative_to(ROOT)):sha(p) for p in sources}
    source_hash = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    configs = [c for c in des_plan() if c['scope']=='cap_check' and c['seed']==0]
    assert len(configs)==9
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[name]='4'
    write(args.out/'protocol.json', dict(sim=1, plan=configs, source_hash=source_hash,
        source_hashes=hashes, p1_completions=completions, workers=2, threads_per_worker_max=4,
        user_authorized='2026-10-13: seed0 nine cap runs, then <=8h and 15%+2GiB gate',
        probe_included_in_cap_270=True, policy='A', warmup_s=600, horizon_s=3600))
    start=time.perf_counter()
    jobs=[(c,str(args.p1/c['class_name']),str(args.out),profiles[c['class_name']],source_hash) for c in configs]
    measurements=[]
    with ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context('spawn')) as pool:
        for measurement in pool.map(measured_trial,jobs,chunksize=1):
            measurements.append(measurement)
            write(args.out/'measurements.json', measurements)
            print(f'cap seed0 {len(measurements)}/9 complete',flush=True)
    elapsed=time.perf_counter()-start
    csvwrite(args.out/'scenario_results.csv',[r['result'] for r in measurements])
    budget=estimate(measurements,elapsed,args.pilot,args.posthoc_gate,shutil.disk_usage(args.out).free)
    write(args.out/'cost_gate.json',budget)
    write(args.out/'completion.json',dict(completed=9,expected=9,wall_seconds=elapsed,
        full_matrix_complete=False,new_DES_runs=9,actual_B_DES=0,posthoc_views_executed=0,
        status='cost_gate_passed' if budget['passed'] else 'stopped_at_cost_gate'))
    lines=['# ARIA 상한 seed0 비용 실측 보고서','',
           '상한 270회에 포함되는 9회만 완료했다. 전체 A와 B 사후 계산 완료 보고서가 아니다.', '',
           f"- 실측: 9회 / {elapsed:.2f}초 / {budget['measured_probe_bytes']:,} bytes.",
           f"- 전체 시간 추정: {budget['estimated_total_hours']:.3f}시간. 8시간 게이트: {budget['time_gate_passed']}.",
           f"- 남은 결과 저장량 추정: {budget['estimated_remaining_bytes']:,} bytes.",
           f"- 15% + 2 GiB 포함 필요 여유: {budget['required_free_bytes']:,} bytes.",
           f"- 현재 여유: {budget['available_bytes']:,} bytes. 부족: {budget['shortage_bytes']:,} bytes.",
           f"- 저장 게이트: {budget['storage_gate_passed']}. 전체 게이트: {budget['passed']}.", '',
           '실패 시 사용자 조건에 따라 여기서 중단한다. 기존 자료를 삭제하거나 실험 조건을 축소하지 않는다.', '',
           budget['method'], '',
           '원자료: runs/의 events.jsonl.gz·parts.csv.gz·source_schedule.json·complete.json. 비용 실측: measurements.json. 판단: cost_gate.json.']
    (args.out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(budget,ensure_ascii=False),flush=True)
    return 0 if budget['passed'] else 2


if __name__=='__main__':
    raise SystemExit(main())
