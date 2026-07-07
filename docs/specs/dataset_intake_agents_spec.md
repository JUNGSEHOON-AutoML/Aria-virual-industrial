# ARIA 명세서 — 데이터셋 인테이크 에이전트 (SCAN + DOMAIN, zip/tar) for Antigravity

> 자율 가상 공장 파이프라인의 **입구(①+②).** "데이터셋을 넣으면 전문 에이전트들이 받아 스스로 처리하는" 첫 조각.
> 핵심: 두 에이전트(SCAN, DOMAIN)가 **SWARM MONITOR에 단계별로 깜빡이며 가동**되는 게 보인다.

## 0. 흐름

```
zip/tar 업로드 → [SCAN 에이전트] 압축해제·구조/통계 리포트
              → [DOMAIN 에이전트] 샘플 → VLM → "어떤 산업 데이터인가" 판단
              → 결과(통계 + 도메인) 반환
   (두 에이전트는 agent_status를 WS로 흘려 SWARM MONITOR에 실시간 표시)
```

## 1. 범위 (Scope)

**포함:**
- **SCAN 에이전트** — zip **+ tar** 해제, 통계 리포트(이미지 수·클래스/폴더·포맷·해상도 분포).
- **DOMAIN 에이전트** — 샘플 K장 → `get_vlm().analyze()` → 산업 도메인 판단 + 근거. (VLM 다운 시 graceful.)
- `POST /api/dataset/intake` — 위 둘을 순차 실행하며 **`agent_status`(SCAN, DOMAIN) 실시간 emit** + 결과 반환.
- 프론트 최소: 업로드 버튼 + 결과 표시. (SWARM 칩은 자동 — `AgentSwarm`이 미등록 에이전트 자동 추가.)

**제외(다음):**
- ③ 라우팅(도메인→detector 선택), ④ 학습, ⑤ 추론/NG검증, ⑥ 지속 자율 루프 — 다음 슬라이스.
- 도메인 판단 정확도 보장(VLM 최선 추정), 멀티샘플 투표/요약(후속).

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `intake/scan_agent.py` (신규) | `scan_dataset(archive, work_dir)` — zip/tar 해제 + 통계 |
| `intake/domain_agent.py` (신규) | `classify_domain(report, k)` — VLM 도메인 판단 (graceful) |
| `app.py` | `POST /api/dataset/intake` + `agent_status`(SCAN/DOMAIN) emit |
| `frontend/src/api/apiClient.js` | `intakeDataset(file)` |
| `frontend/src/components/Dashboard.jsx` (또는 TrainingControl 영역) | 업로드 버튼 + 결과 표시 |

## 3. 작업 명세 (What)

### 3-A. `intake/scan_agent.py` (신규)
```python
import os, zipfile, tarfile
from pathlib import Path
from PIL import Image

_IMG_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

def _extract(archive_path: str, out: Path):
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as z: z.extractall(out)
    elif tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path) as t:
            t.extractall(out, filter="data")   # path-traversal 방지(py3.12+); 구버전이면 filter 제거
    else:
        raise ValueError("zip/tar 형식이 아님")

def scan_dataset(archive_path: str, work_dir: str) -> dict:
    out = Path(work_dir); out.mkdir(parents=True, exist_ok=True)
    _extract(archive_path, out)
    images, classes, formats, sizes = [], {}, {}, []
    for root, _, files in os.walk(out):
        for fn in files:
            ext = Path(fn).suffix.lower()
            if ext in _IMG_EXT:
                p = os.path.join(root, fn); images.append(p)
                cls = Path(root).name; classes[cls] = classes.get(cls, 0) + 1
                formats[ext] = formats.get(ext, 0) + 1
                try:
                    with Image.open(p) as im: sizes.append(im.size)
                except Exception: pass
    resolution = {}
    if sizes:
        ws = [s[0] for s in sizes]; hs = [s[1] for s in sizes]
        resolution = {"w": [min(ws), max(ws)], "h": [min(hs), max(hs)]}
    return {"n_images": len(images), "classes": classes, "formats": formats,
            "resolution": resolution, "images": images[:200], "work_dir": str(out)}
```

### 3-B. `intake/domain_agent.py` (신규)
```python
from config.vlm import get_vlm

_PROMPT = ("이 이미지는 산업 검사 데이터입니다. 어떤 제품/표면 종류인가요? "
           "(예: 금속표면·PCB·직물·캡슐·카펫 등) 한 단어 카테고리와 한 줄 근거만.")

def classify_domain(report: dict, k: int = 3) -> dict:
    imgs = report.get("images", [])[:k]
    if not imgs:
        return {"domain": "unknown", "rationale": "이미지 없음", "samples": 0}
    vlm = get_vlm()
    notes = []
    for p in imgs:
        try: notes.append(vlm.analyze(p, _PROMPT))
        except Exception as e: notes.append(f"VLM 실패: {e}")
    first = notes[0] if notes else ""
    domain = (first.split()[0][:30] if first and not first.startswith("VLM") else "unknown")
    return {"domain": domain, "rationale": first, "samples": len(imgs)}
```
> VLM(Ollama)이 꺼져 있어도 예외 없이 dict 반환 — 파이프라인이 죽지 않는다.

### 3-C. `app.py` — 엔드포인트 + agent_status emit
```python
@app.post("/api/dataset/intake")
async def dataset_intake(file: UploadFile = File(...)):
    import time, asyncio, threading
    from pathlib import Path
    from intake.scan_agent import scan_dataset
    from intake.domain_agent import classify_domain
    run_id = f"ds_{int(time.time())}"
    arc = UPLOAD_DIR / f"{run_id}{Path(file.filename).suffix or '.zip'}"
    arc.write_bytes(await file.read())
    work = UPLOAD_DIR / run_id
    loop = asyncio.get_running_loop()
    def emit(agent, state, detail=""):
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"type": "agent_status", "agent": agent,
                               "state": state, "detail": detail}), loop)
    result = {}
    def pipeline():
        emit("SCAN", "running", "압축 해제·구조 분석")
        rep = scan_dataset(str(arc), str(work))
        emit("SCAN", "done", f"{rep['n_images']}장 · 클래스 {len(rep['classes'])}")
        emit("DOMAIN", "running", "VLM 도메인 판단")
        dom = classify_domain(rep)
        emit("DOMAIN", "done", dom["domain"])
        result.update(report=rep, domain=dom)
    t = threading.Thread(target=pipeline, daemon=True); t.start(); t.join()
    r = result["report"]
    return {"run_id": run_id, "n_images": r["n_images"], "classes": r["classes"],
            "resolution": r["resolution"], "domain": result["domain"]}
```
> `agent_status`는 기존 SWARM이 쓰는 형식. Dashboard가 이미 `agent_status` → `agents` state로 라우팅하면 그대로 표시됨(미등록 SCAN/DOMAIN은 `AgentSwarm`이 자동 칩 추가, L52). **만약 Dashboard WS 핸들러에 `agent_status` 라우팅이 없으면 추가**: `if(data.type==='agent_status') setAgents(a=>({...a,[data.agent]:{state:data.state,detail:data.detail}}))`.

### 3-D. `apiClient.js`
```javascript
export async function intakeDataset(file) {
  const fd = new FormData(); fd.append('file', file)
  const { data } = await api.post('/api/dataset/intake', fd,
    { headers: { 'Content-Type': 'multipart/form-data' } })
  return data   // { run_id, n_images, classes, resolution, domain }
}
```

### 3-E. 프론트 — 업로드 버튼 + 결과 (TRAINING CONTROL 인근)
```jsx
<label className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-white/[0.08] cursor-pointer whitespace-nowrap w-fit">
  데이터셋 인테이크 (zip/tar)
  <input type="file" accept=".zip,.tar,.tar.gz,.tgz" hidden
         onChange={async e=>{const f=e.target.files?.[0]; if(!f)return;
           const r=await intakeDataset(f);
           alert(`도메인: ${r.domain} · ${r.n_images}장 · 클래스 ${Object.keys(r.classes).length}`)}} />
</label>
```
> 업로드 누르면 **SWARM MONITOR에서 SCAN → DOMAIN이 차례로 깜빡이고**, 끝나면 도메인·통계가 표시된다.

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "def scan_dataset\|tarfile\|zipfile" intake/scan_agent.py
grep -n "def classify_domain\|get_vlm" intake/domain_agent.py
grep -n "/api/dataset/intake\|agent_status\|emit(" app.py
grep -n "intakeDataset" frontend/src/api/apiClient.js
```

### 4-2. Headless smoke (내가 실행 — python)
- **zip + tar 각각** 작은 더미(이미지 N장) → `scan_dataset` → `n_images==N`, `classes` 정확, `resolution` 채워짐.
- `classify_domain`(VLM/Ollama 없는 환경) → 예외 없이 dict(`domain`·`rationale`·`samples`) 반환(파이프라인 graceful).

### 4-3. 회귀 가드
```
grep -c "frontend/dist/index.html" app.py     # 서빙
grep -c "/api/train/upload" app.py             # 6A
grep -c "/api/sim/dataset" app.py              # SIM
grep -c "get_snapshot" app.py                  # HW-1
grep -c "inspect_via_registry" autonomous_agent.py  # 1~4단계
python -m py_compile intake/scan_agent.py intake/domain_agent.py app.py
```

### 4-4. 런타임 (당신/Antigravity — 핵심 손맛)
- 검사 탭에서 **데이터셋 인테이크(zip/tar)** 업로드 → **SWARM MONITOR에 SCAN이 실행→완료, 이어 DOMAIN이 실행→완료**로 깜빡이는지.
- 결과 alert에 **도메인 + 이미지 수 + 클래스 수**. tar도 zip처럼 동작하는지.
- Antigravity 녹화(에이전트가 단계별로 가동되는 모습) 첨부.

## 5. 검증 절차 (내가 수행)
"푸시 완료" → 재clone → 4-1 grep, 4-2 python smoke(zip/tar·VLM graceful), 4-3 회귀. 4-4(SWARM 가동·도메인)는 Antigravity. 통과 시 ③ 라우팅(도메인→detector) 또는 ⑥ 루프 자율화로.

## 6. 커밋
- 브랜치: `feat/dataset-intake-agents`
- 메시지(예): `feat(agents): dataset intake pipeline — SCAN (zip/tar stats) + DOMAIN (VLM) streaming to swarm`

## 7. 주의
- **VLM graceful** 필수 — Ollama 꺼져도 인테이크가 죽지 않게(domain="unknown").
- **tar `extractall`은 신뢰된 데이터셋 전제** — `filter="data"`로 path-traversal 방어(py3.12+). 외부 비신뢰 입력이면 추가 검증 필요.
- `agent_status`는 **기존 SWARM 형식 재사용** — 새 패널 만들지 말 것(자동 칩).
- 범위 엄수: 라우팅·학습·추론·지속 루프는 다음. 지금은 **"넣으면 SCAN·DOMAIN이 가동되어 무엇인지 말해준다"**까지.
