from __future__ import annotations
import os
from typing import Protocol, runtime_checkable

@runtime_checkable
class Backbone(Protocol):
    """Backbone feature extractor interface."""
    name: str

    def extract_features(self, image_path: str):
        """Extract patch features from an image.
        
        Args:
            image_path (str): The path to the image file.
            
        Returns:
            Tensor: Patch feature tensor [N, D].
        """
        ...

class DinoViTB8Backbone:
    """Default Backbone wrapping existing DINO ViT-B/8."""
    name = "dino_vit_b8"

    def __init__(self):
        self._engine = None

    def _ensure(self):
        if self._engine is None:
            # Lazy import to avoid loading heavy weights when not needed
            from aria.perception.cmdiad_inference import CMDIADInference
            self._engine = CMDIADInference()
        return self._engine

    def extract_features(self, image_path: str):
        from aria.perception.cmdiad_inference import preprocess_image
        eng = self._ensure()
        # Pass caller_context to help with logging differentiation if needed
        eng._ensure_backbone(caller_context="ProductRegistry/Backbone")
        tensor = preprocess_image(image_path)
        return eng.backbone.extract_features(tensor)

# ── Singleton ─────────────────────────────────────────────────────────────────
_BACKBONE_SINGLETON: Backbone | None = None

def get_backbone() -> Backbone:
    """Get active Backbone singleton. Chosen via env ARIA_BACKBONE (default 'dino_vit_b8')."""
    global _BACKBONE_SINGLETON
    if _BACKBONE_SINGLETON is None:
        kind = os.environ.get("ARIA_BACKBONE", "dino_vit_b8").lower()
        # Future enhancement: elif kind == "clip": _BACKBONE_SINGLETON = ClipBackbone()
        _BACKBONE_SINGLETON = DinoViTB8Backbone()
    return _BACKBONE_SINGLETON
