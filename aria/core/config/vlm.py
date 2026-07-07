"""config/vlm.py — VLM 공급자 seam (Step 2: Pluggable VLM).

- VLMProvider: Protocol (교체 가능한 인터페이스)
- OllamaVLMProvider: 현재 동작 보존 (qwen2.5vl:7b via ollama)
- get_vlm(): 활성 공급자 singleton 반환

환경변수:
  ARIA_VLM_PROVIDER=ollama (기본) / mcp / api  → 4단계에서 분기 추가
  OLLAMA_API_BASE=http://localhost:11434       → OllamaVLMProvider 엔드포인트

교체 방법 (현재):
  ARIA_VLM_PROVIDER=ollama           → OllamaVLMProvider (기본)
  MODELS['vision'] 변경               → 다른 ollama 모델로 1줄 교체
"""
from __future__ import annotations

import os
import json
import base64
import urllib.request
from typing import Protocol, runtime_checkable

from aria.core.config.models import MODELS

# 기존 코드가 쓰던 env 이름을 그대로 재사용 (OLLAMA_API_BASE) 및 OLLAMA_API 지원
_OLLAMA_BASE = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434")
OLLAMA_API = os.environ.get("OLLAMA_API", f"{_OLLAMA_BASE}/api/chat")


@runtime_checkable
class VLMProvider(Protocol):
    """VLM 공급자 인터페이스. analyze()만 구현하면 교체 가능."""
    name: str

    def analyze(self, image_path: str, prompt: str) -> str:
        """이미지 경로 + 프롬프트 → VLM 텍스트 응답."""
        ...


class OllamaVLMProvider:
    """현재 동작 보존 — config/models.py MODELS['vision'] 모델을 ollama로 호출."""
    name = "ollama"

    def __init__(self, model: str | None = None):
        self.model = model or MODELS["vision"]

    def analyze(self, image_path: str, prompt: str) -> str:
        try:
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            return f"VLM 이미지 인코딩 실패: {e}"

        payload = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            "stream": False,
        }).encode("utf-8")

        req = urllib.request.Request(
            OLLAMA_API, data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read())["message"]["content"].strip()
        except Exception as e:
            return f"VLM 호출 오류: {e}"


# ── Singleton ─────────────────────────────────────────────────────────────────
_VLM_SINGLETON: VLMProvider | None = None


def get_vlm() -> VLMProvider:
    """활성 VLM 공급자 반환. env ARIA_VLM_PROVIDER 로 선택 (기본 'ollama').

    4단계에서 'mcp', 'api' 분기 추가 예정 — 지금은 ollama만.
    """
    global _VLM_SINGLETON
    if _VLM_SINGLETON is None:
        kind = os.environ.get("ARIA_VLM_PROVIDER", "ollama").lower()
        # 4단계: elif kind == "mcp": _VLM_SINGLETON = MCPVLMProvider()
        # 4단계: elif kind == "api": _VLM_SINGLETON = APIVLMProvider()
        _VLM_SINGLETON = OllamaVLMProvider()
    return _VLM_SINGLETON
