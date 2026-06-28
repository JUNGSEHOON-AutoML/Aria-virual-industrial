# ARIA 명세서 — 핫픽스: 뱅크빌드 차단 버그 + 중앙 검사대 제거 for Antigravity

> 1순위(차단): `'type' object is not subscriptable` 수정 → 뱅크 빌드/학습/판정 복구. 2순위: 빨간 동그라미(중앙 검사대) 제거.

## 1. [P1 · 차단 버그] policy.py 3.8 호환

**원인 확정:** `resource/policy.py` L1 `def choose_device() -> tuple[str, str]:` — `tuple[str, str]`(PEP 585 generic)은 **Python 3.8에서 import 시 평가되며 `'type' object is not subscriptable`**. `policy`는 `cmdiad_inference.CMDIADInference.__init__`(L130)에서 *지연 import*라 **첫 뱅크 빌드 때** 터짐 → `/api/class/train`·`/api/sim/train` 워커가 모두 실패(로그의 `[sim_train] bank build 실패`).

**수정(한 줄):** `resource/policy.py` **맨 위**에 추가:
```python
from __future__ import annotations   # 어노테이션 지연평가 → tuple[str,str]가 런타임에 평가되지 않음 (3.8 호환)
```
- 이러면 파일 내 모든 어노테이션이 문자열로 처리돼 런타임 평가 안 됨. `choose_device`의 동작은 불변.
- (대안: `from typing import Tuple` + `-> Tuple[str, str]`. 하지만 future-import가 더 깔끔하고 파일 전체를 방어함.)

## 2. [P2 · 정리] 중앙 검사대(빨간 동그라미) 제거

스크린샷의 빨간 동그라미 = **중앙 단일 검사대**(작업대/테이블 + 회색 placeholder 부품 + 발광 링 + `PART [PLACEHOLDER]` 라벨). 이제 각 *라인*이 검사하므로 중앙 검사대는 불필요.

**제거 대상(SimulationView.jsx):**
- `InspectionCell` 내 **Workbench(테이블/다리)** + **InspectionPart(placeholder 부품)** + 중앙 **발광 링/halo** 메쉬.
- `SceneLabels`의 **`PART [PLACEHOLDER]`** 라벨.

**보존(건드리지 말 것):**
- **`GLBridge`(glRef) — 캡처 카메라.** 절대 제거 금지.
- 조명(Lights), `<FactoryLine>`(라인·작업자·설비), StatusBoard(공장 현황판 — 이건 중앙 모니터지 검사대가 아님; 유지).

> ⚠️ 캡처 영향(솔직): 중앙 부품이 사라지면 *옛 합성-캡처 경로*(captureDataset→/api/sim/train)는 빈 무대를 찍게 됨. 하지만 **현재 실제 흐름은 MVTec 클래스 학습(/api/class/*)** 이라 영향 없음. 합성 캡처를 다시 쓰려면 라인 부품을 피사체로 (후속).

## 3. 수용 기준

### 3-1. Greppable
```
head -3 resource/policy.py | grep -c "from __future__ import annotations"     # 1
grep -c "InspectionPart\|Workbench\|PART \[PLACEHOLDER\]\|PART_PLACEHOLDER" frontend/src/components/SimulationView.jsx  # 0 (제거)
grep -c "GLBridge\|glRef" frontend/src/components/SimulationView.jsx           # 보존(≥1)
grep -c "FactoryLine\|factoryGroupRef" frontend/src/components/SimulationView.jsx  # 라인·캡처가드 보존
```

### 3-2. 구문/빌드
```
python -m py_compile resource/policy.py cmdiad_inference.py app.py
# npm run build (Node20) 무에러
```

### 3-3. 런타임 (당신 — 핵심 복구 확인)
- `./start_aria.sh` 재기동 → **"🔮 클래스별 가동"** → 로그에 **더 이상 `'type' object is not subscriptable` 없음**, 대신 `[ProductRegistry/DINO] ... 로드` 후 뱅크 빌드 진행 → `banks/bottle.npy` 등 생성 → 라인에 진짜 escape·PASS/FAIL.
- 화면에서 **중앙 검사대(빨간 동그라미)가 사라짐**.

## 4. 검증 (내가 수행)
재clone → 3-1 grep(future import·중앙검사대 제거·GLBridge 보존) + 3-2 py_compile. 실제 뱅크 빌드 성공은 GPU라 당신 런타임 로그로 확인.

## 5. 커밋
- main 직접. 메시지: `fix(device): py3.8 annotation compat (unblocks bank build) + remove central inspection cell`

## 6. 주의
- **P1이 최우선** — 이거 없으면 학습/판정 전부 실패. 한 줄이지만 차단 해제의 핵심.
- `GLBridge`/`glRef`(캡처 카메라) **보존**. StatusBoard(현황판) 유지 — 검사대만 제거.
- 다른 파일에 동일한 3.8 비호환 어노테이션은 없음(확인됨 — policy.py만).
