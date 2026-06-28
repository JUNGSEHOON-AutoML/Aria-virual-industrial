# ARIA 6단계 (슬라이스 6A) 명세서 — ZIP 드롭 → 더미 학습 실시간 시청

## 0. 목표 (Why)

"압축파일을 넣으면 학습 장면이 도는 걸 내 눈으로 본다"를 **실제 학습·CAD 없이** 끝까지 연결한다.
1~4단계와 같은 seam 패턴: **`TrainingEvent`라는 seam을 정의**하고, **더미 producer**로 끝까지
흐르게 한 뒤, 나중에 producer만 더미→실제→CAD로 교체한다.

흐름:
```
ZIP 업로드 → (최소 인제스트: unzip+카운트+manifest)
          → 더미 학습 producer (가짜 loss·프리뷰 N스텝)
          → publish(TrainingEvent) → event_bus("training")
          → [브리지] → manager.broadcast → WebSocket → 대시보드 패널
```

---

## 1. 범위 (Scope)

**포함:**
- `TrainingEvent` seam (스키마 + 토픽 상수 + 빌더)
- 최소 ZIP 인제스트 (unzip + 이미지 카운트 + 폴더기반 클래스 + `manifest.json` 작성)
- 더미 학습 producer — **주입된 `publish` 콜백**으로 이벤트 발행(웹 계층과 디커플링)
- `event_bus("training") → manager.broadcast` 브리지(app 시작 시 1회 구독)
- 업로드 엔드포인트 `POST /api/train/upload` + 백그라운드 스레드로 더미 학습 기동
- 대시보드가 `type:"training"` 메시지를 진행 패널로 렌더

**제외(명시적으로 손대지 않음 — 다음 슬라이스):**
- tar/WebDataset 샤딩, 에이전트의 샤딩 "판단" → 6B
- MCP 관측 서버(get_status/pause 등) → 6C
- 실제 학습기 → 6D
- CAD/Omniverse 렌더 → 6E

---

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `training/events.py` (신규) | `TRAINING_TOPIC` + `make_training_event(...)` (seam) |
| `training/ingest.py` (신규) | `ingest_zip(zip_path, work_dir) -> manifest`(unzip+카운트+manifest, **tar 없음**) |
| `training/dummy_trainer.py` (신규) | `run_dummy_training(run_id, manifest, publish, n_steps=20)` — 주입 publish로 이벤트 발행 |
| `app.py` | `POST /api/train/upload` 엔드포인트 + event_bus→broadcast 브리지 + 백그라운드 기동 |
| `static/js/main.js` | `type:"training"` 수신 시 진행 패널 렌더(진행바·loss·프리뷰) |

---

## 3. 작업 명세 (What)

### 3-A. `training/events.py` — seam

```python
import time

TRAINING_TOPIC = "training"

def make_training_event(run_id, step, total_steps, status,
                        loss=None, preview_image=None) -> dict:
    """대시보드/WS가 소비하는 표준 학습 진행 이벤트.
    type='training'은 WS 메시지 라우팅 디스크리미네이터."""
    return {
        "type": TRAINING_TOPIC,
        "run_id": run_id,
        "step": step,
        "total_steps": total_steps,
        "status": status,            # "running" | "done" | "error"
        "metrics": {"loss": loss},
        "preview_image": preview_image,   # 대시보드가 표시할 경로/URL (없으면 None)
        "ts": time.time(),
    }
```

### 3-B. `training/ingest.py` — 최소 인제스트 (tar 없음)

```python
import os, json, zipfile
from pathlib import Path

_IMG_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

def ingest_zip(zip_path: str, work_dir: str) -> dict:
    """ZIP을 풀고 이미지 수/클래스를 집계해 manifest.json을 쓴다.
    [범위] tar/샤딩/판단 없음 — 6B로 미룸."""
    out = Path(work_dir)
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out)

    images, classes = [], {}
    for root, _, files in os.walk(out):
        for fn in files:
            if Path(fn).suffix.lower() in _IMG_EXT:
                images.append(os.path.join(root, fn))
                cls = Path(root).name
                classes[cls] = classes.get(cls, 0) + 1

    manifest = {
        "n_images": len(images),
        "classes": classes,
        "images": images[:200],      # 프리뷰용 일부만 보관
        "work_dir": str(out),
    }
    with open(out / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest
```

### 3-C. `training/dummy_trainer.py` — 디커플링된 producer

```python
import time, math
from training.events import make_training_event

def run_dummy_training(run_id: str, manifest: dict, publish, n_steps: int = 20,
                       step_delay: float = 0.4) -> None:
    """가짜 학습 — 주입된 publish(event)로만 외부와 통신(웹/버스 의존 없음).
    preview는 업로드 이미지를 순환시켜 '움직이는 장면' 느낌을 준다."""
    imgs = manifest.get("images", []) or [None]
    try:
        for step in range(1, n_steps + 1):
            loss = round(2.0 * math.exp(-3.0 * step / n_steps) + 0.05, 4)  # 감소 곡선
            preview = imgs[step % len(imgs)]
            publish(make_training_event(run_id, step, n_steps, "running",
                                        loss=loss, preview_image=preview))
            time.sleep(step_delay)
        publish(make_training_event(run_id, n_steps, n_steps, "done", loss=loss,
                                    preview_image=imgs[-1]))
    except Exception as e:
        publish(make_training_event(run_id, 0, n_steps, "error"))
        raise
```

### 3-D. `app.py` — 브리지 + 엔드포인트 + 기동

**(1) event_bus → broadcast 브리지** (startup, event_bus.start 직후):

```python
from event_bus import event_bus
from training.events import TRAINING_TOPIC

async def _bridge_training_to_ws(event: dict):
    await manager.broadcast(event)

event_bus.subscribe(TRAINING_TOPIC, _bridge_training_to_ws)
```

**(2) 업로드 엔드포인트** (`/api/analyze`의 UploadFile 패턴 재사용):

```python
import asyncio, threading, uuid, time
from pathlib import Path
from training.ingest import ingest_zip
from training.dummy_trainer import run_dummy_training
from event_bus import event_bus
from training.events import TRAINING_TOPIC

@app.post("/api/train/upload")
async def train_upload(file: UploadFile = File(...)):
    run_id = f"run_{int(time.time())}"
    zip_path = UPLOAD_DIR / f"{run_id}.zip"
    zip_path.write_bytes(await file.read())

    work_dir = UPLOAD_DIR / run_id
    manifest = ingest_zip(str(zip_path), str(work_dir))

    loop = asyncio.get_running_loop()
    def _publish(ev):
        asyncio.run_coroutine_threadsafe(event_bus.publish(TRAINING_TOPIC, ev), loop)

    threading.Thread(
        target=run_dummy_training, args=(run_id, manifest, _publish),
        daemon=True).start()

    return {"run_id": run_id, "n_images": manifest["n_images"],
            "classes": manifest["classes"], "status": "training_started"}
```

> producer는 `_publish` 콜백만 알고 event_bus·manager를 직접 모른다(디커플링).
> 스레드→메인 루프 발행은 확립된 `run_coroutine_threadsafe` 패턴을 따른다(publish_sync 사용 금지).

### 3-E. `static/js/main.js` — 진행 패널

기존 WS `onmessage` 바인더(약 489행)에 분기 추가:

```javascript
if (data.type === "training") {
    renderTrainingPanel(data);   // 진행바(step/total_steps), loss, preview_image 표시
    return;
}
```

`renderTrainingPanel`은 간단한 DOM 갱신으로 충분(전용 컴포넌트 신규는 선택).
React 프론트(`frontend/`)를 쓴다면 동일하게 `type==="training"` 분기를 추가.

---

## 4. 수용 기준 (3층 검증)

### 4-1. Greppable seam (객관)
```
grep -n "TRAINING_TOPIC\|def make_training_event" training/events.py
grep -n "def ingest_zip\|zipfile\|manifest" training/ingest.py
grep -n "def run_dummy_training\|publish(" training/dummy_trainer.py
grep -n "/api/train/upload\|event_bus.subscribe\|run_coroutine_threadsafe" app.py
grep -n "training" static/js/main.js
```
- `training/ingest.py`에 `tar` / `webdataset` 문자열이 **없을 것**(범위 밖):
  ```
  grep -ni "tarfile\|webdataset" training/ingest.py   # → 0건
  ```

### 4-2. Runnable smoke (객관 — 제가 헤드리스로 실행, GPU 불필요)
- 작은 더미 ZIP 만들어 `ingest_zip` → `manifest["n_images"]`가 실제 이미지 수와 일치.
- `run_dummy_training(run_id, manifest, publish=collector.append)` 호출 → 수집된 이벤트가
  `n_steps + 1`건이고 마지막 `status=="done"`, `loss`가 단조 감소.

### 4-3. 회귀 가드 (객관)
```
grep -c "inspect_via_registry" autonomous_agent.py   # > 0
grep -c "get_vlm" agents/vision_agent.py             # > 0
grep -c "get_backbone" product_registry.py           # > 0
grep -c "run_inference(" harness_loop.py             # = 0
grep -n "mcpDetectors" mcp_config.json               # 존재
python -m py_compile training/events.py training/ingest.py training/dummy_trainer.py app.py
```

### 4-4. Human-watch (당신만 가능 — 핵심)
- 대시보드를 열고 ZIP을 업로드 → **진행바·loss·프리뷰가 실제로 움직이는지** 눈으로 확인.
- Antigravity 브라우저로 그 화면을 **스크린샷 또는 짧은 녹화**해서 walkthrough에 첨부 → "봤다"의 증거.

> 4-1·4-2·4-3 통과 + 4-4 시각 증거 첨부면 6A 완료.

---

## 5. 검증 절차 (내가 수행)

"푸시 완료" → 브랜치 재clone → 4-1(grep)·4-2(헤드리스 smoke 실행)·4-3(회귀) 확인.
4-4는 당신의 스크린샷/녹화로 확인. 통과 시 6B(ZIP→tar 샤딩 + 에이전트 판단) 명세서로 진행.

---

## 6. 커밋

- 브랜치: `feat/step6a-live-training-view`
- 메시지(예): `feat(observe): ZIP→dummy-train→live dashboard via TrainingEvent seam on event_bus`

---

## 7. 주의 / 설계 포인트

- **producer 디커플링이 핵심.** `run_dummy_training`은 `publish` 콜백만 받는다 — event_bus·FastAPI·manager를 import하지 않는다. 그래야 6D(실제 학습)·6E(CAD)가 같은 함수 시그니처로 자리만 바꾸면 된다.
- **스레드→루프 발행은 `run_coroutine_threadsafe`로.** `publish_sync`를 워커 스레드에서 쓰면 루프 불일치로 조용히 실패할 수 있다.
- **preview_image 경로 노출 주의.** 대시보드가 접근 가능한 경로/URL이어야 표시된다. 필요하면 `UPLOAD_DIR`를 정적 제공(static mount)하거나 기존 `/video_feed` 패턴 참고.
- **범위 엄수.** tar·실제학습·CAD·MCP는 6A에 없다. "움직이는 걸 본다" 하나만 끝까지.
