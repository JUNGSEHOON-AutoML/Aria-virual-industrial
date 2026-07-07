# ARIA SIM-4 명세서 — 결함 합성 (정상/결함 라벨) for Antigravity

> 3D 시뮬레이션 트랙 4단계. 합성데이터를 **정상(good)/결함(defect)** 으로 라벨링한다.
> **왜 중요한가:** 맨 처음 비평의 치명적 공백 — *임계값을 GOOD-only(mean+3σ)로만 잡고 **NG 검증이 없어 오검출(escape)률을 모른다***. 합성 결함이 바로 그 **NG 검증 데이터**가 된다. 원점의 문제를 닫는다.

## 0. 핵심 설계 — 결함 합성은 "seam"이다

`synth_defect(img, defect_type)`를 **교체 가능한 seam**으로 둔다. 지금은 절차적(procedural) 결함 1종,
나중에 diffusion(DefectFill/AnomalyDiffusion)으로 *같은 자리만* 교체. 백엔드(PIL)에서 수행 — 3D 씬 불변, 헤드리스 테스트 가능.

## 1. 범위 (Scope)

**포함:**
- `sim/defects.py` 신규: `synth_defect()` seam — 결함 타입 **1종("scratch")** + blob 폴백.
- `save_sim_dataset`를 **good/ + defect/ 2클래스**로 확장(`defect_ratio`로 비율 제어), manifest `classes={good, defect}`.
- `app.py`/`apiClient`/`SimulationView`가 `defect_ratio` 전달 + 결과 good/defect 개수 표시.

**제외(다음):**
- 다양한/사실적 결함 타입, **diffusion 기반 합성**(seam 교체로 후속), 결함 마스크(segmentation 라벨).
- 합성 데이터로 **실제 임계값 검증 실행**("NG 검증" 슬라이스) — SIM-4가 데이터를 만들고, 검증 실행은 별도.

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `sim/defects.py` (신규) | `synth_defect(img, defect_type="scratch")` seam |
| `sim/dataset.py` | `save_sim_dataset(..., defect_ratio, defect_type)` → good/defect 분리 + manifest 2클래스 |
| `app.py` | `/api/sim/dataset`가 `defect_ratio` 수용 |
| `frontend/src/api/apiClient.js` | `uploadSimDataset(images, defectRatio)` |
| `frontend/src/components/SimulationView.jsx` | 결과에 good/defect 개수 표시 (+선택: 결함 비율 입력) |

## 3. 작업 명세 (What)

### 3-A. `sim/defects.py` (신규) — 결함 합성 seam
```python
import random
from PIL import Image, ImageDraw

def synth_defect(img: "Image.Image", defect_type: str = "scratch", seed=None) -> "Image.Image":
    """정상 이미지에 합성 결함 주입 → 결함 이미지. (seam: 추후 diffusion으로 교체)"""
    rng = random.Random(seed)
    out = img.convert("RGB").copy()
    d = ImageDraw.Draw(out)
    w, h = out.size
    if defect_type == "scratch":
        for _ in range(rng.randint(1, 3)):
            x1, y1 = rng.randint(0, w), rng.randint(0, h)
            x2, y2 = x1 + rng.randint(-w // 3, w // 3), y1 + rng.randint(-h // 3, h // 3)
            d.line([(x1, y1), (x2, y2)], fill=(18, 18, 18), width=rng.randint(1, 3))
    else:  # blob 폴백
        cx, cy = rng.randint(0, w), rng.randint(0, h)
        r = rng.randint(max(2, min(w, h) // 12), max(3, min(w, h) // 6))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(30, 25, 25))
    return out
```

### 3-B. `sim/dataset.py` — good/defect 분리 (시그니처 변경)
```python
import base64, io, json, random
from pathlib import Path
from sim.defects import synth_defect

def save_sim_dataset(images_b64: list, work_dir: str,
                     defect_ratio: float = 0.3, defect_type: str = "scratch") -> dict:
    base = Path(work_dir)
    good_dir, def_dir = base / "good", base / "defect"
    good_dir.mkdir(parents=True, exist_ok=True)
    def_dir.mkdir(parents=True, exist_ok=True)
    good_paths, def_paths = [], []
    for i, data in enumerate(images_b64):
        raw = base64.b64decode(data.split(",", 1)[-1])
        gp = good_dir / f"{i:04d}.png"; gp.write_bytes(raw); good_paths.append(str(gp))
        if random.random() < defect_ratio:                 # 일부를 결함 버전으로 합성
            img = Image.open(io.BytesIO(raw))
            dp = def_dir / f"{i:04d}.png"
            synth_defect(img, defect_type).save(dp)
            def_paths.append(str(dp))
    all_paths = good_paths + def_paths
    manifest = {                                            # 6A 포맷 유지, classes만 2개로
        "n_images": len(all_paths),
        "classes": {"good": len(good_paths), "defect": len(def_paths)},
        "images": all_paths[:200],
        "work_dir": str(base),
        "source": "sim",
    }
    with open(base / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest
```
> `from PIL import Image`도 상단에 추가. **good = 학습용, defect = NG 검증용** — PatchCore식(정상으로 학습→이상 검증)에 그대로 맞다.

### 3-C. `app.py` — defect_ratio 수용
```python
m = save_sim_dataset(payload.get("images", []), str(work),
                     defect_ratio=float(payload.get("defect_ratio", 0.3)))
return {"run_id": run_id, "n_images": m["n_images"], "classes": m["classes"], "work_dir": m["work_dir"]}
```

### 3-D. `apiClient.js`
```javascript
export async function uploadSimDataset(images, defectRatio = 0.3) {
  const { data } = await api.post('/api/sim/dataset', { images, defect_ratio: defectRatio })
  return data   // { run_id, n_images, classes: {good, defect}, work_dir }
}
```

### 3-E. `SimulationView.jsx` — 결과 표시
캡처 후 결과 alert/토스트를 클래스별로:
```jsx
const res = await uploadSimDataset(shots, 0.3)
alert(`생성 완료 — good ${res.classes.good} / defect ${res.classes.defect} (${res.run_id})`)
```
(선택) 컨트롤 패널에 결함 비율 입력(0~1)을 두고 `uploadSimDataset(shots, ratio)`.

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "def synth_defect" sim/defects.py
grep -n "good\|defect\|defect_ratio\|synth_defect" sim/dataset.py
grep -n "defect_ratio" app.py
grep -n "defect_ratio\|defectRatio" frontend/src/api/apiClient.js
grep -n "classes.good\|classes.defect\|defect" frontend/src/components/SimulationView.jsx
```

### 4-2. Headless smoke (내가 실행 — python)
- `synth_defect(plain_img)`가 **입력과 다른** 이미지 반환(픽셀 diff > 0).
- `save_sim_dataset([img×4], work, defect_ratio=1.0)` → `classes=={"good":4,"defect":4}`, `good/`·`defect/` 디렉토리 + `manifest.json` 존재, defect 이미지 ≠ good 이미지.
- `defect_ratio=0.0` → `classes.defect==0`.

### 4-3. 회귀 가드
```
grep -c "frontend/dist/index.html" app.py            # 서빙 일원화
grep -c "/api/sim/dataset" app.py                     # SIM-3 엔드포인트 유지
grep -c "captureDataset\|toDataURL" frontend/src/components/SimulationView.jsx  # SIM-3 캡처 유지
grep -c "/api/train/upload" app.py                    # 6A
grep -c "get_snapshot" app.py                         # HW-1
python -m py_compile sim/defects.py sim/dataset.py app.py
```

### 4-4. 빌드 + 런타임 (Antigravity)
- `npm run build` 에러 없음.
- "데이터셋 생성(24장)" → 결과에 **good N / defect M** 표시.
- 서버 `uploads/sim_<ts>/`에 `good/`·`defect/` + `manifest.json`(classes 2개) → **기존 학습이 good으로 학습, defect로 검증 가능**.
- defect 이미지에 **합성 스크래치가 보이는지**. Antigravity 녹화/스샷.

## 5. 검증 절차 (내가 수행)
"푸시 완료" → 재clone → 4-1 grep, 4-2 python smoke(결함 주입·2클래스 manifest), 4-3 회귀. 4-4는 Antigravity. 통과 시 — **"NG 검증 실행"**(이 defect 데이터로 임계값의 오검출률 측정 = 원점 비평 완전 종결) 또는 다양한 결함 타입/ diffusion seam 교체.

## 6. 커밋
- 브랜치: `feat/sim4-defect-synthesis`
- 메시지(예): `feat(sim): synthetic defect injection seam → good/defect labeled dataset (NG validation data)`

## 7. 주의
- **`synth_defect`는 seam** — 절차적 1종으로 시작, diffusion은 같은 함수 교체로 후속. 지금 다종/사실성에 욕심내지 말 것.
- `save_sim_dataset` **시그니처 변경**(`label` → `defect_ratio`/`defect_type`) — `app.py` 호출부도 함께 수정(누락 시 500).
- manifest는 여전히 **6A 포맷**(classes dict만 2개로). 키 구조 바꾸지 말 것.
- defect = good 베이스 + 합성 이상. good(학습)·defect(NG 검증) 분리가 핵심 가치.
- 범위 엄수: **검증 실행**(임계값 평가)은 SIM-4 아님 — 데이터 생성까지만.
