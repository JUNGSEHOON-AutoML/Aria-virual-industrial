import asyncio
import io
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.datastructures import UploadFile
from aria.perception.scorer.feature_bank import _l2, cosine_patch_scores, cosine_score_features
from aria.inspection.detectors import _score_and_map

@pytest.mark.parametrize('n,m,d',[(1,1,3),(17,13,9),(784,4000,768)])
def test_scores_match_dense(n,m,d):
    rng=np.random.default_rng(5);f=rng.normal(size=(n,d)).astype('f');b=_l2(rng.normal(size=(m,d)).astype('f'))
    expected=1-(_l2(f)@b.T).max(1)
    np.testing.assert_allclose(cosine_patch_scores(f,b),expected,rtol=1e-6,atol=1e-6)
    score,hm=_score_and_map(f,b)
    np.testing.assert_allclose(hm.ravel(),expected,rtol=1e-6,atol=1e-6)
    assert abs(score-cosine_score_features(f,b)) < 1e-7

@pytest.mark.parametrize('f,b',[(np.zeros((0,4)),np.ones((2,4))),(np.zeros((2,4)),np.ones((0,4))),(np.zeros((2,4)),np.ones((2,3))),(np.full((2,4),np.nan),np.ones((2,4)))])
def test_invalid_arrays(f,b):
    with pytest.raises(ValueError):cosine_patch_scores(f,b)

@pytest.mark.parametrize('category,tau',[('../banks/x',.5),(['bottle'],.5),('bottle','nan'),('bottle','inf')])
def test_invalid_request(category,tau):
    from server.routers import analyze as mod
    async def run():
        app=FastAPI();app.include_router(mod.router)
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as c:
            res=await c.post('/api/analyze_path',json={'category':category,'tau':tau})
            assert res.status_code==422
    asyncio.run(run())

def test_path_prefix_escape(tmp_path,monkeypatch):
    from server.routers import analyze as mod
    root=tmp_path/'root';root.mkdir();other=tmp_path/'root-evil';other.mkdir();image=other/'x.png';image.write_bytes(b'x');(root/'bottle.npy').write_bytes(b'x')
    monkeypatch.setattr(mod,'ROOT',root);monkeypatch.setattr(mod,'DATA_ROOT',root);monkeypatch.setattr(mod,'BANKS_DIR',root)
    assert asyncio.run(mod.analyze_path({'path':str(image),'category':'bottle'}))['ok'] is False

def test_slow_inference_does_not_block_api(tmp_path,monkeypatch):
    from server.routers import analyze as mod
    (tmp_path/'bottle.npy').write_bytes(b'x');image=tmp_path/'x.png';image.write_bytes(b'x')
    monkeypatch.setattr(mod,'ROOT',tmp_path);monkeypatch.setattr(mod,'DATA_ROOT',tmp_path);monkeypatch.setattr(mod,'BANKS_DIR',tmp_path)
    def slow(*args):time.sleep(.25);return {'score':.5,'_encoded':{}}
    monkeypatch.setattr(mod,'_run_inference',slow)
    async def run():
        app=FastAPI();app.include_router(mod.router)
        @app.get('/heartbeat')
        async def heartbeat():return {'alive':True}
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as c:
            task=asyncio.create_task(c.post('/api/analyze_path',json={'path':str(image)}));await asyncio.sleep(.03)
            assert not task.done(), 'inference blocked event loop'
            assert (await c.get('/heartbeat')).json()['alive']
            result=(await task).json();assert result['verdict']=='OK' # Preserve strict > tau.
    asyncio.run(run())

def test_uploads_do_not_collide(tmp_path,monkeypatch):
    from server.routers import analyze as mod
    (tmp_path/'bottle.npy').write_bytes(b'x');monkeypatch.setattr(mod,'BANKS_DIR',tmp_path);monkeypatch.setattr(mod,'UPLOAD_DIR',tmp_path)
    monkeypatch.setattr(mod,'_run_inference',lambda *args:{'score':.6,'heatmap':np.zeros((2,2))})
    async def run():
        for _ in range(2):await mod.analyze(UploadFile(filename='x.png',file=io.BytesIO(b'image')),category='bottle',tau=.5)
    asyncio.run(run());assert len(list(tmp_path.glob('analyze_*.png')))==2
