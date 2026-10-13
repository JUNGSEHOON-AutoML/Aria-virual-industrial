"""Assumed human inspection model. The only control-side GT reader.

Not an AI model, measured human accuracy, or a deployable quality controller.
"""
import csv,hashlib,random
from pathlib import Path

class ReinspectOracle:
    def __init__(self,gt_path,*,seed,sensitivity=1.,specificity=1.):
        if gt_path is None or not Path(gt_path).is_file():raise ValueError('Policy B requires GT for reinspect_oracle')
        if not 0<=sensitivity<=1 or not 0<=specificity<=1:raise ValueError('Invalid assumed sensitivity/specificity')
        self.seed=seed;self.sensitivity=sensitivity;self.specificity=specificity
        self.labels={}
        with Path(gt_path).open() as f:
            for r in csv.DictReader(f):
                if r['is_defect'] not in ('0','1') or r['image_id'] in self.labels:raise ValueError('Invalid or duplicate GT')
                self.labels[r['image_id']]=int(r['is_defect'])
        self.gt_sha256=hashlib.sha256(Path(gt_path).read_bytes()).hexdigest()
    def validate_images(self,ids):
        if any(i not in self.labels for i in ids):raise ValueError('Missing reinspect_oracle GT for prediction ID')
    def inspect(self,*,image_id,part_id):
        actual=self.labels[image_id]
        key=f'aria-human-v1:{self.seed}:{part_id}:{image_id}'
        u=random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest(),'big')).random()
        reject=u<self.sensitivity if actual else u>=self.specificity
        return dict(verdict='NG' if reject else 'OK',source='reinspect_oracle',mode='assumed_human',
                    sensitivity=self.sensitivity,specificity=self.specificity,parameter_source='assumed',
                    gt_sha256=self.gt_sha256,rng_policy='seed/part/image keyed independent stream')
