# ARIA 리팩터링 1단계 명세서 — 라우팅 통합 (Routing Unification)

## 0. 목표 (Why)

이미지 검사 입구가 레거시 `VisionRouter`(CMDIAD 하드코딩 경로)를 우회하지 않고,
**이미 존재하는 `DetectorRegistry` 경로**를 타게 만든다.

이 한 단계로 레지스트리에 이미 등록돼 있는 탐지기들
(`YOLODetector`, `OCRDefectDetector`, `SegmentationDetector`, `ObjectCountDetector`,
`DimensionDetector`, `VLMInspectorDetector`, `CMDIADDetector`)이 **즉시 살아난다.**
즉 "CMDIAD로만 하드코딩됨" 문제의 대부분이 해결된다.

---

## 1. 범위 (Scope)

**이번 단계에 포함:**
- 이미지 검사 입구를 레지스트리 경로로 전환
- 레거시 dispatch(`run_inference` / `select_best_model` / `_run_ccifps`) 입구에서 분리

**이번 단계에서 건드리지 말 것 (다음 단계):**
- VLM 교체 가능화 → 2단계
- 백본(DINO) 분리 / `product_registry.py` → 3단계
- MCP 탐지기 어댑터 → 4단계
- 런타임 `pip install` 제거 → 5단계

> 범위를 넘는 변경은 검증을 흐리므로 금지. 1단계는 "입구 화살표를 레지스트리로 돌리는 것" 하나에 집중.

---

## 2. 변경 대상 파일

| 파일 | 변경 내용 |
|------|-----------|
| `agents/vision_agent.py` | registry 선택+실행 로직을 **모듈 레벨 공용 함수**로 추출 |
| `autonomous_agent.py` | 이미지 분기에서 `VisionRouter().run()` → 공용 함수 호출로 교체 |
| `vision_router.py` | `_run_ccifps` 등 CMDIAD 직접 호출 경로를 입구에서 **미사용**으로 만들고 deprecation 표시 |

---

## 3. 작업 명세 (What)

### 3-A. 공용 추론 함수 추출 — `agents/vision_agent.py`

현재 `VisionAgent` 내부(약 130–185행)에 있는
`image_meta` 구성 → `get_registry().rank_for()` → Fast/Debate Path → `detector.run()`
로직을 다음 시그니처의 **모듈 레벨 함수**로 추출한다.

```python
def inspect_via_registry(image_path: str, user_caption: str | None = None) -> dict:
    """이미지 1장을 DetectorRegistry 경로로 검사하고 표준 result dict를 반환한다.

    단계:
      1) VLM 분석 → image_meta {domain, defect_suspected, primary_object, scene, scene_text}
      2) ProductRegistry.identify() → product_for_detector (status=='enrolled'만, 아니면 None)
      3) get_registry().rank_for(image_meta, product_for_detector)
      4) Fast/Debate Path 분기 (기존 ESCALATION_GAP_THRESHOLD = 0.35 유지)
      5) top_detector.run(image_path, product_for_detector) 결과 반환
    """
    ...
```

- 반환 dict는 `detectors/base.py`의 `Detector.run()` 계약 키를 따른다
  (`score`, `threshold`, `decision`, `confidence`, `render_type`, `overlay_path`, `regions`, `model_name`).
- 기존 `VisionAgent` 클래스 메서드는 이 함수를 호출하도록 **얇게** 만들어 로직 중복을 제거한다.
- Debate Path(상위 2개 escalation)의 기존 동작은 그대로 유지하고, 실패 시 1위 탐지기 폴백도 유지.

### 3-B. 입구 전환 — `autonomous_agent.py`

이미지 분기(약 565–575행)의 다음 블록:

```python
from vision_router import VisionRouter
vr = VisionRouter()
vr_result = vr.run(image_path)
```

을 다음으로 교체:

```python
from agents.vision_agent import inspect_via_registry
vr_result = inspect_via_registry(image_path, user_caption=user_input)
```

- `callback({...})` 진행 표시와 `try/except` 골격은 그대로 유지.
- `image_ctx`에 `json.dumps(vr_result, ...)`로 넣는 부분은 그대로 동작해야 하므로,
  `inspect_via_registry` 반환 키가 직렬화 가능한지 확인.

### 3-C. 레거시 경로 차단 — `vision_router.py`

- `_run_ccifps()`, `run_inference()`, `select_best_model()`은 **입구에서 더 이상 호출되지 않아야** 한다.
- 처리 방식(둘 중 하나):
  - (권장) 함수 상단에 `# DEPRECATED: 입구는 inspect_via_registry 사용. 1단계 이후 미사용.` 주석을 달고 호출부를 0개로 만든다.
  - 또는 `_run_ccifps`를 레지스트리의 `cmdiad` 탐지기로 위임하도록 바꾼다.
- 결과적으로 `from cmdiad_inference import ...`를 직접 하는 파일은
  `detectors/cmdiad_detector.py`와 `product_registry.py` **두 곳만** 남아야 한다
  (후자는 3단계에서 처리하므로 이번엔 유지).

---

## 4. 수용 기준 (Acceptance Criteria) — GitHub 소스만으로 검증

> 아래는 코드 실행 없이 `grep`/육안으로 확인 가능한 항목이다. 전부 통과해야 2단계로 넘어간다.

1. `autonomous_agent.py`의 **이미지 분기에서 `VisionRouter` import/호출이 제거**됨.
2. `agents/vision_agent.py`에 모듈 함수 `inspect_via_registry`(합의된 이름)가 존재하고,
   내부에서 `get_registry().rank_for(...)`를 호출한다.
3. 다음 grep이 **입구 코드에서 0건**이다 (테스트 파일·`__main__` 블록 제외):
   ```
   grep -rn "VisionRouter()" autonomous_agent.py
   grep -rn "vr.run(" autonomous_agent.py
   ```
4. 다음 grep 결과가 `detectors/cmdiad_detector.py`, `product_registry.py` **외에는 없다**:
   ```
   grep -rn "from cmdiad_inference\|import cmdiad_inference" --include=*.py .
   ```
5. (선택) README 또는 `autonomous_agent.py` 주석에 `image entry → DetectorRegistry` 한 줄 명시.

---

## 5. 검증 절차 (내가 수행)

완료 후 "푸시 완료"라고 알려주면:
1. 레포를 `git clone`으로 최신 상태로 받는다.
2. 위 4-1 ~ 4-4를 grep으로 확인한다.
3. 전부 통과 → **2단계(VLM 교체 가능화) 명세서** 전달.
4. 일부 불통 → 어느 기준이 왜 막혔는지 정확히 짚어 재수정 요청.

---

## 6. 커밋 / 브랜치

- 브랜치: `refactor/step1-routing-unification`
- 커밋 메시지(예):
  `refactor(routing): route image entry through DetectorRegistry, deprecate legacy CMDIAD dispatch`

---

## 7. 리스크 / 주의

- **결과 키 호환성:** `inspect_via_registry`의 반환 dict가 기존 `vr.run()` 소비처와
  호환되는지 확인 (base.py 표준 키 사용). 키가 달라지면 다운스트림 표시가 깨질 수 있다.
- **Debate Path:** `AgentOrchestrator._run_debate_detectors`를 우회 호출하는 기존 방식은
  그대로 두되, 예외 시 1위 탐지기 폴백을 반드시 유지.
- **범위 엄수:** VLM/백본/MCP/pip은 이번에 손대지 않는다. 한 번에 한 단계.
