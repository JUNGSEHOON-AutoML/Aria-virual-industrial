# ARIA 리팩터링 4단계 명세서 — MCP 어댑터 (Pluggable MCP Detectors)

## 0. 목표 (Why)

MCP 도구를 `Detector` Protocol로 감싸는 **`MCPDetector` 어댑터**를 만들고,
이를 **config 기반으로 레지스트리에 자동 등록**한다.

결과: "MCP 서버 추가 → `mcp_config.json`에 선언 한 줄 → 새 검사기"가 성립.
레지스트리는 이미 Protocol만 만족하면 무엇이든 받으므로(1~3단계로 정문이 레지스트리 경유),
이 어댑터 하나로 "MCP 자유자재 연결"이 완성된다.

**기존 동작 영향 없음** — MCP 탐지기를 선언하지 않으면 현 동작 그대로.

---

## 1. 범위 (Scope)

**포함:**
- `MCPDetector` 어댑터 신규 (`Detector` Protocol 구현)
- `get_mcp_client()` 싱글톤 접근자 신규 (mcp_client.py)
- 레지스트리의 config 기반 MCP 탐지기 자동 등록
- `mcp_config.json`에 `mcpDetectors` 선언 섹션 추가(빈 배열로 시작 가능)

**제외(다음/별도):**
- `MCPVLMProvider`(VLM seam의 MCP 구현)는 **선택**(§3-E). 같은 패턴이라 원하면 같이, 아니면 다음에.
- 런타임 pip 제거 → 5단계
- ZIP→시뮬레이션 시청 → 6단계

---

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `detectors/mcp_detector.py` (신규) | `MCPDetector` — MCP 도구를 Detector로 래핑 |
| `mcp_client.py` | `get_mcp_client()` 싱글톤 접근자 추가 |
| `detectors/registry.py` | `_register_mcp_detectors(reg)` 추가 + `_build_default_registry`에서 호출 |
| `mcp_config.json` | `"mcpDetectors": []` 선언 섹션 추가 |

---

## 3. 작업 명세 (What)

### 3-A. `get_mcp_client()` — mcp_client.py 싱글톤

```python
_MCP_SINGLETON = None

def get_mcp_client():
    """프로세스 단일 MCPClient 반환 (레지스트리 상주 탐지기가 사용)."""
    global _MCP_SINGLETON
    if _MCP_SINGLETON is None:
        import os
        _MCP_SINGLETON = MCPClient(os.environ.get("MCP_CONFIG", "mcp_config.json"))
    return _MCP_SINGLETON
```

### 3-B. `detectors/mcp_detector.py` — 어댑터

```python
from __future__ import annotations


class MCPDetector:
    """MCP 도구를 Detector Protocol로 감싸는 어댑터.

    [base.py 불변식 준수]
    - applicability(): 무거운 추론 금지 — config 규칙만 본다(MCP 호출 금지).
    - run(): MCP 도구 호출 → 표준 result dict 매핑.
    - 수치 비교 불가 시 decision="n/a"(LLM 출력에서 pass/fail 파싱 금지).
    """

    def __init__(self, name, modality, server, tool,
                 applicability=None, result_map=None):
        self.name = name
        self.modality = modality
        self._server = server
        self._tool = tool
        self._appl = applicability or {}
        self._map = result_map or {}

    def applicability(self, image_meta: dict, product: dict | None) -> float:
        domains = self._appl.get("domains", [])
        if not domains or image_meta.get("domain") in domains:
            return float(self._appl.get("score", 0.4))
        return 0.05

    def run(self, image_path: str, product: dict | None) -> dict:
        from mcp_client import get_mcp_client
        try:
            raw = get_mcp_client().call_tool(
                self._tool, {"image_path": image_path}, server_name=self._server)
        except Exception as e:
            return self._na(f"MCP 호출 실패: {e}")
        if isinstance(raw, dict) and raw.get("error"):
            return self._na(raw["error"])
        return self._to_standard(raw if isinstance(raw, dict) else {"text": str(raw)})

    def _to_standard(self, raw: dict) -> dict:
        g = lambda k, d=None: raw.get(self._map.get(k, k), d)
        score, threshold = g("score"), g("threshold")
        if isinstance(score, (int, float)) and isinstance(threshold, (int, float)):
            decision = "fail" if score > threshold else "pass"
        else:
            decision = "n/a"
        return {
            "score": score, "threshold": threshold, "decision": decision,
            "confidence": g("confidence", 0.5),
            "render_type": g("render_type", "none"),
            "overlay_path": g("overlay"),
            "regions": g("regions", []),
            "model_name": f"MCP:{self._server}.{self._tool}",
        }

    def _na(self, msg: str) -> dict:
        return {"score": None, "threshold": None, "decision": "n/a",
                "confidence": 0.0, "render_type": "none", "overlay_path": None,
                "regions": [], "model_name": f"MCP:{self._server}", "error": msg}
```

### 3-C. `detectors/registry.py` — config 기반 등록

```python
def _register_mcp_detectors(reg) -> None:
    """mcp_config.json의 mcpDetectors 선언을 읽어 MCPDetector로 등록."""
    import json, os
    from detectors.mcp_detector import MCPDetector
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
```

`_build_default_registry()` 끝부분, `return reg` 직전에 호출:

```python
    reg.register(SegmentationDetector())
    _register_mcp_detectors(reg)   # ← 추가
    return reg
```

### 3-D. `mcp_config.json` — 선언 섹션

최상위에 빈 배열로 시작(추후 한 줄씩 추가):

```json
  "mcpDetectors": [],
```

선언 예시(문서용 — 실제 MCP 비전 도구가 생기면 이렇게 추가):

```json
  "mcpDetectors": [
    {
      "name": "mcp_hf_vision",
      "modality": "object_detection",
      "server": "huggingface",
      "tool": "huggingface.run_vision_model",
      "applicability": { "domains": ["general_object"], "score": 0.55 },
      "result_map": { "regions": "detections", "overlay": "image_path" }
    }
  ]
```

### 3-E. (선택) `MCPVLMProvider` — VLM seam의 MCP 구현

원하면 2단계 seam을 대칭으로 확장: `config/vlm.py`에 `MCPVLMProvider(analyze())`를 추가하고
`get_vlm()`의 `kind == "mcp"` 분기에 연결. 이번 단계 필수 아님(원하면 같이).

---

## 4. 수용 기준 (Acceptance Criteria) — GitHub grep로 검증

1. 어댑터 정의(Protocol 구현 + MCP 호출):
   ```
   grep -n "class MCPDetector\|def applicability\|def run\|call_tool" detectors/mcp_detector.py
   ```
2. 싱글톤 접근자:
   ```
   grep -n "def get_mcp_client" mcp_client.py
   ```
3. 레지스트리가 config에서 MCP 탐지기 등록:
   ```
   grep -n "_register_mcp_detectors\|MCPDetector\|mcpDetectors" detectors/registry.py
   ```
4. config에 선언 섹션 존재:
   ```
   grep -n "mcpDetectors" mcp_config.json
   ```
5. (회귀 가드) 1·1.5·2·3 유지:
   ```
   grep -c "inspect_via_registry" autonomous_agent.py     # > 0
   grep -c "get_vlm" agents/vision_agent.py               # > 0
   grep -c "get_backbone" product_registry.py             # > 0
   grep -c "run_inference(" harness_loop.py               # = 0
   grep -rn "from cmdiad_inference\|import cmdiad_inference" --include=*.py . | grep -v "_deprecated/"
   # → cmdiad_detector / threshold_calibrator / config/backbone 3곳만
   ```
6. (구문) `python -m py_compile detectors/mcp_detector.py detectors/registry.py mcp_client.py` → OK

> 1~4 통과 + 5 회귀 없음 + 6 구문 OK이면 완료. `mcpDetectors: []`로 비워둬도 통과(어댑터·배선만 검증).

---

## 5. 검증 절차 (내가 수행)

"푸시 완료" → 브랜치 재clone → 4-1~4-6 확인 → 통과 시 다음 단계.
가능하면 빈 `mcpDetectors`로 시작하되, 실제 동작 확인용으로 기존 서버(예: huggingface)의
읽기전용 도구 하나를 예시로 선언해보는 것도 좋다(선택).

---

## 6. 커밋

- 브랜치: `refactor/step4-mcp-detector`
- 메시지(예): `feat(mcp): add MCPDetector adapter + config-driven registration into DetectorRegistry`

---

## 7. 주의 / 안전 / 설계 포인트

- **applicability는 반드시 가벼워야 한다.** MCP 호출/모델 로드 금지 — config 규칙(domain/score)만. (base.py 불변식)
- **읽기전용 도구만 래핑.** `mcp_config.json`의 `require_approval_for: [delete_file, write_file]` 게이트는 MCPClient 계층에 있으므로, 파괴적 도구는 여전히 승인 뒤에 있다. MCPDetector는 이미지 분석 같은 **읽기전용 추론 도구**만 감싼다.
- **결정론/재현성 유지.** MCP 탐지기는 **config에 명시적으로 선언**(런타임 자동 발견 아님)되고, `rank_for`는 결정론적이므로 검사 게이트의 재현성이 보존된다.
- **결과 매핑 방어적으로.** MCP 도구 출력 키가 제각각이라 `result_map`으로 흡수하고, 수치 비교 불가 시 `decision="n/a"`로 안전하게 둔다.
- **범위 엄수.** pip 제거·시뮬레이션 시청은 이번에 손대지 않는다.
