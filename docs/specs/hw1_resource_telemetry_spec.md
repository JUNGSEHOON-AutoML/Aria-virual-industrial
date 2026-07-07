# ARIA HW-1 명세서 — 하드웨어 텔레메트리 (관측 seam) for Antigravity IDE

> 자율 자원 에이전트의 1단계. **읽기전용 관측만.** 디바이스 변경(HW-2)·자율 제어(HW-3)는 범위 밖.
> 목적: GPU·VRAM·CPU를 구조화된 실시간 수치로 본다 → 285초 추론이 CPU-bound인지 *증명*한다.

## 0. 배경 (Why)

- `skills/ccifps_vision/local_agent.py`가 `device="cpu"` 고정 → 추론이 CPU에서 돌아 285초로 추정.
- 현재 "GPU 상태"는 `nvidia-smi` 텍스트 덤프뿐(autonomous_agent.py:483). 구조화된 텔레메트리 없음.
- HW-1은 이를 **구조화·실시간화**한다. 측정이 되어야 HW-2/3에서 제어한다.

## 1. 범위 (Scope)

**포함:** `ResourceMonitor`(GPU/VRAM/CPU/RAM/온도 샘플링) + `ResourceSnapshot` 스키마 + `GET /api/hardware` + React `HardwarePanel`(2초 폴링).
**제외(다음):** 디바이스 자동선택(HW-2), 모델/배치/큐/OOM 제어(HW-3), 프로세스·OS 제어(영구 범위 밖).

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `hardware/monitor.py` (신규) | `get_snapshot()` + `ResourceSnapshot`(GPU 없거나 pynvml 미설치 시 graceful fallback) |
| `app.py` | `GET /api/hardware` → `get_snapshot()` |
| `requirements.txt` | `pynvml`(nvidia-ml-py), `psutil` 추가 |
| `frontend/src/api/apiClient.js` | `fetchHardware()` → GET /api/hardware |
| `frontend/src/components/HardwarePanel.jsx` (신규) | GPU util·VRAM·CPU·RAM 실시간 바, 2초 폴링 |
| `frontend/src/components/Dashboard.jsx` | `HardwarePanel` 마운트(기존 'GPU 상태 확인' 모달 대체/승격) |

## 3. 작업 명세 (What)

### 3-A. `hardware/monitor.py` — 관측 (graceful fallback 필수)
```python
import time
try: import psutil
except Exception: psutil = None
try:
    import pynvml; pynvml.nvmlInit(); _NVML = True
except Exception: _NVML = False
try:
    import torch; _CUDA = torch.cuda.is_available()
except Exception: _CUDA = False

def get_snapshot() -> dict:
    """읽기전용 하드웨어 스냅샷. GPU/pynvml 없으면 gpus=[]로 안전 폴백."""
    gpus = []
    if _NVML:
        try:
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                mem = pynvml.nvmlDeviceGetMemoryInfo(h)
                util = pynvml.nvmlDeviceGetUtilizationRates(h)
                name = pynvml.nvmlDeviceGetName(h)
                gpus.append({
                    "index": i,
                    "name": name.decode() if isinstance(name, bytes) else name,
                    "util_pct": util.gpu,
                    "vram_used_mb": mem.used // 1048576,
                    "vram_total_mb": mem.total // 1048576,
                    "temp_c": pynvml.nvmlDeviceGetTemperature(h, 0),
                })
        except Exception:
            pass
    cpu = psutil.cpu_percent(interval=None) if psutil else None
    vm = psutil.virtual_memory() if psutil else None
    return {
        "ts": time.time(),
        "cuda_available": _CUDA,
        "gpus": gpus,
        "cpu_pct": cpu,
        "ram_used_mb": (vm.used // 1048576) if vm else None,
        "ram_total_mb": (vm.total // 1048576) if vm else None,
    }
```

### 3-B. `app.py` — 엔드포인트
```python
from hardware.monitor import get_snapshot

@app.get("/api/hardware")
async def hardware():
    return get_snapshot()
```
> (선택) 나중에 WS 푸시를 원하면 6A처럼 event_bus("hardware") 발행 + broadcast 브리지. HW-1은 폴링으로 충분.

### 3-C. `frontend/src/api/apiClient.js`
```javascript
export async function fetchHardware() {
  const { data } = await api.get('/api/hardware')
  return data
}
```

### 3-D. `frontend/src/components/HardwarePanel.jsx` (신규)
- `useEffect`로 2초마다 `fetchHardware()` 폴링(기존 `fetchState` 폴링 패턴 그대로).
- 표시: 각 GPU의 `util_pct`·`vram_used_mb/vram_total_mb`(바), `temp_c`; `cpu_pct`; `ram_used/total`; `cuda_available` 뱃지.
- GPU 없으면("gpus":[]) "GPU 미감지 / CPU 모드"로 표시 → **285초의 원인이 한눈에**.
- 스타일은 기존 패널 톤(glass-panel, var(--cyan)/(--green)) 따름.

### 3-E. `Dashboard.jsx` — 마운트
- `HardwarePanel`을 좌측 또는 상단에 마운트. 기존 'GPU 상태 확인' 퀵액션(nvidia-smi 모달)은 이 패널로 대체(승격).

## 4. 수용 기준

### 4-1. Greppable (배선)
```
grep -n "def get_snapshot\|ResourceSnapshot\|pynvml\|psutil" hardware/monitor.py
grep -n "/api/hardware\|get_snapshot" app.py
grep -n "fetchHardware\|/api/hardware" frontend/src/api/apiClient.js
test -f frontend/src/components/HardwarePanel.jsx && echo OK
grep -n "HardwarePanel" frontend/src/components/Dashboard.jsx
grep -ni "pynvml\|psutil" requirements.txt
```

### 4-2. Headless smoke (내가 실행 — GPU 없이도)
- `get_snapshot()`가 예외 없이 dict 반환, `cpu_pct`·`ram_total_mb`가 숫자, GPU 없으면 `gpus==[]`·`cuda_available in {true,false}`.

### 4-3. 회귀 가드
```
grep -c "frontend/dist/index.html" app.py        # 서빙 일원화 유지
grep -c "/api/train/upload" app.py                # 6A 유지
grep -c "inspect_via_registry" autonomous_agent.py # 1~4단계 유지
python -m py_compile hardware/monitor.py app.py
```

### 4-4. 런타임 (당신 — 핵심 증명)
- GPU 머신에서 `curl -s localhost:8080/api/hardware | python3 -m json.tool` → gpus 채워짐.
- HardwarePanel 실시간 갱신 확인.
- **검사(SCAN)를 돌리는 동안** 패널을 보면: GPU util ≈ 0 / CPU ≈ 100 이면 → **CPU-bound 확정**(HW-2의 정당화). Antigravity 녹화 첨부.

## 5. 검증 절차 (내가 수행)
"푸시 완료" → 재clone → 4-1 grep, 4-2 smoke 실행, 4-3 회귀. 4-4는 당신 캡처로. 통과 시 **HW-2(디바이스 자동선택, 285초→수초)** 명세서로.

## 6. 커밋
- 브랜치: `feat/hw1-resource-telemetry`
- 메시지(예): `feat(hw): read-only resource telemetry (GPU/VRAM/CPU) via /api/hardware + HardwarePanel`

## 7. 주의
- **읽기전용 엄수.** HW-1은 측정만 — `local_agent.py`의 `device` 등 어떤 실행 로직도 바꾸지 않는다(그건 HW-2).
- pynvml/psutil 미설치·GPU 부재에서도 **절대 죽지 않게**(try/except 폴백) — 검사 시스템 본체에 영향 0.
- `psutil.cpu_percent(interval=None)`는 첫 호출이 0을 반환할 수 있으니, 패널이 2초 폴링이라 두 번째부터 정상값.
