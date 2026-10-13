"""Fixed policy-A DES inventory; human reinspection is an offline view."""
from itertools import product

CLASSES = ('bottle', 'screw', 'carpet')
SELECTORS = ('coreset', 'ccifps', 'random_same_k')
CELLS = (('robot', .5), ('inline', .25), ('inline', .5), ('inline', .75), ('inline', 1.))
VARIANTS = (('reinspection_s', 10.), ('reinspection_s', 60.),
            ('sensitivity', .98), ('sensitivity', .95),
            ('specificity', .98), ('specificity', .95))


def baseline(class_name):
    if class_name not in CLASSES:
        raise ValueError('Unknown class')
    return [dict(class_name=class_name, selector=selector, cell=cell, speed=speed,
                 latency_mode=mode, policy='A', seed=seed, sensitivity=1.,
                 specificity=1., reinspection_s=30., scope='main', defect_rate=.05)
            for selector, (cell, speed), mode, seed in
            product(SELECTORS, CELLS, ('profile', 'constant'), range(30))]


def des_plan():
    main = [c for cls in CLASSES for c in baseline(cls)]
    cap = [dict(class_name=cls, selector=selector, cell='inline', speed=2.,
                latency_mode='profile', policy='A', seed=seed, sensitivity=1.,
                specificity=1., reinspection_s=30., scope='cap_check', defect_rate=.05)
           for cls, selector, seed in product(CLASSES, SELECTORS, range(30))]
    return main + cap


def posthoc_variants(condition):
    """Only baseline gets B views; cap checks do not expand the human sweep."""
    if condition['policy'] != 'A':
        raise ValueError('Posthoc input must be policy A')
    if condition['scope'] not in ('main', 'pilot30'):
        return []
    base = dict(condition, policy='B', sensitivity=1., specificity=1., reinspection_s=30., scope='main')
    result = [base]
    if (condition['cell'], condition['speed'], condition['latency_mode']) == ('inline', .5, 'profile'):
        for field, value in VARIANTS:
            result.append(dict(base, **{field: value, 'scope': 'sensitivity'}))
    return result


def condition_key(condition):
    """Scope is provenance, not a different physical condition for pilot reuse."""
    return tuple(condition[k] for k in ('class_name', 'selector', 'cell', 'speed',
                                       'latency_mode', 'policy', 'seed', 'sensitivity',
                                       'specificity', 'reinspection_s', 'defect_rate'))
