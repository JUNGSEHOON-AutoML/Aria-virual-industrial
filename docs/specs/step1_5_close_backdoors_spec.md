# ARIA 리팩터링 1단계 보강 명세서 — 뒷문 차단 (Close Legacy Backdoors)

## 0. 목표 (Why)

1단계에서 **정문**(`autonomous_agent` 이미지 입구)은 레지스트리로 통합됐다.
하지만 두 개의 **보조 라이브 경로**가 아직 레거시 dispatch로 CMDIAD에 직접 닿는다:

- `harness_loop.py` — 폴백 실행 시 `run_inference` → anomaly면 `ccifps` 직행
- `model_discovery.py` — `_run_ccifps`가 `cmdiad_inference`를 직접 import

이 둘을 닫아 **모든 CMDIAD 실행이 `cmdiad` 탐지기 플러그인을 거치게** 만든다.
폴백 오케스트레이션은 `inspect_via_registry`로 통일한다.

---

## 1. 범위 (Scope)

**포함:** CMDIAD를 *직접* 실행하는 지점을 레지스트리/플러그인 경유로 전환.

**보존(건드리지 말 것):**
- `model_discovery.py`의 **동적 모델 실행 분기**(`source == "ultralytics"|"huggingface"|"timm"|"vlm"`)는
  "자율 모델 탐색" 기능의 본체다. 그대로 둔다. 이들이 쓰는 `run_inference` /
  `_run_transformers_pipeline` / `_run_timm_model`은 **레거시가 아니라 동적 실행기**로 재정의한다.

**다음 단계로 미룸:** VLM 교체(2단계), 백본 분리(3단계), 동적 발견 모델을 레지스트리에 등록(4단계).

---

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `harness_loop.py` | 폴백 추론을 `run_inference(...)` → `inspect_via_registry(image_path)`로 교체 |
| `model_discovery.py` | `_run_ccifps`가 `cmdiad_inference` 직접 import 대신 `inspect_via_registry`로 위임 |
| `vision_router.py` | (정리) `_run_ccifps`의 `cmdiad_inference` 직접 import 제거 — 위임 또는 사실상 dead 처리. `run_inference` 주석을 "입구 미사용; ModelDiscovery 동적 실행기"로 정정 |

---

## 3. 작업 명세 (What)

### 3-A. `harness_loop.py` — 폴백을 레지스트리로

약 345–346행, 폴백 추론 호출부:

```python
# AS-IS
result = run_inference(image_path, model_decision)

# TO-BE
from agents.vision_agent import inspect_via_registry
result = inspect_via_registry(image_path)
```

- 위쪽의 `ensure_model_installed` / ccifps·yolo 폴백 `model_decision` 구성 블록은 추론에는 더 이상 쓰이지 않는다(레지스트리가 탐지기를 선택). 로깅용으로 `result["model_decision"] = model_decision`은 남겨도 무방.
- 설계 노트: 하니스는 "다른 접근" 폴백이지만, 레지스트리 `rank_for`가 재분석 기반으로 다른 탐지기를 고를 수 있으므로 잠금 해제 목적에는 이 경로가 맞다. (특정 탐지기 제외 힌트는 1단계 보강 범위 밖.)

### 3-B. `model_discovery.py` — `_run_ccifps` 위임

`_run_ccifps` 메서드(약 787행)의 본문을 직접 import 대신 위임으로 교체:

```python
# AS-IS
def _run_ccifps(self, image_path: str) -> dict:
    try:
        from cmdiad_inference import CMDIADInference
        engine = CMDIADInference()
        return engine.run(image_path)
    except Exception as e:
        return {"error": f"CCIFPS 실패: {e}", "status": "error"}

# TO-BE
def _run_ccifps(self, image_path: str) -> dict:
    """CMDIAD 실행 — inspect_via_registry로 위임 (직접 import 금지)."""
    try:
        from agents.vision_agent import inspect_via_registry
        return inspect_via_registry(image_path)
    except Exception as e:
        return {"error": f"CCIFPS 위임 실패: {e}", "status": "error"}
```

- `_execute`의 `source == "ccifps"` 분기는 `self._run_ccifps(...)`를 그대로 호출 → 자동으로 위임된다.
- yolo/huggingface/timm/vlm 분기는 **변경 없음**(동적 탐색 보존).

### 3-C. `vision_router.py` — 죽은 CMDIAD import 정리

`_run_ccifps`(약 858행)의 `from cmdiad_inference import CMDIADInference`를 제거하고
본문을 `inspect_via_registry` 위임으로 교체(3-B와 동일 패턴). 1단계에서 이미 `DEPRECATED`
주석이 달려 있고 정문에선 호출되지 않으므로, import만 제거하면 라이브 CMDIAD 직접 경로가 사라진다.

`run_inference` 상단 주석을 다음과 같이 정정(완전 미사용이 아님을 명확히):

```python
# NOTE: 입구(inspect_via_registry) 미사용. ModelDiscovery의 동적 모델(yolo/hf/timm) 실행기로만 사용.
```

---

## 4. 수용 기준 (Acceptance Criteria) — GitHub grep로 검증

1. `harness_loop.py`에 `run_inference(` **호출이 0건**이고 `inspect_via_registry` 호출이 존재:
   ```
   grep -n "run_inference(\|inspect_via_registry" harness_loop.py
   ```
2. `cmdiad_inference` 직접 import가 **다음 3개 파일에만** 남는다 — `model_discovery.py`와 `vision_router.py`는 빠진다:
   ```
   grep -rn "from cmdiad_inference\|import cmdiad_inference" --include=*.py . | grep -v "_deprecated/"
   ```
   허용 목록: `detectors/cmdiad_detector.py`(플러그인 본체), `product_registry.py`(3단계 대상), `threshold_calibrator.py`(CMDIAD 캘리브레이션 — 정당).
3. (회귀 가드) 1단계 유지: `autonomous_agent.py`가 여전히 `inspect_via_registry`를 호출.
   ```
   grep -n "inspect_via_registry\|VisionRouter()" autonomous_agent.py
   ```
4. (보존 확인) `model_discovery.py`에 동적 실행 분기가 그대로 존재 — yolo/huggingface/timm 경로가 삭제되지 않음:
   ```
   grep -n "ultralytics\|huggingface\|_run_timm_model" model_discovery.py
   ```

> 1·2·3이 통과하고 4가 보존되면 완료. 정문 + 두 뒷문 모두 레지스트리/플러그인 경유, 동적 탐색은 보존.

---

## 5. 검증 절차 (내가 수행)

"푸시 완료" 알림 → 브랜치 재clone → 4-1~4-4 grep 확인 →
전부 통과 시 **2단계(VLM 교체 가능화) 명세서** 전달.

---

## 6. 커밋

- 같은 브랜치 `refactor/step1-routing-unification`에 추가 커밋(또는 `step1.5-close-backdoors`)
- 메시지(예): `refactor(routing): route harness/discovery CMDIAD calls through registry, drop direct cmdiad_inference imports`

---

## 7. 주의

- `_run_ccifps` 위임 시 무한 재귀 없음 — `inspect_via_registry` → `rank_for` → `CMDIADDetector.run` →
  `cmdiad_inference`(플러그인 내부, **허용된 단 하나의 import 지점**). `_run_ccifps`로 되돌아오지 않는다.
- `inspect_via_registry`는 내부에서 `ProductRegistry.identify()`를 하므로, 폴백/탐색 경로에서도
  등록(enrolled) 여부에 맞게 CMDIAD가 올바르게 선택된다(직접 `engine.run()`보다 정확).
- 동적 발견 모델을 레지스트리 플러그인으로 승격하는 것은 4단계(MCP/동적 탐지기) 주제. 지금은 분리 유지.
