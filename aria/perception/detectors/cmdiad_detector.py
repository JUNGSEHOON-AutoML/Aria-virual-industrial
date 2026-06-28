"""detectors/cmdiad_detector.py — CMDIAD 이상탐지 플러그인.

v4 §1 규칙:
- 기존 CMDIADInference 추론 로직을 유지하되, Detector 인터페이스로 감싼다.
- applicability()는 무거운 추론 금지 — product.status와 image_meta만 참조.
- decision은 결정론적: calibrator.get_decision(score, product_id)["verdict"]만 사용.
- 이 클래스는 직접 인스턴스화하지 않는다; get_registry()를 통해 접근.

v4 §2 추가:
- keep_alive 캐시: _engine_cache {product_id: CMDIADInference} 클래스 레벨
  DINO ViT-B/8 백본(~346MB)을 매 요청마다 재로드하지 않는다.
"""
from __future__ import annotations

import os
import threading
import time


class CMDIADDetector:
    """CMDIAD DINO ViT-B/8 기반 이상탐지 탐지기.

    modality = "surface_anomaly"
    enrolled 제품에 대해 정밀 이상 탐지 히트맵을 생성한다.
    """

    name = "cmdiad"
    modality = "surface_anomaly"

    # ── §2 keep_alive 캐시 ────────────────────────────────────────────────
    # product_id → CMDIADInference 인스턴스 재사용
    # DetectorRegistry는 싱글톤이므로 CMDIADDetector 인스턴스도 1개 — 캐시가 프로세스 생존 동안 유지됨
    _engine_cache: dict = {}
    _cache_lock = threading.Lock()

    # ── applicability ──────────────────────────────────────────────────────
    def applicability(self, image_meta: dict, product: dict | None) -> float:
        """enrolled 제품의 표면 이상탐지에 최적.

        [무거운 추론 금지] image_meta와 product 필드만 참조한다.

        - enrolled 제품 + industrial_anomaly 도메인 → 0.95
        - enrolled 제품 + 다른 도메인 → 0.75
        - unenrolled / 미등록 → 0.05
        """
        if product and product.get("status") == "enrolled":
            domain = image_meta.get("domain", "")
            if domain == "industrial_anomaly" or image_meta.get("defect_suspected", False):
                return 0.95
            return 0.75
        return 0.05

    # ── run ───────────────────────────────────────────────────────────────
    def run(self, image_path: str, product: dict | None) -> dict:
        """CMDIAD 추론 실행.

        [§2 keep_alive] 동일 product_id에 대해 CMDIADInference 인스턴스를 캐시에서 꺼낸다.
        product가 없거나 unenrolled이면 즉시 n/a 반환.
        """
        if not product or product.get("status") != "enrolled":
            return self._na_result("등록된 제품 정보가 없습니다.")

        product_id = product.get("product_id") or product.get("category")
        if not product_id:
            return self._na_result("product_id가 누락됐습니다.")

        # ── 지연 임포트 ────────────────────────────────────────────────────
        try:
            from aria.perception.cmdiad_inference import CMDIADInference
            from aria.core.product_registry import ProductRegistry
            from aria.perception.threshold_calibrator import ThresholdCalibrator
        except ImportError as e:
            print(f"  [CMDIADDetector] 의존성 로드 실패: {e}")
            return self._opencv_fallback(image_path, product)

        # ── §2 캐시에서 엔진 조회 / 없으면 생성 ──────────────────────────
        with self._cache_lock:
            if product_id not in self._engine_cache:
                print(f"  [CMDIADDetector] 엔진 캐시 미스 — CMDIADInference 새로 생성 ({product_id})")
                self._engine_cache[product_id] = CMDIADInference()
            else:
                print(f"  [CMDIADDetector] 엔진 캐시 히트 — 기존 인스턴스 재사용 ({product_id})")
            engine = self._engine_cache[product_id]

        print(f"  [CMDIADDetector] CMDIAD 추론 시작 (product={product_id})")
        t0 = time.time()

        try:
            res = engine.run(image_path, product_id)

            if res is None:
                raise RuntimeError("CMDIAD 추론 반환값 없음 (메모리뱅크 없거나 경로 오류)")

            anomaly_score: float = res["anomaly_score"]
            heatmap_path: str    = res["heatmap_path"]
            model_name: str      = res["model_used"]

            # 결정론적 판정 — 수치 vs 캘리브레이션 임계값
            registry    = ProductRegistry()
            calibrator  = ThresholdCalibrator(registry=registry)
            decision_data = calibrator.get_decision(anomaly_score, product_id)
            verdict: str   = decision_data["verdict"]      # "pass" | "fail"
            threshold: float = decision_data["threshold"]

            elapsed = round(time.time() - t0, 2)
            print(f"  [CMDIADDetector] 완료 (score={anomaly_score:.3f}, "
                  f"threshold={threshold:.3f}, verdict={verdict}, {elapsed}s)")

            return {
                "score"       : anomaly_score,
                "threshold"   : threshold,
                "decision"    : verdict,        # "pass" | "fail" (결정론적)
                "confidence"  : 0.92,
                "render_type" : "heatmap",
                "overlay_path": heatmap_path,
                "regions"     : [],
                "model_name"  : model_name,
                "device"      : res.get("device", "cpu"),
                "device_reason": res.get("device_reason", ""),
            }

        except Exception as e:
            print(f"  [CMDIADDetector] CMDIAD 추론 에러 ({e}) → OpenCV Fallback")
            # 캐시에서 제거 — 다음 요청 시 새로 생성
            with self._cache_lock:
                self._engine_cache.pop(product_id, None)
            return self._opencv_fallback(image_path, product)

    # ── 헬퍼 ──────────────────────────────────────────────────────────────
    @staticmethod
    def _na_result(reason: str) -> dict:
        return {
            "score"       : 0.0,
            "threshold"   : 0.0,
            "decision"    : "n/a",
            "confidence"  : 0.0,
            "render_type" : "none",
            "overlay_path": None,
            "regions"     : [],
            "model_name"  : "CMDIADDetector (N/A)",
            "_reason"     : reason,
        }

    @staticmethod
    def _opencv_fallback(image_path: str, product: dict | None) -> dict:
        """CMDIAD 실패 시 Canny Edge Fallback.

        score를 보수적으로 0.0으로 두고 decision을 "n/a"로 반환해
        상위 레이어가 결정하도록 한다.
        """
        import cv2
        from datetime import datetime
        from pathlib import Path

        try:
            img = cv2.imread(image_path)
            if img is None:
                raise FileNotFoundError(f"이미지 로드 실패: {image_path}")

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            edges_color = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
            cv2.putText(edges_color, "FALLBACK: OpenCV Canny Edge",
                        (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            output_dir = os.environ.get(
                "OUTPUT_DIR",
                str(Path(__file__).resolve().parent.parent / "outputs")
            )
            os.makedirs(output_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = os.path.join(output_dir, f"fallback_edge_{ts}.jpg")
            cv2.imwrite(out_path, edges_color)

            return {
                "score"       : 0.0,
                "threshold"   : 0.0,
                "decision"    : "n/a",       # Fallback은 수치 없으므로 n/a
                "confidence"  : 0.1,
                "render_type" : "heatmap",
                "overlay_path": out_path,
                "regions"     : [],
                "model_name"  : "OpenCV Fallback (Canny Edge)",
                "_reason"     : "CMDIAD 추론 실패",
            }
        except Exception as ex:
            return CMDIADDetector._na_result(f"OpenCV Fallback도 실패: {ex}")
