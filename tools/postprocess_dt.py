"""Evaluate saved policy-A runs as offline B views; never execute DES."""
import argparse
import csv
import gzip
import json
from pathlib import Path

from aria.simulation.dt.plan import posthoc_variants
from aria.simulation.dt.posthoc import reconstruct_b
from tools.run_dt_matrix import sha

NUMERIC = ('born', 'inspection_time', 'reinspection_time', 'exit_time',
           'mainline_exit_time', 'reinspection_queue_enter', 'reinspection_start')


def load_run(folder, p1):
    done = json.loads((folder / 'complete.json').read_text())
    config = done['lock']['config']
    if config['policy'] != 'A':
        raise ValueError('Only saved policy A runs may be postprocessed')
    for name, digest in done['hashes'].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha(path) != digest:
            raise ValueError('Saved run hash mismatch: ' + name)
    gt = (p1 / config['class_name'] / 'gt_labels.csv').resolve()
    if done['lock']['inputs'].get(str(gt)) != sha(gt):
        raise ValueError('GT does not match the saved input')
    with gzip.open(folder / 'parts.csv.gz', 'rt') as source:
        parts = list(csv.DictReader(source))
    for part in parts:
        for key in NUMERIC:
            part[key] = float(part[key]) if part[key] else None
        for key in ('ai_verdict', 'reinspection_verdict', 'route'):
            part[key] = part[key] or None
    return config, parts, gt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True, help='Saved policy-A runs/<id> directory')
    parser.add_argument('--p1', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Output already exists; choose a new path to preserve existing artifacts')
    config, parts, gt = load_run(args.run.resolve(), args.p1.resolve())
    views = posthoc_variants(config)
    if not views:
        parser.error('Cap checks do not have B or reinspection sensitivity views')
    args.out.mkdir(parents=True, exist_ok=False)
    rows = []
    for index, variant in enumerate(views):
        _, metrics, normalized, events = reconstruct_b(
            parts, gt, seed=config['seed'], service_seconds=variant['reinspection_s'],
            sensitivity=variant['sensitivity'], specificity=variant['specificity'])
        rows.append({**variant, **normalized, **metrics})
        (args.out / f'view_{index}.json').write_text(json.dumps(
            dict(config=variant, metrics=metrics, normalized=normalized, events=events),
            indent=2, allow_nan=False) + '\n')
    with (args.out / 'posthoc_results.csv').open('w') as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (args.out / 'completion.json').write_text(json.dumps(dict(
        sim=1, source_run=str(args.run.resolve()), source_complete_sha256=sha(args.run / 'complete.json'),
        views=len(rows), new_DES_runs=0, policy='B_posthoc',
        implementation_sha256=sha(Path(__file__).resolve().parents[1] / 'aria/simulation/dt/posthoc.py')),
        indent=2) + '\n')
    print(json.dumps(dict(views=len(rows), new_DES_runs=0)))


if __name__ == '__main__':
    main()
