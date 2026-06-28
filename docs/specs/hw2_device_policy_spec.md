# ARIA HW-2 명세서 — 디바이스 선택 교정·일원화·가시화 (for Antigravity IDE)

> 자율 자원 에이전트 2단계. **285초의 진짜 원인을 고친다.**
> 핵심 발견: 자동 GPU 선택은 **이미 존재**(`cmdiad_inference.py::_pick_best_gpu`). 285초는 "device=cpu 하드코딩"이 아니라 **GPU 마스킹/가용성** 문제다.

## 0. 배경 (정직한 진단)

- `vision_router.py`(L33–39)가 import 시 `CUDA_VISIBLE_DEVICES`를 `pick_gpus()["vision"]`(실패 시 **"1"**)로 강제. 이 모듈은 라이브 경로(`yolo_detector`, `object_count_detector`, `autonomous_agent`)에서 import됨.
- 머신에 GPU **인덱스 1이 없으면** 모든 GPU가 가려져 → `torch.cuda.is_available()=False` → `_pick_best_gpu()`가 `"cpu"` 반환 → **CPU 추론 285초**.
- 추가 위험: torch가 먼저 초기화되면 `CUDA_VISIBLE_DEVICES` 설정이 **늦어 무효**가 될 수 있음.
- 그 외 산재한 `torch.device("cpu")`(`model_scout.py:543`, `src/patchcore/utils.py:106`)와 `local_agent.py`의 `device="cpu"`는 **표준이 아닌/스탠드얼론** 경로 — 라이브와 구분 필요.

## 0.5. **선행 조건 — 4-4로 케이스 확정 먼저**

HW-1 `HardwarePanel`/`curl /api/hardware`로 확인:
- **케이스 A:** `gpus`에 GPU가 보이는데(예: 인덱스 0) SCAN 시 util≈0 → **마스킹 문제**. 이 명세서가 285초를 고침.
- **케이스 B:** `cuda_available=false`·`gpus=[]` → torch가 CUDA 빌드가 아님(설치/드라이버). **코드로 못 고침** — CUDA용 torch 설치가 필요. 이 경우 본 명세서는 "왜 CPU인지 시끄럽게 노출"까지만.

## 1. 범위 (Scope)

**포함:**
- P1) `vision_router.py`의 `CUDA_VISIBLE_DEVICES` 마스킹 교정 (**285초 핵심 수정**)
- P2) 추론이 실제로 어떤 디바이스에서 도는지 **가시화**(DIAGNOSTIC + 로그)
- P3) 디바이스 선택을 `ResourcePolicy.choose_device()` **단일 seam**으로 일원화

**제외(HW-3):** VRAM 부족 시 모델/배치/큐/OOM 중단 제어. 비라이브 device 코드(patchcore util, local_agent) 리팩터.

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `vision_router.py` | `CUDA_VISIBLE_DEVICES`를 **실존 인덱스일 때만** 설정, 아니면 마스킹 안 함 (P1) |
| `resource/policy.py` (신규) | `choose_device()` — 실가용 GPU 중 free-VRAM 최대 선택 + 사유 반환 (P3) |
| `cmdiad_inference.py` | `_pick_best_gpu` → `resource.policy.choose_device` 사용(또는 위임) + 해석된 device 로깅 (P2/P3) |
| `detectors/cmdiad_detector.py` (또는 결과 경로) | 결과 dict에 `device`·`device_reason` 포함 (P2) |
| `frontend` DIAGNOSTIC | "Device: cuda:0 / CPU ⚠ 느림" 표기 (P2) |

## 3. 작업 명세 (What)

### 3-P1. `vision_router.py` — 마스킹 교정 (핵심)
현재(L33–39)를 **실존 인덱스 검증**으로 교체:
```python
import os
# ── GPU 격리: 실존하는 인덱스일 때만 마스킹 ──
def _safe_set_visible_devices():
    try:
        import torch
        n = torch.cuda.device_count()        # 마스킹 전 실제 개수
    except Exception:
        n = 0
    target = None
    try:
        from utils.gpu_selector import pick_gpus
        target = int(pick_gpus()["vision"])
    except Exception:
        target = None
    # target이 실존 범위 안일 때만 설정. 아니면 마스킹하지 않음(자동선택에 맡김).
    if target is not None and 0 <= target < n:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(target)
    # else: 손대지 않음 → 모든 GPU 가시 → 정책이 best-VRAM 선택
_safe_set_visible_devices()
```
> 더 이상 **"1" 무조건 강제 금지.** 인덱스 1이 없으면 마스킹하지 않아 GPU가 살아 있게 둔다.
> (주의: 이 코드는 torch가 CUDA를 초기화하기 *전에* 실행돼야 효과가 있다 — 모듈 최상단 유지.)

### 3-P3. `resource/policy.py` (신규) — 디바이스 정책 seam
`_pick_best_gpu` 로직을 여기로 모아 사유까지 반환:
```python
def choose_device() -> tuple[str, str]:
    """(device, reason) 반환. 라이브 추론이 공통으로 호출하는 단일 진입점."""
    try:
        import torch
        if not torch.cuda.is_available():
            return "cpu", "CUDA 미가용(torch가 CPU 빌드이거나 GPU 미감지)"
        best, best_free = 0, -1
        for i in range(torch.cuda.device_count()):
            free, total = torch.cuda.mem_get_info(i)
            if free > best_free:
                best, best_free = i, free
        return f"cuda:{best}", f"GPU {best} 선택(free VRAM 최대 {best_free//1048576}MB)"
    except Exception as e:
        return "cpu", f"디바이스 탐색 실패→CPU ({e})"
```

### 3-P2. 가시화 — 어떤 디바이스로 돌았는지 항상 보이게
- `cmdiad_inference.py`: 디바이스 확정 직후 1줄 로그 + 결과/엔진에 보관:
  ```python
  from resource.policy import choose_device
  dev, reason = choose_device()
  self.device = dev
  print(f"  [CMDIAD] device={dev} ({reason})")
  ```
- 검사 결과 dict에 `"device": dev, "device_reason": reason` 추가 → DIAGNOSTIC가 표시:
  - `cuda:*` → "Device: cuda:0" (정상)
  - `cpu` → "Device: CPU ⚠ 느림 — {reason}" (사용자가 즉시 원인 인지)

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "device_count()\|CUDA_VISIBLE_DEVICES" vision_router.py   # '1' 무조건 강제 제거 확인
grep -n "def choose_device" resource/policy.py
grep -n "choose_device\|device=" cmdiad_inference.py
grep -rn "device_reason\|Device:" frontend/src/components/   # 가시화
```
- `vision_router.py`에 `= \"1\"` 무조건 분기가 **없어야**:
  ```
  grep -n 'CUDA_VISIBLE_DEVICES.*=.*"1"' vision_router.py   # → 0건(또는 실존검증 안)
  ```

### 4-2. Headless smoke (내가 실행)
- `from resource.policy import choose_device; choose_device()` → GPU 없는 환경에서 `("cpu", "CUDA 미가용…")` 예외 없이 반환.

### 4-3. 회귀 가드
```
grep -c "frontend/dist/index.html" app.py        # 서빙 일원화
grep -c "/api/train/upload" app.py                # 6A
grep -c "get_snapshot" app.py                     # HW-1
grep -c "inspect_via_registry" autonomous_agent.py # 1~4단계
python -m py_compile vision_router.py resource/policy.py cmdiad_inference.py
```

### 4-4. 런타임 (당신 — 결정적)
- **케이스 A에서:** SCAN 시간이 **285초 → 수 초**로 급감, HW-1 패널에서 **GPU util 급증**, DIAGNOSTIC에 "Device: cuda:0".
- **케이스 B에서:** 여전히 CPU지만 DIAGNOSTIC/로그가 "Device: CPU ⚠ — CUDA 미가용"로 **원인을 명시** → CUDA torch 설치가 다음 액션.
- Antigravity 녹화로 전/후 시간 + 디바이스 표기 첨부.

## 5. 검증 절차 (내가 수행)
"푸시 완료" → 재clone → 4-1 grep, 4-2 smoke, 4-3 회귀. 4-4(시간 급감/디바이스 표기)는 당신 캡처. 통과 시 HW-3(VRAM 기반 모델/배치/큐 자율 제어)로.

## 6. 커밋
- 브랜치: `feat/hw2-device-policy`
- 메시지(예): `fix(hw): stop masking GPUs to nonexistent index, centralize device policy, surface active device`

## 7. 주의
- **4-4(케이스 A/B 확정)를 먼저.** 케이스 B면 이 코드는 285초를 못 줄인다(설치 문제) — 그땐 "왜 CPU인지" 노출까지가 성과.
- `CUDA_VISIBLE_DEVICES`는 **torch CUDA 초기화 전**에만 효과 — `vision_router` 최상단 유지, 그리고 앱 어디서도 그 전에 torch.cuda를 만지지 않는지 주의.
- **범위 엄수:** VRAM 부족 시 모델 다운그레이드·배치·큐·OOM 중단은 HW-3. 여기선 "올바른 디바이스 + 가시화"까지만.
- 비라이브 `torch.device("cpu")`(patchcore util, local_agent 등)는 건드리지 말 것 — 라이브 경로만.
