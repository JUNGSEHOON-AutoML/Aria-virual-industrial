import json
import numpy as np
import pytest
from aria.perception import ccifps_backend as cc


def test_bundle_rejects_pending_corruption_and_wrong_features(tmp_path,monkeypatch):
    monkeypatch.setattr(cc,'BUNDLE_ROOT',tmp_path);run='ccifps_'+'a'*32;p=tmp_path/run;p.mkdir();np.save(p/'bank.npy',np.ones((2,768),dtype='f'))
    m={'status':'running','feature_contract':'dino_vit_b8_resize224_D768','bank_sha256':cc.sha(p/'bank.npy')}
    cc.atomic_json(p/'manifest.json',m)
    with pytest.raises(ValueError,match='not completed'):cc.load_bundle(run)
    m['status']='completed';cc.atomic_json(p/'manifest.json',m);assert cc.load_bundle(run)[0]==p/'bank.npy'
    m['feature_contract']='wr50_1024';cc.atomic_json(p/'manifest.json',m)
    with pytest.raises(ValueError,match='incompatible'):cc.load_bundle(run)
    m['feature_contract']='dino_vit_b8_resize224_D768';m['bank_sha256']='wrong';cc.atomic_json(p/'manifest.json',m)
    with pytest.raises(ValueError,match='hash mismatch'):cc.load_bundle(run)

@pytest.mark.parametrize('run',['../bottle','bottle',None,'ccifps_abc'])
def test_bundle_id_validation(run):
    with pytest.raises(ValueError):cc.load_bundle(run)


def test_ccifps_detector_preserves_calibrated_threshold(tmp_path,monkeypatch):
    from aria.inspection.detectors import CCIFPSDetector
    from aria.perception.scorer.feature_bank import _l2
    bank=_l2(np.array([[1,0],[0,1]],dtype='f'));np.save(tmp_path/'bank.npy',bank)
    monkeypatch.setattr(cc,'load_bundle',lambda _: (tmp_path/'bank.npy',{'threshold':.7,'run_id':'test'}))
    d=CCIFPSDetector('test');monkeypatch.setattr(d,'_extract',lambda _:np.array([[1,0]],dtype='f'))
    assert d.tau==.7 and d.infer('unused')['verdict_hint']=='OK'


def test_full_app_registers_ccifps_routes():
    from server.app import create_app
    paths=set(create_app().openapi()['paths'])
    assert {'/api/ccifps/train','/api/ccifps/analyze','/api/ccifps/runs/{run_id}','/api/inspector/start'} <= paths


def test_combined_still_requires_yolo_weights(tmp_path,monkeypatch):
    import asyncio
    from server.routers import inspector
    monkeypatch.setattr(inspector,'MODELS_DIR',tmp_path)
    result=asyncio.run(inspector.start({'mode':'combined','category':'bottle'}))
    assert result['ok'] is False and 'YOLO' in result['error']
