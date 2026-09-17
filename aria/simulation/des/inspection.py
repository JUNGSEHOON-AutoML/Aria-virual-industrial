"""Lazy bridge to ARIA detectors; missing assets are explicitly SKIPPED."""
from pathlib import Path

class InspectionAdapter:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.detectors = {}
        from .evidence import EvidenceStore
        self.evidence = EvidenceStore(self.root)

    def path(self, value, roots):
        p = (self.root / value).resolve()
        if not any(p.is_relative_to((self.root / r).resolve()) for r in roots):
            raise ValueError('Inspection asset must be in data/, uploads/ or banks/')
        if not p.is_file():
            raise ValueError('Inspection asset does not exist')
        return str(p)

    def __call__(self, component, part):
        if not component.image_paths:
            return {'verdict': 'SKIPPED', 'reason': 'No product image configured'}
        image = self.path(component.image_paths[(part['serial'] - 1) % len(component.image_paths)], ['data', 'uploads'])
        key = (component.inspection_mode,component.run_id,component.bank,component.category,component.threshold)
        if key not in self.detectors:
            from aria.inspection.detectors import PatchCoreDetector, CCIFPSDetector, CombinedDetector
            if component.inspection_mode == 'ccifps':
                detector = CCIFPSDetector(component.run_id)
            else:
                bank = self.path(component.bank or f'banks/{component.category}.npy', ['banks'])
                detector = PatchCoreDetector(bank, tau=component.threshold)
                if component.inspection_mode == 'combined':
                    detector = CombinedDetector(detector)
            if len(self.detectors)>=3:
                self.detectors.pop(next(iter(self.detectors)))
            self.detectors[key] = detector
        detector = self.detectors[key]
        result = detector.infer(image)
        tau = getattr(detector, 'tau', component.threshold)
        score = float(result['score'])
        import math
        if not math.isfinite(score) or not math.isfinite(float(tau)):
            raise ValueError('Non-finite detector result')
        metadata = {'verdict': result.get('verdict_hint', 'NG' if score > tau else 'OK'),
                'score': score, 'threshold': tau, 'image': image,
                'mode': component.inspection_mode,
                'note': 'combined uses the existing optional YOLO gate; no YOLO weights loaded' if component.inspection_mode == 'combined' else ''}

        metadata['run_id'] = component.run_id
        metadata['evidence'] = self.evidence.save(image, result, metadata)
        return metadata
