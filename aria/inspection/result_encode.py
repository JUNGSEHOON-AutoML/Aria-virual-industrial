"""검사 결과 텔레메트리 보강 — 2D↔3D 시각화(PiP·Decal)용 image/heatmap/peak 인코딩.

원칙:
 - 추론 로직 불변. 이건 **표현 레이어**(이미 산출된 image 경로 + heatmap 배열을 직렬화).
 - 절대 예외를 던지지 않음 — 실패 시 빈 dict 반환(파이프라인/텔레메트리 차단 금지).
 - 경량: 이미지·heatmap을 작은 해상도로 다운스케일해 WS 대역폭을 억제.
"""
from __future__ import annotations
import base64
import io
from typing import Any

import numpy as np


def _img_to_b64(image: Any, max_px: int = 160) -> str | None:
    """이미지(경로 또는 배열) → 다운스케일 JPEG base64(data URI). 실패 시 None."""
    try:
        from PIL import Image
        if isinstance(image, str):
            im = Image.open(image).convert("RGB")
        elif isinstance(image, np.ndarray):
            arr = image
            if arr.dtype != np.uint8:
                arr = np.clip(arr, 0, 255).astype(np.uint8)
            im = Image.fromarray(arr).convert("RGB")
        else:
            return None
        im.thumbnail((max_px, max_px))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=62)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


def _heatmap_to_b64_and_peak(heatmap: Any, max_px: int = 96):
    """anomaly heatmap(2D float) → (적색 컬러맵 PNG base64, peak 정규화좌표 [nx,ny]).

    낮을수록 정상 로직 불변 — 여기선 단순히 값이 큰(이상) 영역을 붉게 표현만.
    실패 시 (None, None).
    """
    try:
        hm = np.asarray(heatmap, dtype=np.float32)
        if hm.ndim != 2 or hm.size == 0:
            return None, None
        # peak(최대 이상값) 좌표 — decal 역투영 입력
        iy, ix = np.unravel_index(int(np.argmax(hm)), hm.shape)
        ny = float(iy) / max(1, hm.shape[0] - 1)
        nx = float(ix) / max(1, hm.shape[1] - 1)

        # 0..1 정규화 후 적색 알파 컬러맵 RGBA
        mn, mx = float(hm.min()), float(hm.max())
        norm = (hm - mn) / (mx - mn) if mx > mn else np.zeros_like(hm)
        from PIL import Image
        H, W = hm.shape
        rgba = np.zeros((H, W, 4), dtype=np.uint8)
        rgba[..., 0] = 255                                  # R
        rgba[..., 1] = (np.clip(1.0 - norm, 0, 1) * 90).astype(np.uint8)   # 약간의 G(피크=순적색)
        rgba[..., 3] = (np.clip(norm, 0, 1) * 235).astype(np.uint8)        # 알파=이상도
        im = Image.fromarray(rgba, mode="RGBA")
        if max(H, W) < max_px:                              # 업샘플(부드럽게)
            im = im.resize((max_px, max_px), Image.BILINEAR)
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        return b64, [round(nx, 4), round(ny, 4)]
    except Exception:
        return None, None


def _heatmap_blob(heatmap: Any, thresh_ratio: float = 0.6):
    """F-07: heatmap 임계화 → 결함 blob 면적·중심·bbox(정규 0..1). numpy만. 실패 시 None.

    임계 = min + ratio*(max-min). 임계 초과 픽셀 집합을 단일 blob으로 근사(연결성분 의존성 회피).
    """
    try:
        hm = np.asarray(heatmap, dtype=np.float32)
        if hm.ndim != 2 or hm.size == 0:
            return None
        mn, mx = float(hm.min()), float(hm.max())
        if mx <= mn:
            return None
        mask = hm >= (mn + thresh_ratio * (mx - mn))
        ys, xs = np.nonzero(mask)
        if xs.size == 0:
            return None
        H, W = hm.shape
        cx = float(xs.mean()) / max(1, W - 1)
        cy = float(ys.mean()) / max(1, H - 1)
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())
        bbox = [round(x0 / max(1, W - 1), 4), round(y0 / max(1, H - 1), 4),
                round((x1 - x0) / max(1, W - 1), 4), round((y1 - y0) / max(1, H - 1), 4)]
        area = round(float(xs.size) / float(hm.size), 5)   # 전체 대비 면적 비율
        return {"cx": round(cx, 4), "cy": round(cy, 4), "area": area, "bbox": bbox}
    except Exception:
        return None


def enrich_result(image: Any, heatmap: Any) -> dict:
    """워커가 emit 직전 호출. 가용한 것만 담은 dict 반환(없으면 빈 dict).

    반환 키: image_b64?, heatmap_b64?, defect_xy?, defect_blob?  (모두 직렬화 안전)
    """
    out: dict = {}
    img = _img_to_b64(image)
    if img:
        out["image_b64"] = img
    hb64, peak = _heatmap_to_b64_and_peak(heatmap)
    if hb64:
        out["heatmap_b64"] = hb64
    if peak:
        out["defect_xy"] = peak
    blob = _heatmap_blob(heatmap)
    if blob:
        out["defect_blob"] = blob
    return out
