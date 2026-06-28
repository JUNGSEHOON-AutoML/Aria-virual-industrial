# ARIA 리팩터링 2단계 명세서 — VLM 교체 가능화 (Pluggable VLM)

## 0. 목표 (Why)

검사 경로의 VLM(`qwen2.5vl:7b` via ollama)을 **하나의 교체 가능한 seam** 뒤로 모은다.
결과:
- 다른 VLM(다른 ollama 모델 / API형 / MCP형)을 **config 한 줄**로 교체.
- 모델명 리터럴이 흩어진 현 상태를 `config/models.py` 한 곳으로 외부화.
- "자유자재로 MCP VLM" → `MCPVLMProvider`를 끼우는 자리(seam)가 생긴다(구현은 4단계).

현재 동작(qwen2.5vl:7b)은 **기본값으로 그대로 보존**된다.

---

## 1. 범위 (Scope)

**포함 — 검사(이미지 분석) VLM seam:**
- `VLMProvider` 인터페이스 + `OllamaVLMProvider` 기본 구현 + `get_vlm()` 셀렉터 신규
- 검사 경로의 두 VLM 호출부를 seam 경유로 전환
- `harness_loop.py`의 검증용 VLM 모델명도 config 참조로 통일

**제외(다음 단계 / 다른 관심사 — 건드리지 말 것):**
- `agent_orchestrator.py`의 `_call_ollama`(chat/routing/debate용 **텍스트 LLM** — qwen2.5:14b, deepseek-r1:8b). VLM 아님.
- `autonomous_agent.py`의 `_analyze_image_with_vlm` / `_get_best_vlm_model`(커스텀 질의 전용 별도 경로). 향후 정리 대상으로만 표시.
- `MCPVLMProvider` / `APIVLMProvider` 실제 구현 → 4단계.

---

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `config/vlm.py` (신규) | `VLMProvider` Protocol + `OllamaVLMProvider` + `get_vlm()` |
| `agents/vision_agent.py` | `_call_vlm_module` → `get_vlm().analyze(...)` 위임, `"qwen2.5vl:7b"` 리터럴 제거(67·405행) |
| `detectors/vlm_inspector_detector.py` | `run`의 인라인 ollama POST → `get_vlm().analyze(...)`, 리터럴 제거(91행) |
| `harness_loop.py` | `VLM_MODEL = "qwen2.5vl:7b"` → `from config.models import MODELS; VLM_MODEL = MODELS["vision"]` |

---

## 3. 작업 명세 (What)

### 3-A. `config/vlm.py` 신규 — seam 정의

```python
from __future__ import annotations
import os, json, base64, urllib.request
from typing import Protocol, runtime_checkable
from config.models import MODELS

# 기존 코드가 쓰던 ollama 엔드포인트 env 이름을 그대로 재사용할 것
OLLAMA_API = os.environ.get("OLLAMA_API", "http://localhost:11434/api/chat")


@runtime_checkable
class VLMProvider(Protocol):
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
            OLLAMA_API, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read())["message"]["content"].strip()
        except Exception as e:
            return f"VLM 호출 오류: {e}"


_VLM_SINGLETON: VLMProvider | None = None

def get_vlm() -> VLMProvider:
    """활성 VLM 공급자 반환. env ARIA_VLM_PROVIDER 로 선택(기본 'ollama')."""
    global _VLM_SINGLETON
    if _VLM_SINGLETON is None:
        kind = os.environ.get("ARIA_VLM_PROVIDER", "ollama").lower()
        # 4단계에서 'mcp', 'api' 분기 추가 예정 — 지금은 ollama만
        _VLM_SINGLETON = OllamaVLMProvider()
    return _VLM_SINGLETON
```

> 주의: `OLLAMA_API`(또는 `vlm_inspector_detector`가 쓰던 `OLLAMA_API_BASE`) 중 **기존에 실제로 동작하던 엔드포인트 env 이름**을 그대로 써서 현 동작을 깨지 않는다.

### 3-B. `agents/vision_agent.py` — 위임

`_call_vlm_module`(58–78행) 본문을 seam 위임으로 교체:

```python
def _call_vlm_module(image_path: str, prompt: str) -> str:
    """모듈 레벨 VLM 호출 — config.vlm.get_vlm()로 위임."""
    from config.vlm import get_vlm
    return get_vlm().analyze(image_path, prompt)
```

- 67행과 405행의 `"model": "qwen2.5vl:7b"` 직접 페이로드 구성은 제거(이제 provider가 담당).
- 405행이 속한 `VisionAgent` 래퍼는 이미 `inspect_via_registry`를 호출하므로, 거기 남은 VLM 페이로드는 죽은 코드 → 정리.

### 3-C. `detectors/vlm_inspector_detector.py` — 위임

`run`(57행~)의 인라인 ollama POST(78–91행 부근)를 다음으로 교체:

```python
from config.vlm import get_vlm
raw = get_vlm().analyze(image_path, prompt)   # 기존 프롬프트 변수 그대로 사용
```

- `"qwen2.5vl:7b"` 리터럴(91행) 및 인라인 `urllib`/`requests` POST 제거.
- 표시명(`model_name`)은 그대로 둬도 됨(`"VLM Inspector (Qwen2.5-VL)"`) — 다만 provider 모델명을 쓰고 싶으면 `get_vlm().name`/`.model` 참조 가능(선택).
- 이 detector는 `modality="vlm_inspect"`이므로 `decision`은 반드시 `"n/a"` 유지(base.py 불변식).

### 3-D. `harness_loop.py` — 모델명 config 참조

20행:
```python
# AS-IS
VLM_MODEL = "qwen2.5vl:7b"
# TO-BE
from config.models import MODELS
VLM_MODEL = MODELS["vision"]
```

---

## 4. 수용 기준 (Acceptance Criteria) — GitHub grep로 검증

1. seam이 정의됨:
   ```
   grep -n "class VLMProvider\|def get_vlm\|class OllamaVLMProvider" config/vlm.py
   ```
2. 검사 경로 두 곳이 seam을 호출:
   ```
   grep -n "get_vlm" agents/vision_agent.py detectors/vlm_inspector_detector.py
   ```
3. `"qwen2.5vl"` 리터럴이 **검사 경로 3파일에서 제거**됨(0건):
   ```
   grep -n "qwen2.5vl" agents/vision_agent.py detectors/vlm_inspector_detector.py harness_loop.py
   ```
   (참고: `config/models.py`에는 `MODELS["vision"]` 값으로 1건 남는 것이 정상 — 모델명의 단일 출처.)
4. (회귀 가드) 1단계·보강 유지:
   ```
   grep -n "inspect_via_registry" autonomous_agent.py
   grep -rn "from cmdiad_inference\|import cmdiad_inference" --include=*.py . | grep -v "_deprecated/"
   ```
   → 정문 유지 + cmdiad_inference 직접 import는 여전히 3곳(cmdiad_detector / product_registry / threshold_calibrator)만.

> 1·2·3 통과 + 4 회귀 없음이면 완료.

---

## 5. 검증 절차 (내가 수행)

"푸시 완료" → 브랜치 재clone → 4-1~4-4 grep 확인 →
통과 시 **3단계(백본 분리 — product_registry의 CMDIAD/DINO 의존 제거)** 명세서 전달.

---

## 6. 커밋

- 브랜치: `refactor/step2-pluggable-vlm` (또는 기존 브랜치에 이어서)
- 메시지(예): `refactor(vlm): introduce VLMProvider seam, route inspection VLM through config, drop hardcoded model literals`

---

## 7. 주의 / 검증 포인트

- **동작 보존:** `ARIA_VLM_PROVIDER` 기본값 `ollama` + `MODELS["vision"]=qwen2.5vl:7b`이므로 기존과 100% 동일하게 동작해야 한다. 교체는 env/ config만 바꾸면 됨.
- **엔드포인트 env 일관성:** `OllamaVLMProvider`가 쓰는 ollama URL env 이름이 기존 동작하던 것과 같은지 확인(`OLLAMA_API` vs `OLLAMA_API_BASE`). 다르면 호출이 조용히 실패한다.
- **MCP seam(질문 답):** provider 인터페이스가 생기면 MCP VLM은 `MCPVLMProvider(VLMProvider)`로 `analyze()`만 구현해 `get_vlm()` 분기에 추가하면 끝. 단 그 구현은 **4단계**이며, 2단계에선 seam만 만든다(범위 엄수).
- **범위 엄수:** orchestrator 텍스트 LLM, autonomous_agent 커스텀 VLM 경로는 이번에 손대지 않는다.
