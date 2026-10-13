"""Project CLI for OpenUSD 26.8's official UsdValidation validators.

The PyPI usd-core wheel has no upstream usdchecker executable. This adapter
reports that fact explicitly and uses every registered official validator,
including missing references/materials/units. It also checks each CAD variant.
"""
import argparse
import json
from pathlib import Path
from pxr import Usd, UsdValidation


def check(path):
    registry = UsdValidation.ValidationRegistry()
    validators = registry.GetOrLoadAllValidators()
    context = UsdValidation.ValidationContext(validators)
    stage = Usd.Stage.Open(str(path))
    if not stage:
        raise ValueError(f'Cannot open USD: {path}')
    runs = []
    def validate(label):
        issues = [e for e in context.Validate(stage) if not e.HasNoError()]
        runs.append({'selection': label, 'issues': [dict(type=str(e.GetType()), message=e.GetMessage()) for e in issues]})
    validate('default')
    # No variants are written back to disk by this read-only checker.
    stage.SetEditTarget(stage.GetSessionLayer())
    variants = [(p.GetPath(), name) for p in stage.Traverse() for name in p.GetVariantSets().GetNames()]
    for prim_path, name in variants:
        vs = stage.GetPrimAtPath(prim_path).GetVariantSet(name)
        original = vs.GetVariantSelection()
        for value in vs.GetVariantNames():
            vs.SetVariantSelection(value)
            validate(f'{prim_path}:{name}={value}')
        vs.SetVariantSelection(original)
    return {'pass': all(not r['issues'] for r in runs),
            'engine': 'OpenUSD UsdValidation; project CLI adapter (wheel has no upstream usdchecker binary)',
            'version': list(Usd.GetVersion()), 'validators': sorted(m.name for m in registry.GetAllValidatorMetadata()),
            'file': Path(path).name, 'runs': runs}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    report = check(args.path)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['pass'] else 1)
