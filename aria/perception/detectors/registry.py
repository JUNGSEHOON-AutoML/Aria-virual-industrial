"""detectors/registry.py — 탐지기 플러그인 레지스트리.

v4 §1 규칙:
- 외부에서 CMDIADInference 등을 직접 인스턴스화하지 않는다.
- get_registry()를 통해 싱글톤 레지스트리를 받고, rank_for()로 탐지기를 선택한다.
- 신규 탐지기 추가: 이 파일의 _build_default_registry()에 register() 한 줄 추가.
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aria.perception.detectors.base import Detector


class DetectorRegistry:
    """탐지기 플러그인 레지스트리."""

    def __init__(self) -> None:
        self._detectors: list = []

    def register(self, detector) -> None:
        """탐지기를 레지스트리에 등록한다."""
        self._detectors.append(detector)

    def list(self) -> list:
        """등록된 탐지기 목록을 반환한다."""
        return list(self._detectors)

    def rank_for(self, image_meta: dict, product: dict | None) -> list[tuple]:
        """이미지 메타와 제품 정보를 바탕으로 탐지기를 적합도 내림차순으로 정렬해 반환.

        Args:
            image_meta: {"domain": str, "defect_suspected": bool,
                         "primary_object": str, "scene": str}
            product: ProductRegistry.identify() 결과.
                     status=="enrolled"이면 그대로 전달, 아니면 None.

        Returns:
            [(detector, applicability_score), ...] — 적합도 내림차순
        """
        scored: list[tuple] = []
        for d in self._detectors:
            try:
                score = float(d.applicability(image_meta, product))
            except Exception as e:
                print(f"  [Registry] {d.name}.applicability() 에러: {e}")
                score = 0.0
            scored.append((d, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def get(self, name: str):
        """이름으로 탐지기를 직접 조회한다."""
        for d in self._detectors:
            if d.name == name:
                return d
        return None


# ── 싱글톤 ─────────────────────────────────────────────────────────────────
_registry_instance: DetectorRegistry | None = None
_registry_lock = threading.Lock()


def _register_mcp_detectors(reg) -> None:
    """mcp_config.json의 mcpDetectors 선언을 읽어 MCPDetector로 등록."""
    import json, os
    from aria.perception.detectors.mcp_detector import MCPDetector
    try:
        with open(os.environ.get("MCP_CONFIG", "mcp_config.json")) as f:
            decls = json.load(f).get("mcpDetectors", [])
    except Exception as e:
        print(f"  [Registry] mcpDetectors 로드 실패: {e}")
        decls = []
    for d in decls:
        try:
            reg.register(MCPDetector(**d))
            print(f"  [Registry] MCP 탐지기 등록: {d.get('name')}")
        except Exception as e:
            print(f"  [Registry] MCP 탐지기 등록 실패 {d.get('name')}: {e}")

def _build_default_registry() -> DetectorRegistry:
    """기동 시 큐레이션된 탐지기들을 등록한 기본 레지스트리를 반환."""
    from aria.perception.detectors.cmdiad_detector          import CMDIADDetector
    from aria.perception.detectors.yolo_detector            import YOLODetector
    from aria.perception.detectors.vlm_inspector_detector   import VLMInspectorDetector
    # ── 산업 에이전트 AI 확장 플러그인 ──────────────────────────────────────
    from aria.perception.detectors.object_count_detector    import ObjectCountDetector
    from aria.perception.detectors.ocr_defect_detector      import OCRDefectDetector
    from aria.perception.detectors.dimension_detector       import DimensionDetector
    from aria.perception.detectors.segmentation_detector    import SegmentationDetector

    reg = DetectorRegistry()
    # 기존 탐지기
    reg.register(CMDIADDetector())
    reg.register(YOLODetector())
    reg.register(VLMInspectorDetector())
    # 신규 산업 특화 탐지기
    reg.register(ObjectCountDetector())
    reg.register(OCRDefectDetector())
    reg.register(DimensionDetector())
    reg.register(SegmentationDetector())
    _register_mcp_detectors(reg)
    return reg


def get_registry() -> DetectorRegistry:
    """싱글톤 DetectorRegistry를 반환한다.

    [v4 §1 규칙] 탐지기는 반드시 이 함수를 통해 얻는다.
    직접 CMDIADDetector() 등을 인스턴스화하는 것을 금지한다.
    """
    global _registry_instance
    if _registry_instance is None:
        with _registry_lock:
            if _registry_instance is None:
                _registry_instance = _build_default_registry()
    return _registry_instance
