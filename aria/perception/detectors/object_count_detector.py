"""detectors/object_count_detector.py — 객체 수량 카운팅 탐지기 플러그인.

산업 활용:
  - 생산라인 부품 수량 불일치 감지 (볼트/너트 누락)
  - 포장 내 알약 수 확인
  - 다수 동일 객체 배열 균일성 검사

v4 §1 규칙:
  - applicability()는 무거운 추론 금지 — image_meta의 domain/scene만 참조.
  - decision은 결정론적: 기대 수량 ± 허용범위 초과 → fail, 미만 → pass.
  - 기대 수량 정보가 없으면 decision="n/a" (탐지 목록만 반환).
  - YOLO 실패 시 단순 Contour 카운팅으로 fallback.
"""
from __future__ import annotations

import os
import time


class ObjectCountDetector:
    """YOLO 기반 객체 수량 카운팅 탐지기.

    modality = "object_counting"
    다중 동일 객체가 배열된 이미지에서 수량을 세고, 기대 수량과 비교한다.
    """

    name = "object_count"
    modality = "object_counting"

    # 카운팅 도메인 키워드 — scene/primary_object에서 탐지
    _COUNT_KEYWORDS = {
        "pill", "tablet", "capsule", "bolt", "nut", "screw", "rivet",
        "ball", "bearing", "chip", "pcb", "component", "package",
        "알약", "정제", "볼트", "너트", "나사", "부품", "패키지", "베어링",
        "칩", "구슬", "캡슐", "포장",
    }

    # ── applicability ──────────────────────────────────────────────────────
    def applicability(self, image_meta: dict, product: dict | None) -> float:
        """다중 동일 객체가 있는 이미지에 최적.

        - enrolled 제품 + surface_anomaly → 0.05 (CMDIAD가 담당)
        - domain == "counting" → 0.92
        - scene/primary_object에 카운팅 관련 키워드 → 0.85
        - domain == "industrial_anomaly" + unenrolled → 0.30 (보조)
        - general_object → 0.35
        - 기타 → 0.10
        """
        # 등록 제품 표면 이상탐지는 CMDIAD가 담당
        if product and product.get("status") == "enrolled":
            return 0.05

        domain = image_meta.get("domain", "")
        scene  = (image_meta.get("scene", "") + " " + image_meta.get("primary_object", "")).lower()

        if domain == "counting":
            return 0.92

        # 카운팅 키워드 탐지
        for kw in self._COUNT_KEYWORDS:
            if kw in scene:
                return 0.85

        if domain == "industrial_anomaly":
            return 0.30
        if domain == "general_object":
            return 0.35

        return 0.10

    # ── run ───────────────────────────────────────────────────────────────
    def run(self, image_path: str, product: dict | None) -> dict:
        """YOLO로 객체를 탐지하고 클래스별로 수량을 집계한다.

        product dict에 expected_count, tolerance 필드가 있으면
        결정론적 pass/fail 판정. 없으면 n/a.

        Returns: Detector.run() 표준 스키마
        """
        print("  [ObjectCountDetector] YOLO 기반 수량 카운팅 구동")
        t0 = time.time()

        # 기대 수량 파라미터 (product dict 또는 기본값)
        expected_count = None
        tolerance      = 0
        if product:
            expected_count = product.get("expected_count")
            tolerance      = int(product.get("count_tolerance", 0))

        detections = []
        overlay_path = None
        model_name = "ObjectCount (YOLOv8n)"

        # ── YOLO 추론 시도 ──────────────────────────────────────────────
        try:
            from aria.perception.vision_router import _run_yolo
            yolo_res = _run_yolo(image_path, "yolov8n", "yolov8n.pt")

            if yolo_res.get("status") == "success":
                raw_dets   = yolo_res.get("detections", [])
                overlay_path = yolo_res.get("result_image_path")
                detections = self._aggregate_counts(raw_dets)
                print(f"  [ObjectCountDetector] YOLO 탐지 완료: {detections}")
            else:
                raise RuntimeError(f"YOLO 실패: {yolo_res.get('error', '알 수 없음')}")

        except Exception as e:
            print(f"  [ObjectCountDetector] YOLO 실패 ({e}) → OpenCV Contour fallback")
            detections, overlay_path = self._opencv_count_fallback(image_path)
            model_name = "ObjectCount (OpenCV Contour Fallback)"

        # ── 결정론적 판정 ───────────────────────────────────────────────
        total_count = sum(d.get("count", 0) for d in detections)
        decision, score = self._decide(total_count, expected_count, tolerance)

        elapsed = round(time.time() - t0, 2)
        print(f"  [ObjectCountDetector] 완료 (total={total_count}, "
              f"expected={expected_count}, decision={decision}, {elapsed}s)")

        return {
            "score"        : score,
            "threshold"    : float(expected_count) if expected_count is not None else 0.0,
            "decision"     : decision,
            "confidence"   : 0.80,
            "render_type"  : "bounding_box",
            "overlay_path" : overlay_path,
            "regions"      : detections,
            "model_name"   : model_name,
            # 카운팅 전용 추가 필드
            "total_count"  : total_count,
            "expected_count": expected_count,
        }

    # ── 헬퍼 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _aggregate_counts(raw_dets: list) -> list:
        """YOLO detection 목록을 클래스별로 집계."""
        counts: dict[str, dict] = {}
        for det in raw_dets:
            cls = det.get("class", det.get("label", "object"))
            if cls not in counts:
                counts[cls] = {"class": cls, "count": 0, "boxes": []}
            counts[cls]["count"] += 1
            box = det.get("bbox") or det.get("box")
            if box:
                counts[cls]["boxes"].append(box)
        return list(counts.values())

    @staticmethod
    def _decide(total: int, expected: int | None, tolerance: int) -> tuple[str, float]:
        """총 수량과 기대 수량을 비교해 결정과 점수 반환."""
        if expected is None:
            return "n/a", 0.0
        diff = abs(total - expected)
        if diff <= tolerance:
            return "pass", 0.0
        # 정규화 점수: 기대 수량 대비 오차 비율 (0~1)
        score = min(diff / max(expected, 1), 1.0)
        return "fail", round(score, 4)

    @staticmethod
    def _opencv_count_fallback(image_path: str) -> tuple[list, str | None]:
        """OpenCV Contour로 객체 수를 추정하는 fallback."""
        import cv2
        import numpy as np
        from datetime import datetime
        from pathlib import Path

        try:
            img = cv2.imread(image_path)
            if img is None:
                return [], None

            gray    = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (7, 7), 0)
            _, thresh = cv2.threshold(blurred, 0, 255,
                                      cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            # 노이즈 제거
            kernel  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            cleaned = cv2.morphologyEx(thresh, cv2.MORPH_OPEN,  kernel, iterations=2)
            cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel, iterations=2)

            contours, _ = cv2.findContours(
                cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # 너무 작은 컨투어 제거
            h, w = img.shape[:2]
            min_area = (h * w) * 0.002
            valid = [c for c in contours if cv2.contourArea(c) > min_area]

            # 오버레이 이미지 생성
            vis = img.copy()
            for i, c in enumerate(valid):
                x, y, bw, bh = cv2.boundingRect(c)
                cv2.rectangle(vis, (x, y), (x + bw, y + bh), (0, 200, 100), 2)
                cv2.putText(vis, str(i + 1), (x, y - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 100), 1)
            cv2.putText(vis, f"Count: {len(valid)} (OpenCV Fallback)",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 140, 255), 2)

            out_dir = Path(image_path).resolve().parent.parent / "outputs"
            out_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = str(out_dir / f"count_fallback_{ts}.jpg")
            cv2.imwrite(out_path, vis)

            return [{"class": "object", "count": len(valid), "boxes": []}], out_path

        except Exception as ex:
            print(f"  [ObjectCountDetector] OpenCV fallback도 실패: {ex}")
            return [], None
