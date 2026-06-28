"""detectors/base.py — 탐지기 플러그인 공통 계약(Protocol).

v4 §1 규칙:
- 모든 비전 방법(이상탐지·객체탐지·OCR·VLM검사)은 이 인터페이스를 구현한다.
- CMDIAD/PatchCore는 이 인터페이스를 구현한 플러그인 1개씩으로 강등된다.
- applicability()는 무거운 추론 금지 — image_meta(이미 계산된 VLM 결과)만 본다.
- VLM 검사기는 decision을 "n/a"로만 반환한다(수치 기반 탐지기 아님).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Detector(Protocol):
    """탐지기 플러그인 계약.

    name     : 탐지기 고유 식별자. 예) "cmdiad", "yolo", "vlm_inspector"
    modality : 탐지 방식. "surface_anomaly" | "object_detection" | "ocr" | "vlm_inspect"
    """

    name: str
    modality: str

    def applicability(self, image_meta: dict, product: dict | None) -> float:
        """이 이미지에 얼마나 적합한지 0.0~1.0 반환.

        [필수] 무거운 추론(모델 로드, 피처 추출 등) 금지.
               VLM이 이미 계산한 image_meta 필드만 참조해 빠르게 점수를 낸다.

        Args:
            image_meta: VLM 분석 결과. 키: domain, defect_suspected, primary_object, scene
            product: ProductRegistry.identify() 결과. 없거나 status=="unenrolled"이면 None.

        Returns:
            0.0(부적합) ~ 1.0(최적합)
        """
        ...

    def run(self, image_path: str, product: dict | None) -> dict:
        """실제 추론을 수행하고 표준 결과 dict를 반환.

        [v4 불변식]
        - decision은 결정론적 수치 비교 결과(score vs threshold)로만 결정.
        - VLM 검사기(vlm_inspect 모달리티)는 decision을 항상 "n/a"로 반환한다.
        - LLM 출력에서 pass/fail을 파싱해 decision에 쓰는 것을 금지한다.

        Returns:
            {
                "score"       : float,          # 이상 점수 (수치 탐지기만 유효)
                "threshold"   : float,          # 판정 기준값
                "decision"    : "pass"|"fail"|"n/a",  # 결정론적 판정
                "confidence"  : float,          # 이 탐지기가 자기 결과를 얼마나 확신하는가 0~1
                "render_type" : "heatmap"|"bounding_box"|"text"|"none",
                "overlay_path": str | None,     # 오버레이 이미지 경로
                "regions"     : list,           # bbox / 세그멘테이션 리스트
                "model_name"  : str,            # 표시용 모델 이름
            }
        """
        ...
