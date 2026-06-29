"""디텍터 레지스트리 — 플러그형 검출기 (ARIA_Vision_Inspection_Node_Spec 신규2).

두 검출기를 플러그형으로 운영(단독/결합):
- PatchCoreDetector (기본, 비지도): good 뱅크로 anomaly_score + heatmap. 라벨 불필요.
- Yolo26Detector  (지도): 결함 종류를 bbox로 분류·검출. (yolo_dataset_builder + 학습 후 연결)

결합 정책(CombinedDetector): PatchCore가 이상 게이트(score>τ) → 이상일 때만 YOLO26로
결함 종류/위치(bbox) 분류. 두 결과를 합쳐 최종 {verdict, score, heatmap, defect_class, bbox}.

추론 알고리즘 재작성 금지(§11 DON'T): PatchCore는 기존
`aria.perception.scorer.feature_bank` + `aria.core.config.backbone` 를 그대로 재사용.
heatmap은 기존 패치별 anomaly 값을 정사각 맵으로 reshape한 것(동일 수식).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

import numpy as np


# ─────────────────────────── 디텍터 인터페이스 ───────────────────────────
class Detector(ABC):
    name: str = "detector"

    @abstractmethod
    def infer(self, image: Any) -> dict:
        """image(경로 또는 배열) → {score, heatmap, defect_class?, bbox?}."""

    def as_infer_fn(self, extra_latency_ms: float = 0.0) -> Callable[[Any], dict]:
        """AsyncPipeline.infer_fn 어댑터. extra_latency_ms로 '느린 추론' 인위 주입(§10-1 증명)."""
        import time

        def _fn(image: Any) -> dict:
            out = self.infer(image)
            if extra_latency_ms > 0:
                time.sleep(extra_latency_ms / 1000.0)
            return out

        return _fn


# ─────────────────────────── PatchCore (비지도) ───────────────────────────
def _score_and_map(feats, bank: np.ndarray):
    """기존 feature_bank와 동일 수식으로 (이미지 score, 패치 anomaly map) 동시 산출.

    cosine_score_features는 max만 반환하므로, 같은 정규화(_l2)·코사인으로 패치맵을 추가 노출.
    (수식 동일 — 재작성 아님, 패치값을 맵으로 드러낼 뿐)."""
    from aria.perception.scorer.feature_bank import _l2, _np

    f = _l2(_np(feats))                 # [N, D] L2 정규화
    sims = f @ bank.T                   # [N, M] 코사인 유사도
    patch_anom = 1.0 - sims.max(axis=1)  # [N] 패치별 (1 − 최대유사도)
    score = float(patch_anom.max())     # 이미지 점수 = 최악 패치
    n = patch_anom.shape[0]
    side = int(round(n ** 0.5))
    if side * side == n:
        heatmap = patch_anom.reshape(side, side).astype(np.float32)  # 예: 28×28
    else:
        heatmap = patch_anom.astype(np.float32)
    return score, heatmap


class PatchCoreDetector(Detector):
    """비지도 이상탐지. good 뱅크(npy)와 기존 백본을 재사용."""

    name = "patchcore"

    def __init__(self, bank: Any, tau: float = 0.5):
        # bank: npy 경로(str) 또는 np.ndarray
        self.bank = np.load(bank) if isinstance(bank, str) else np.asarray(bank)
        self.tau = tau
        self._backbone = None

    def _extract(self, image_path: str):
        if self._backbone is None:
            from aria.core.config.backbone import get_backbone
            self._backbone = get_backbone()
        return self._backbone.extract_features(image_path)

    def infer(self, image: Any) -> dict:
        feats = self._extract(image)
        score, heatmap = _score_and_map(feats, self.bank)
        return {
            "score": score,
            "heatmap": heatmap,
            "verdict_hint": "NG" if score > self.tau else "OK",
        }


# ─────────────────────────── YOLO26 (지도, 결함 분류) ───────────────────────────
class YoloDetector(Detector):
    """결함 종류 bbox 검출. yolo_dataset_builder로 만든 data.yaml 학습 후 weights 연결.

    모델은 무관(yolo11/yolov8/yolo26 등). 기본 yolo11n(안정·경량). 학습 산출 weights 지정 권장."""

    name = "yolo"

    def __init__(self, weights: str = "yolo11n.pt", conf: float = 0.25):
        try:
            from ultralytics import YOLO
        except ImportError as e:
            raise ImportError("ultralytics 미설치 — `pip install ultralytics`") from e
        self.model = YOLO(weights)
        self.conf = conf

    def infer(self, image: Any) -> dict:
        r = self.model.predict(image, conf=self.conf, verbose=False)[0]
        boxes = []
        names = r.names if hasattr(r, "names") else {}
        for b in r.boxes:
            cls = int(b.cls[0])
            xywh = [float(v) for v in b.xywh[0].tolist()]
            boxes.append({"class": names.get(cls, str(cls)), "conf": float(b.conf[0]), "bbox": xywh})
        top = max(boxes, key=lambda x: x["conf"]) if boxes else None
        return {
            "defect_class": top["class"] if top else None,
            "bbox": top["bbox"] if top else None,
            "boxes": boxes,
        }


# ─────────────────────────── 결합 정책 ───────────────────────────
class CombinedDetector(Detector):
    """PatchCore 게이트(score>τ) → 이상일 때만 YOLO26 분류. 결과 병합."""

    name = "patchcore+yolo26"

    def __init__(self, patchcore: PatchCoreDetector, yolo: Optional["YoloDetector"] = None,
                 tau: Optional[float] = None):
        self.patchcore = patchcore
        self.yolo = yolo
        self.tau = tau if tau is not None else patchcore.tau

    def infer(self, image: Any) -> dict:
        pc = self.patchcore.infer(image)
        out = {"score": pc["score"], "heatmap": pc.get("heatmap"),
               "defect_class": None, "bbox": None}
        if pc["score"] > self.tau and self.yolo is not None:   # 이상 게이트 통과 시에만 YOLO
            yo = self.yolo.infer(image)
            out["defect_class"] = yo.get("defect_class")
            out["bbox"] = yo.get("bbox")
            out["boxes"] = yo.get("boxes")
        return out


Yolo26Detector = YoloDetector   # 하위호환 별칭 (모델은 무관)


# ─────────────────────────── 레지스트리 ───────────────────────────
class DetectorRegistry:
    def __init__(self):
        self._d: dict = {}

    def register(self, detector: Detector, name: Optional[str] = None):
        self._d[name or detector.name] = detector
        return detector

    def get(self, name: str) -> Detector:
        if name not in self._d:
            raise KeyError(f"디텍터 '{name}' 미등록. 등록됨: {list(self._d)}")
        return self._d[name]

    def names(self) -> list:
        return list(self._d)


# ─────────────────────────── 런타임 증명: 실제 patchcore로 비병목 (§10-1,2,5) ───────────────────────────
def _collect_labeled(category_dir: str, per_group: int = 20):
    """test/ 에서 good / 결함을 분리 수집 → (good_paths, defect_paths)."""
    import glob
    import os
    exts = (".png", ".jpg", ".jpeg", ".bmp")
    good, defect = [], []
    for sub in sorted(glob.glob(os.path.join(category_dir, "test", "*"))):
        if not os.path.isdir(sub):
            continue
        files = [p for p in sorted(glob.glob(os.path.join(sub, "*"))) if p.lower().endswith(exts)]
        if os.path.basename(sub).lower() == "good":
            good += files
        else:
            defect += files
    return good[:per_group], defect[:per_group]


def _interleave(good: list, defect: list) -> list:
    """good/결함을 번갈아 섞어 라인 인입 순서를 현실적으로(연속 동일라벨 방지)."""
    out = []
    for i in range(max(len(good), len(defect))):
        if i < len(good):
            out.append(good[i])
        if i < len(defect):
            out.append(defect[i])
    return out


def _prove_patchcore_nonblocking():
    import time
    from aria.inspection.async_pipeline import AsyncPipeline, MockDriver

    BANK = "banks/bottle.npy"
    CAT = "data/bottle"
    TAU = 0.5
    good, defect = _collect_labeled(CAT, per_group=20)
    imgs = _interleave(good, defect)
    print("=" * 74)
    print(f"실제 PatchCore 증명 — category=bottle, good {len(good)} / 결함 {len(defect)}, τ={TAU}")
    print("=" * 74)

    det = PatchCoreDetector(BANK, tau=TAU)
    # 백본 웜업(첫 추론 가중치 로드 비용 제외)
    t0 = time.perf_counter()
    _ = det.infer(imgs[0])
    print(f"  백본 웜업 1장: {(time.perf_counter()-t0)*1000:.0f}ms (이후 정상 latency)")

    # ── §10-2 정확도: good은 pass, NG는 fail + heatmap 산출 확인 ──
    hm_shape = None
    good_ok = 0
    for p in good:
        r = det.infer(p)
        if hm_shape is None and r.get("heatmap") is not None:
            hm_shape = getattr(r["heatmap"], "shape", None)
        if r["score"] <= TAU:
            good_ok += 1
    ng_hit = sum(1 for p in defect if det.infer(p)["score"] > TAU)
    print(f"  §10-2 정확도 | good→pass {good_ok}/{len(good)} · 결함→NG {ng_hit}/{len(defect)} "
          f"· heatmap shape={hm_shape}")

    def run(extra_ms, label, line_interval_ms=80.0, n=40, workers=2, q=4):
        pipe = AsyncPipeline(MockDriver(grab_ms=2.0, image_paths=imgs),
                             det.as_infer_fn(extra_latency_ms=extra_ms),
                             tau=TAU, queue_capacity=q, n_workers=workers)
        pipe.start()
        for _ in range(n):
            t = time.perf_counter()
            pipe.trigger()
            rem = line_interval_ms - (time.perf_counter() - t) * 1000.0
            if rem > 0:
                time.sleep(rem / 1000.0)
        pipe.drain(timeout=10.0)
        snap = pipe.snapshot()
        pipe.stop()
        snap["_label"] = label
        return snap

    base = run(0.0, "실제 추론")
    slow = run(600.0, "추론 +600ms(≈5×)")

    def row(s):
        return (f"  {s['_label']:<18} | ack max={s['ack_max_ms']:>6.2f}ms | "
                f"infer p95={s['infer_latency_p95_ms']:>7.1f}ms | drop={s['drop_count']:>3} "
                f"skip={s['n_skipped']:>3} | OK={s['n_ok']} NG={s['n_ng']}")

    print(row(base))
    print(row(slow))
    print("-" * 74)
    SLA = 20.0
    ok_ack = base["ack_max_ms"] < SLA and slow["ack_max_ms"] < SLA
    grew = slow["infer_latency_p95_ms"] > base["infer_latency_p95_ms"] * 2
    bp = slow["drop_count"] > 0
    acc_ok = good_ok >= 0.8 * len(good) and ng_hit >= 0.8 * len(defect)  # §10-2
    verdict = "PASS" if (ok_ack and grew and bp and acc_ok) else "FAIL"
    print(f"  §10-1 추론 p95 {base['infer_latency_p95_ms']:.0f}→{slow['infer_latency_p95_ms']:.0f}ms 인데 "
          f"트리거 ack max {base['ack_max_ms']:.2f}→{slow['ack_max_ms']:.2f}ms (둘 다 <{SLA:.0f}ms)")
    print(f"  과부하분 drop={slow['drop_count']}(SKIPPED) 흡수 — 라인 미정지")
    print(f"\n  [{verdict}] 실제 PatchCore: 비병목(§10-1) + 정확도(§10-2) + MockDriver end-to-end(§10-5)")
    print("=" * 74)
    return verdict == "PASS"


if __name__ == "__main__":
    import sys
    sys.exit(0 if _prove_patchcore_nonblocking() else 1)
