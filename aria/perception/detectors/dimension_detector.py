"""detectors/dimension_detector.py — OpenCV 기반 치수/간격 측정 탐지기.

산업 활용:
  - 부품 간격 측정 및 규격 초과/미달 판정
  - 크기 균일성 검사 (표준편차 기반)
  - 홀 직경, 보스 높이, 가공면 너비 측정
  - 단색 배경 클로즈업 촬영 부품 치수 검사

v4 §1 규칙:
  - applicability()는 image_meta의 domain/scene만 참조.
  - decision은 결정론적: 픽셀 비율 측정값 vs 허용 스펙 비교.
  - 외부 의존성 없음 (OpenCV만 사용).
  - 스펙 없을 때는 상대 균일성(표준편차 비율)으로 이상탐지.
"""
from __future__ import annotations

import os
import time


class DimensionDetector:
    """OpenCV Contour 기반 치수 측정 탐지기.

    modality = "dimension_measurement"
    단색 배경 클로즈업 이미지에서 주요 객체의 크기/간격을 측정한다.
    """

    name     = "dimension_check"
    modality = "dimension_measurement"

    # 치수 측정 관련 키워드
    _DIM_KEYWORDS = {
        "measurement", "dimension", "size", "width", "height", "gap",
        "spacing", "diameter", "radius", "length", "depth", "tolerance",
        "치수", "측정", "크기", "너비", "높이", "간격", "직경", "반경",
        "길이", "깊이", "공차", "규격", "사이즈",
    }

    # ── applicability ──────────────────────────────────────────────────────
    def applicability(self, image_meta: dict, product: dict | None) -> float:
        """단색 배경 클로즈업 부품 이미지에 최적.

        - domain == "dimension" → 0.90
        - scene/primary_object에 치수 키워드 → 0.82
        - enrolled 제품 + dimension_spec 있음 → 0.78
        - industrial_anomaly unenrolled (단순 표면 검사) → 0.35
        - general_object → 0.15
        - 기타 → 0.05
        """
        domain = image_meta.get("domain", "")
        scene  = (image_meta.get("scene", "") + " " +
                  image_meta.get("primary_object", "")).lower()

        if domain == "dimension":
            return 0.90

        for kw in self._DIM_KEYWORDS:
            if kw in scene:
                if product and product.get("dimension_spec"):
                    return 0.82
                return 0.72

        if product and product.get("dimension_spec"):
            return 0.78

        if domain == "industrial_anomaly":
            return 0.35

        if domain == "general_object":
            return 0.15

        return 0.05

    # ── run ───────────────────────────────────────────────────────────────
    def run(self, image_path: str, product: dict | None) -> dict:
        """OpenCV Contour로 주요 객체 치수를 측정하고 스펙과 비교.

        Returns: Detector.run() 표준 스키마
        """
        print("  [DimensionDetector] OpenCV 치수 측정 구동")
        t0 = time.time()

        # 스펙 파라미터 읽기
        dim_spec = product.get("dimension_spec") if product else None
        # dim_spec 예시: {"min_ratio": 0.2, "max_ratio": 0.8, "target_ratio": 0.5, "tolerance": 0.05}

        regions, overlay_path, measurements = self._measure(image_path)
        decision, score = self._decide(measurements, dim_spec)

        elapsed = round(time.time() - t0, 2)
        print(f"  [DimensionDetector] 완료 (측정값={len(measurements)}개, "
              f"decision={decision}, score={score:.3f}, {elapsed}s)")

        return {
            "score"        : score,
            "threshold"    : float(dim_spec.get("tolerance", 0.1)) if dim_spec else 0.15,
            "decision"     : decision,
            "confidence"   : 0.75,
            "render_type"  : "heatmap",
            "overlay_path" : overlay_path,
            "regions"      : regions,
            "model_name"   : "Dimension Checker (OpenCV Contour)",
            # 치수 전용 추가 필드
            "measurements" : measurements,
            "dimension_spec": dim_spec,
        }

    # ── 측정 로직 ─────────────────────────────────────────────────────────

    def _measure(self, image_path: str) -> tuple[list, str | None, list]:
        """OpenCV Contour로 주요 객체 경계를 찾고 치수를 측정."""
        import cv2
        import numpy as np
        from datetime import datetime
        from pathlib import Path

        try:
            img = cv2.imread(image_path)
            if img is None:
                return [], None, []

            h, w = img.shape[:2]
            image_area = h * w

            gray    = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges   = cv2.Canny(blurred, 50, 150)

            # 팽창으로 엣지 연결
            kernel  = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            dilated = cv2.dilate(edges, kernel, iterations=2)

            contours, _ = cv2.findContours(
                dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            # 의미 있는 컨투어 필터링 (면적 0.5%~60% 범위)
            valid = [
                c for c in contours
                if image_area * 0.005 < cv2.contourArea(c) < image_area * 0.60
            ]
            valid.sort(key=cv2.contourArea, reverse=True)
            valid = valid[:8]  # 상위 8개만

            vis        = img.copy()
            regions    = []
            measurements = []

            for i, c in enumerate(valid):
                x, y, bw, bh = cv2.boundingRect(c)

                # 정규화 비율 (이미지 크기 대비)
                w_ratio = round(bw / w, 4)
                h_ratio = round(bh / h, 4)
                area_ratio = round(cv2.contourArea(c) / image_area, 4)

                # 회전 사각형으로 정밀 측정
                rect      = cv2.minAreaRect(c)
                box_pts   = cv2.boxPoints(rect)
                rect_w    = round(rect[1][0], 1)
                rect_h    = round(rect[1][1], 1)
                angle     = round(rect[2], 1)

                region = {
                    "label"        : f"object_{i + 1}",
                    "bbox"         : [x, y, bw, bh],
                    "w_ratio"      : w_ratio,
                    "h_ratio"      : h_ratio,
                    "area_ratio"   : area_ratio,
                    "rect_angle"   : angle,
                    "px_width"     : int(rect_w),
                    "px_height"    : int(rect_h),
                    "valid"        : True,
                }
                regions.append(region)
                measurements.append({
                    "id"        : i + 1,
                    "w_ratio"   : w_ratio,
                    "h_ratio"   : h_ratio,
                    "area_ratio": area_ratio,
                })

                # 오버레이: 컨투어 + 측정값 텍스트
                color = (0, 200, 80)
                cv2.rectangle(vis, (x, y), (x + bw, y + bh), color, 2)
                cv2.drawContours(vis, [box_pts.astype(int)], 0, (200, 80, 0), 1)
                label_text = f"#{i+1} W:{w_ratio:.2f} H:{h_ratio:.2f}"
                cv2.putText(vis, label_text, (x, max(y - 6, 12)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

            # 균일성 분석 (w_ratio 표준편차)
            if len(measurements) >= 2:
                w_ratios = [m["w_ratio"] for m in measurements]
                std_w    = float(np.std(w_ratios))
                mean_w   = float(np.mean(w_ratios))
                cv2.putText(vis,
                    f"Uniformity CV: {std_w/max(mean_w,1e-6):.3f}",
                    (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (200, 200, 50), 1)

            # 오버레이 저장
            out_dir = Path(image_path).resolve().parent.parent / "outputs"
            out_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = str(out_dir / f"dimension_{ts}.jpg")
            cv2.imwrite(out_path, vis)

            return regions, out_path, measurements

        except Exception as e:
            print(f"  [DimensionDetector] 측정 오류: {e}")
            return [], None, []

    # ── 판정 (결정론적) ───────────────────────────────────────────────────

    @staticmethod
    def _decide(measurements: list, dim_spec: dict | None) -> tuple[str, float]:
        """측정값과 스펙을 비교해 pass/fail/n/a 결정."""
        if not measurements:
            return "n/a", 0.0

        import numpy as np

        if dim_spec is None:
            # 스펙 없음 → 균일성(CV)으로 상대 판정
            if len(measurements) < 2:
                return "n/a", 0.0
            w_ratios = [m["w_ratio"] for m in measurements]
            cv_val   = float(np.std(w_ratios) / max(np.mean(w_ratios), 1e-6))
            # CV > 0.20 이면 비균일 → fail
            if cv_val > 0.20:
                return "fail", round(min(cv_val, 1.0), 4)
            return "pass", round(cv_val, 4)

        # 스펙 기반 판정
        target    = float(dim_spec.get("target_ratio", 0.5))
        tolerance = float(dim_spec.get("tolerance", 0.05))
        min_r     = float(dim_spec.get("min_ratio", target - tolerance))
        max_r     = float(dim_spec.get("max_ratio", target + tolerance))

        violations = []
        for m in measurements:
            wr = m["w_ratio"]
            if not (min_r <= wr <= max_r):
                violations.append(abs(wr - target))

        if not violations:
            return "pass", 0.0

        max_dev = max(violations)
        score   = round(min(max_dev / max(tolerance, 1e-6), 1.0), 4)
        return "fail", score
