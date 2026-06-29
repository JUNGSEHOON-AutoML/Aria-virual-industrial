"""ARIA Vision Inspection Node — 비병목 검사 노드 레이어.

명세: ARIA_Vision_Inspection_Node_Spec.md
- async_pipeline      : 비병목 비동기 파이프라인 (§3) — acquisition/inference 분리 + bounded queue + backpressure
- detectors           : 플러그형 디텍터 (§신규2) — PatchCore/YOLO26/Combined + 레지스트리
- yolo_dataset_builder: YOLO 학습 데이터 생성 (§신규3) — 마스크→bbox + 합성증강
- twin_bridge         : 상위 연동 (§신규4, §5) — OPC UA/MQTT + /ws/floor 동시 송출

추론 알고리즘은 재작성하지 않는다(§11 DON'T). 기존 patchcore 추론을 디텍터로 주입한다.
무거운/선택 의존(cv2·torch·asyncua·paho-mqtt)은 지연 임포트 — `import aria.inspection`만으로는 안 깨짐.
"""
from .async_pipeline import (  # noqa: F401
    AcquisitionDriver,
    MockDriver,
    AsyncPipeline,
    Frame,
    InspectionResult,
    mock_infer_factory,
)

__all__ = [
    "AcquisitionDriver", "MockDriver", "AsyncPipeline", "Frame",
    "InspectionResult", "mock_infer_factory",
    # 지연 로드(아래 __getattr__)
    "Detector", "PatchCoreDetector", "YoloDetector", "Yolo26Detector",
    "CombinedDetector", "DetectorRegistry",
    "build_yolo_dataset", "train_yolo", "TwinBridge", "build_default_bridge",
]

_LAZY = {
    "Detector": ("detectors", "Detector"),
    "PatchCoreDetector": ("detectors", "PatchCoreDetector"),
    "YoloDetector": ("detectors", "YoloDetector"),
    "Yolo26Detector": ("detectors", "YoloDetector"),
    "CombinedDetector": ("detectors", "CombinedDetector"),
    "DetectorRegistry": ("detectors", "DetectorRegistry"),
    "build_yolo_dataset": ("yolo_dataset_builder", "build_yolo_dataset"),
    "train_yolo": ("yolo_dataset_builder", "train"),
    "TwinBridge": ("twin_bridge", "TwinBridge"),
    "build_default_bridge": ("twin_bridge", "build_default_bridge"),
}


def __getattr__(name):
    if name in _LAZY:
        import importlib
        mod, attr = _LAZY[name]
        return getattr(importlib.import_module(f"{__name__}.{mod}"), attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
