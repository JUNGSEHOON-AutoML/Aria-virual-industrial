"""detectors/vlm_inspector_detector.py — VLM 시각 검사 플러그인.

v4 §1 + 제약 4 규칙:
- VLM 검사기는 regions/description만 내고 단독 pass/fail을 선언하지 않는다.
- decision은 항상 "n/a" — LLM 출력에서 판정을 파싱하는 것을 금지한다.
- applicability()는 이미 계산된 image_meta만 보고 빠르게 점수를 낸다 (무거운 추론 금지).
- 문서/스크린샷/텍스트 위주 이미지에서 높은 우선순위를 가진다.
"""
from __future__ import annotations

import time


class VLMInspectorDetector:
    """VLM 시각 묘사 검사기.

    modality = "vlm_inspect"
    문서, 스크린샷, 텍스트 이미지 등 수치 이상탐지가 불가능한 경우의
    시각적 설명을 제공한다. 판정(pass/fail)을 내리지 않는다.
    """

    name = "vlm_inspector"
    modality = "vlm_inspect"

    # ── applicability ──────────────────────────────────────────────────────
    def applicability(self, image_meta: dict, product: dict | None) -> float:
        """문서/스크린샷/텍스트 위주 이미지에 적합.

        [무거운 추론 금지] 이미 계산된 image_meta 필드(domain)만 참조한다.

        규칙:
        - domain이 "document" / "screenshot" / "text" → 0.90
        - enrolled 제품 → 0.15 (CMDIAD가 담당)
        - general_object (unenrolled) → 0.50 (YOLO와 병행 가능)
        - industrial_anomaly (unenrolled) → 0.25
        - 기타 → 0.20
        """
        domain = image_meta.get("domain", "")

        # 문서/스크린샷 도메인: VLM이 최적
        if domain in ("document", "screenshot", "text"):
            return 0.90

        # 등록 제품: CMDIAD가 담당, VLM은 보조 가치 낮음
        if product and product.get("status") == "enrolled":
            return 0.15

        if domain == "general_object":
            return 0.50

        if domain == "industrial_anomaly":
            return 0.25

        return 0.20

    # ── run ───────────────────────────────────────────────────────────────
    def run(self, image_path: str, product: dict | None) -> dict:
        """VLM 시각 묘사 수행.

        [v4 불변식] decision은 항상 "n/a".
        LLM 출력에서 pass/fail 문자열을 파싱해 반환하는 것을 절대 금지한다.
        regions에 VLM이 언급한 관심 영역(텍스트로)을 담는다.

        Returns: Detector.run() 표준 스키마
        """
        print("  [VLMInspectorDetector] VLM 시각 묘사 검사 구동")
        t0 = time.time()

        # VisionAgent가 이미 1회 VLM 호출을 완료했으므로,
        # 여기서 재호출 시 OCR/문서 특화 프롬프트를 사용한다.
        description = ""
        try:
            from aria.core.config.vlm import get_vlm

            ocr_prompt = (
                "이미지에서 시각적으로 관찰되는 모든 내용을 묘사하라. "
                "텍스트가 있으면 그대로 전사하고, 도형·표·수식도 구조를 유지해 기술하라. "
                "추측이나 해석을 추가하지 말고 오직 보이는 것만 보고하라."
            )

            raw = get_vlm().analyze(image_path, ocr_prompt)
            # </think> 태그 제거
            if "</think>" in raw:
                raw = raw.split("</think>")[-1].strip()
            description = raw

        except Exception as e:
            print(f"  [VLMInspectorDetector] VLM 호출 실패: {e}")
            description = f"VLM 묘사 실패: {e}"

        elapsed = round(time.time() - t0, 2)
        print(f"  [VLMInspectorDetector] 완료 ({elapsed}s)")

        return {
            "score": 0.0,
            "threshold": 0.0,
            "decision": "n/a",       # [절대 변경 금지] LLM 판단은 pass/fail 불가
            "confidence": 0.55,
            "render_type": "text",
            "overlay_path": None,
            "regions": [],
            "model_name": "VLM Inspector (Qwen2.5-VL)",
            "description": description,
        }
