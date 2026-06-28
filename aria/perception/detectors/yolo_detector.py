"""detectors/yolo_detector.py — YOLOv8 객체탐지 플러그인.

v4 §1 규칙:
- YOLO는 이상탐지(수치 점수)가 아니라 객체탐지용.
- decision은 항상 "n/a" — YOLO 바운딩박스로 pass/fail을 선언하지 않는다.
- 가짜 점수(len(detections) * 상수) 생성 금지.
- enrolled 제품에는 applicability 0.1 — CMDIAD가 우선.
"""
from __future__ import annotations

import os
import time


class YOLODetector:
    """YOLOv8n 객체탐지 탐지기.

    modality = "object_detection"
    unenrolled/general 이미지에 보조적으로 사용된다.
    이상 수치 점수를 생성하지 않는다(decision="n/a").
    """

    name = "yolo"
    modality = "object_detection"

    # ── applicability ──────────────────────────────────────────────────────
    def applicability(self, image_meta: dict, product: dict | None) -> float:
        """일반 객체/unenrolled 이미지에 적합.

        규칙:
        - enrolled 제품 → 0.10 (CMDIAD가 담당, YOLO는 보조 불필요)
        - general_object 도메인 → 0.70
        - industrial_anomaly + unenrolled → 0.40 (보조 탐지만)
        - 기타 → 0.30
        """
        if product and product.get("status") == "enrolled":
            return 0.10

        domain = image_meta.get("domain", "")
        if domain == "general_object":
            return 0.70
        if domain == "industrial_anomaly":
            return 0.40
        return 0.30

    # ── run ───────────────────────────────────────────────────────────────
    def run(self, image_path: str, product: dict | None) -> dict:
        """YOLOv8n 객체탐지 수행.

        [v4 불변식] score=0.0, decision="n/a" — YOLO는 이상 점수를 만들지 않는다.
        detections(바운딩박스 목록)를 regions에 담아 UI가 표시할 수 있도록 반환.

        Returns: Detector.run() 표준 스키마
        """
        print("  [YOLODetector] YOLOv8n 바운딩박스 객체탐지 구동")
        t0 = time.time()

        try:
            from aria.perception.vision_router import _run_yolo
            yolo_res = _run_yolo(image_path, "yolov8n", "yolov8n.pt")

            if yolo_res.get("status") == "success":
                detections = yolo_res.get("detections", [])
                result_image_path = yolo_res.get("result_image_path")
                elapsed = round(time.time() - t0, 2)
                print(f"  [YOLODetector] 완료 ({len(detections)} 객체, {elapsed}s)")

                return {
                    "score": 0.0,           # YOLO는 이상 점수 없음
                    "threshold": 0.0,
                    "decision": "n/a",      # 항상 n/a — 수치 이상탐지 아님
                    "confidence": 0.65,
                    "render_type": "bounding_box",
                    "overlay_path": result_image_path,
                    "regions": detections,
                    "model_name": "YOLOv8n Object Detector",
                }
            else:
                raise RuntimeError(f"YOLO 실패: {yolo_res.get('error', '알 수 없음')}")

        except Exception as e:
            print(f"  [YOLODetector] 실패: {e}")
            return {
                "score": 0.0,
                "threshold": 0.0,
                "decision": "n/a",
                "confidence": 0.0,
                "render_type": "bounding_box",
                "overlay_path": image_path,
                "regions": [],
                "model_name": "YOLOv8n (실패)",
                "_reason": str(e),
            }
