# ARIA 리팩터링 3단계 명세서 — 백본 분리 (Pluggable Backbone)

## 0. 목표 (Why)

제품 식별/등록(`product_registry.py`)이 CMDIAD의 DINO ViT-B/8에 직접 묶여 있다.
`Backbone` seam을 만들어 **식별 임베딩 추출기를 교체 가능**하게 하고,
`product_registry.py`에서 `cmdiad_inference` 직접 의존을 **완전히 제거**한다.

결과: CMDIAD 의존이 (1)탐지기 플러그인, (2)캘리브레이터, (3)백본 seam 기본구현
**세 곳에만 캡슐화**되고, 범용 컴포넌트인 `product_registry`는 CMDIAD를 모른다.
현재 동작(DINO ViT-B/8)은 **기본값으로 그대로 보존**.

---

## 1. 범위 (Scope)

**포함:**
- `Backbone` 인터페이스 + `DinoViTB8Backbone` 기본 구현 + `get_backbone()` 셀렉터 신규
- `product_registry.enroll()` / `identify()`의 피처 추출을 seam 경유로 전환
- enroll의 임계값 캘리브레이션을 `ThresholdCalibrator`로 위임
- `DATASET_DIR` 의존을 config/env로 이전
- 결과적으로 `product_registry.py`의 `from cmdiad_inference import ...` **전부 제거**

**제외(다음 단계 — 건드리지 말 것):**
- `DinoViTB8Backbone`이 내부에서 `cmdiad_inference`의 DINO를 래핑하는 것은 허용(분리 비용 큼). DINO 클래스를 별도 모듈로 빼는 것은 향후.
- `MCPDetector`/MCP 어댑터 → 4단계
- 런타임 pip 제거 → 5단계

---

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `config/backbone.py` (신규) | `Backbone` Protocol + `DinoViTB8Backbone` + `get_backbone()` |
| `product_registry.py` | enroll/identify 피처 추출 → `get_backbone().extract_features()`; 캘리브레이션 → `ThresholdCalibrator` 위임; `DATASET_DIR` → config; `cmdiad_inference` import 전부 제거 |
| `config/models.py` (선택) | `DATASET_DIR` 또는 데이터 경로 상수 추가(또는 env로 처리) |

---

## 3. 작업 명세 (What)

### 3-A. `config/backbone.py` 신규 — seam 정의

```python
from __future__ import annotations
import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class Backbone(Protocol):
    name: str
    def extract_features(self, image_path: str):
        """이미지 경로 → 패치 피처 텐서 [N, D]."""
        ...


class DinoViTB8Backbone:
    """기본 백본 — 기존 DINO ViT-B/8 래핑(동작 100% 보존)."""
    name = "dino_vit_b8"

    def __init__(self):
        self._engine = None

    def _ensure(self):
        if self._engine is None:
            from cmdiad_inference import CMDIADInference
            self._engine = CMDIADInference()
        return self._engine

    def extract_features(self, image_path: str):
        from cmdiad_inference import preprocess_image
        eng = self._ensure()
        tensor = preprocess_image(image_path)
        return eng.backbone.extract_features(tensor)   # [784, 768]


_BACKBONE_SINGLETON: Backbone | None = None

def get_backbone() -> Backbone:
    """활성 백본 반환. env ARIA_BACKBONE 로 선택(기본 'dino_vit_b8')."""
    global _BACKBONE_SINGLETON
    if _BACKBONE_SINGLETON is None:
        kind = os.environ.get("ARIA_BACKBONE", "dino_vit_b8").lower()
        # 향후 'dinov2', 'clip', 'timm:<name>' 분기 추가 예정 — 지금은 dino만
        _BACKBONE_SINGLETON = DinoViTB8Backbone()
    return _BACKBONE_SINGLETON
```

> 기본 구현이 내부에서 `cmdiad_inference`의 DINO를 lazy import해 래핑하는 건 허용된다(범위 §1).
> 핵심은 `product_registry`가 더 이상 CMDIAD를 직접 알지 않는다는 것.

### 3-B. `product_registry.py` — 피처 추출 위임

`enroll()`(약 67·78–79행):

```python
# AS-IS
engine = CMDIADInference()
...
tensor = preprocess_image(img_path)
features = engine.backbone.extract_features(tensor)

# TO-BE
from config.backbone import get_backbone
bb = get_backbone()
...
features = bb.extract_features(img_path)
```

`identify()`(약 248·251–252행) 동일하게 `get_backbone().extract_features(image_path)`로 교체.
코사인 유사도 판정 로직(STRICT/LOOSE threshold 등)은 그대로 둔다.

### 3-C. enroll 캘리브레이션 위임

enroll 내부의 임계값 산출 루프(약 129–155행, `engine.run(img_path, product_id)`로 점수 모아 mean+3std)는
이미 동일 로직을 가진 `ThresholdCalibrator.calibrate(product_id)`로 위임한다:

```python
from threshold_calibrator import ThresholdCalibrator
...
# 제품 메타 등록 후
ThresholdCalibrator(self).calibrate(product_id)
```

- `ThresholdCalibrator`는 `cmdiad_inference`를 정당하게 import하므로 CMDIAD 캘리브레이션은 거기서 일어난다.
- 이로써 `product_registry`에서 `engine.run()` / `CMDIADInference` 직접 호출이 사라진다.

> 참고: `threshold_calibrator.calibrate`가 mean+3std로 임계값을 잡는 통계 이슈(가우시안 가정·n=100 등)는
> 별도 개선 주제다. 3단계에서는 **위임만** 하고 통계식은 건드리지 않는다(범위 엄수).

### 3-D. `DATASET_DIR` 이전

`_auto_enroll_mvtec_if_empty`(약 32행)의 `from cmdiad_inference import DATASET_DIR`를 제거하고
env/config로 대체:

```python
import os
DATASET_DIR = os.environ.get("DATASET_BASE_PATH", "")  # 또는 config/models.py 상수
```

---

## 4. 수용 기준 (Acceptance Criteria) — GitHub grep로 검증

1. 백본 seam 정의:
   ```
   grep -n "class Backbone\|class DinoViTB8Backbone\|def get_backbone" config/backbone.py
   ```
2. `product_registry`가 seam 사용:
   ```
   grep -n "get_backbone\|extract_features" product_registry.py
   ```
3. `product_registry.py`에 `cmdiad_inference` 직접 import **0건**:
   ```
   grep -n "cmdiad_inference" product_registry.py   # → 0건
   ```
   전역 허용 목록(3곳)으로 수렴 — `product_registry` 빠지고 `config/backbone.py` 추가:
   ```
   grep -rn "from cmdiad_inference\|import cmdiad_inference" --include=*.py . | grep -v "_deprecated/"
   # 허용: detectors/cmdiad_detector.py, threshold_calibrator.py, config/backbone.py
   ```
4. (회귀 가드) 1·1.5·2단계 유지:
   ```
   grep -n "inspect_via_registry" autonomous_agent.py
   grep -n "get_vlm" agents/vision_agent.py
   grep -n "run_inference(" harness_loop.py        # → 0건
   ```

> 1·2·3 통과 + 4 회귀 없음이면 완료.

---

## 5. 검증 절차 (내가 수행)

"푸시 완료" → 브랜치 재clone → 4-1~4-4 grep 확인 →
통과 시 다음 단계 명세서 전달.

---

## 6. 커밋

- 브랜치: `refactor/step3-pluggable-backbone` (또는 기존 브랜치 연속)
- 메시지(예): `refactor(backbone): introduce Backbone seam, decouple product_registry from cmdiad_inference`

---

## 7. 주의 / 검증 포인트

- **동작 보존:** `ARIA_BACKBONE` 기본값 `dino_vit_b8` → 기존 식별/등록과 동일 결과여야 한다.
  enrolled 판정 유사도 임계값(STRICT/LOOSE)은 변경 금지.
- **캘리브레이션 동치성:** enroll이 직접 돌리던 mean+3std와 `ThresholdCalibrator.calibrate`의 산출이
  같은 good_images_dir·동일 n에서 같은 임계값을 내는지 확인(위임 전후 회귀 없게).
- **lazy import 유지:** `DinoViTB8Backbone`이 `cmdiad_inference`를 모듈 최상단이 아니라 메서드 내부에서
  import하도록 둬서, 백본 미사용 경로의 불필요한 무거운 로드를 피한다.
- **범위 엄수:** 통계식·MCP·pip은 이번에 손대지 않는다. 한 번에 한 단계.
