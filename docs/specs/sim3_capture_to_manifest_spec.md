# ARIA SIM-3 명세서 — 캡처 카메라 + 프레임 캡처 → 기존 manifest 내보내기 (for Antigravity)

> 3D 시뮬레이션 트랙의 **payoff 슬라이스.** 3D 씬이 비로소 *학습 데이터*가 된다.
> 흐름: `sampleSceneParams()`×N + 카메라 랜덤화 → 캔버스 캡처 → **6A `manifest`로 내보내기** → 학습 파이프라인에 그대로 투입.

## 0. 두 가지 결정적 사실

1. **캡처하려면 `<Canvas gl={{ preserveDrawingBuffer: true }}>` 필수.** 없으면 `gl.domElement.toDataURL()`이 빈 이미지를 반환한다.
2. **manifest 포맷은 6A와 동일해야 한다** — `{n_images, classes, images, work_dir}`. 그래야 기존 `run_dummy_training`(6A)이 그대로 소비한다.

## 1. 범위 (Scope)

**포함:**
- `sampleCameraParams()` (SIM-2에서 미룬 **카메라 각도 랜덤화** — 캡처 전용)
- `preserveDrawingBuffer:true` + GL 브리지(gl·camera 노출)
- 캡처 루프: N회 (씬+카메라 랜덤화 → 렌더 → `toDataURL`) + 진행률 UI + "데이터셋 생성" 버튼
- `uploadSimDataset()` + 백엔드 `POST /api/sim/dataset`: base64 PNG 저장 + **6A 포맷 manifest.json 작성**

**제외(다음):**
- 결함 합성(SIM-4) — 지금은 전부 단일 클래스 `"synthetic"`(정상)으로 저장.
- 고정밀 오프라인 렌더, 고정 해상도 보장, 자동 학습 기동(아래 7번 선택사항).

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `frontend/src/sim/randomization.js` | `sampleCameraParams()` 추가 |
| `frontend/src/components/SimulationView.jsx` | `preserveDrawingBuffer` + GLBridge + 캡처 루프 + 진행률/버튼 |
| `frontend/src/api/apiClient.js` | `uploadSimDataset(images, label)` → POST /api/sim/dataset |
| `sim/dataset.py` (신규) | `save_sim_dataset()` — base64 저장 + 6A 포맷 manifest 작성 (단위 테스트 가능) |
| `app.py` | `POST /api/sim/dataset` → `save_sim_dataset` |

## 3. 작업 명세 (What)

### 3-A. `randomization.js` — 카메라 랜덤화 (캡처 전용)
```javascript
export function sampleCameraParams() {
  return {
    az: Math.random() * Math.PI * 2,        // 방위각
    el: 0.30 + Math.random() * 0.90,         // 고도(라디안)
    dist: 3.5 + Math.random() * 2.5,         // 거리
  }
}
```

### 3-B. `SimulationView.jsx` — 캡처
**Canvas**: `preserveDrawingBuffer` 추가 + GLBridge + controls ref:
```jsx
import { useRef } from 'react'
import { useThree } from '@react-three/fiber'
import { sampleSceneParams, sampleCameraParams } from '../sim/randomization'
import { uploadSimDataset } from '../api/apiClient'

function GLBridge({ glRef }) {
  const { gl, camera } = useThree()
  useEffect(() => { glRef.current = { gl, camera } }, [gl, camera])
  return null
}
// Canvas: <Canvas gl={{ preserveDrawingBuffer: true }} ...>
//   <GLBridge glRef={glRef} />
//   <OrbitControls ref={controlsRef} makeDefault ... />
```
**캡처 루프** (SimulationView 내부):
```jsx
const glRef = useRef(null), controlsRef = useRef(null)
const [capturing, setCapturing] = useState(false)
const [progress, setProgress] = useState(0)
const raf = () => new Promise(r => requestAnimationFrame(r))

async function captureDataset(n = 24) {
  if (!glRef.current) return
  setCapturing(true); setProgress(0)
  if (controlsRef.current) controlsRef.current.enabled = false   // 캡처 중 사용자 회전 차단
  const { gl, camera } = glRef.current
  const shots = []
  for (let i = 0; i < n; i++) {
    setParams(sampleSceneParams())               // 부품/조명 변주
    const c = sampleCameraParams()                // 카메라 변주
    camera.position.set(
      c.dist * Math.cos(c.el) * Math.cos(c.az),
      c.dist * Math.sin(c.el),
      c.dist * Math.cos(c.el) * Math.sin(c.az))
    camera.lookAt(0, 0.8, 0)
    await raf(); await raf()                      // R3F 재렌더 대기(2프레임)
    shots.push(gl.domElement.toDataURL('image/png'))
    setProgress(i + 1)
  }
  if (controlsRef.current) controlsRef.current.enabled = true
  setCapturing(false)
  const res = await uploadSimDataset(shots)       // 백엔드로
  alert(`${res.n_images}장 생성 → manifest 작성 (${res.run_id})`)  // 또는 토스트
}
```
**컨트롤 패널에 버튼/진행률** 추가:
```jsx
<button disabled={capturing} onClick={() => captureDataset(24)}>
  {capturing ? `캡처 ${progress}/24` : '데이터셋 생성 (24장)'}
</button>
```

### 3-C. `apiClient.js`
```javascript
export async function uploadSimDataset(images, label = 'synthetic') {
  const { data } = await api.post('/api/sim/dataset', { images, label })
  return data   // { run_id, n_images, classes, work_dir }
}
```

### 3-D. `sim/dataset.py` (신규) — 저장 + **6A 포맷** manifest (단위 테스트 가능)
```python
import base64, json
from pathlib import Path

def save_sim_dataset(images_b64: list, work_dir: str, label: str = "synthetic") -> dict:
    out = Path(work_dir) / label
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, data in enumerate(images_b64):
        b64 = data.split(",", 1)[-1]          # 'data:image/png;base64,...' 접두 제거
        p = out / f"{i:04d}.png"
        p.write_bytes(base64.b64decode(b64))
        paths.append(str(p))
    manifest = {                              # ★ 6A 포맷과 동일 → 학습이 그대로 소비
        "n_images": len(paths),
        "classes": {label: len(paths)},
        "images": paths[:200],
        "work_dir": str(Path(work_dir)),
        "source": "sim",
    }
    with open(Path(work_dir) / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest
```

### 3-E. `app.py` — 엔드포인트
```python
from fastapi import Body
@app.post("/api/sim/dataset")
async def sim_dataset(payload: dict = Body(...)):
    import time
    from sim.dataset import save_sim_dataset
    run_id = f"sim_{int(time.time())}"
    work = UPLOAD_DIR / run_id
    m = save_sim_dataset(payload.get("images", []), str(work), payload.get("label", "synthetic"))
    return {"run_id": run_id, "n_images": m["n_images"], "classes": m["classes"], "work_dir": m["work_dir"]}
```

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "sampleCameraParams" frontend/src/sim/randomization.js
grep -n "preserveDrawingBuffer\|toDataURL\|GLBridge\|captureDataset" frontend/src/components/SimulationView.jsx
grep -n "uploadSimDataset\|/api/sim/dataset" frontend/src/api/apiClient.js
grep -n "def save_sim_dataset\|manifest.json\|n_images" sim/dataset.py
grep -n "/api/sim/dataset\|save_sim_dataset" app.py
```

### 4-2. Headless smoke (내가 실행)
- **node:** `sampleCameraParams()` → `az∈[0,2π]`, `el∈[0.3,1.2]`, `dist∈[3.5,6]`.
- **python:** 1×1 PNG base64 1장을 `save_sim_dataset([...], work, "synthetic")` → `manifest["n_images"]==1`, `classes=={"synthetic":1}`, `work/synthetic/0000.png` 존재, `manifest.json`이 6A 키(`n_images/classes/images/work_dir`)를 가짐.

### 4-3. 회귀 가드
```
grep -c "frontend/dist/index.html" app.py            # 서빙 일원화
grep -c "Canvas" frontend/src/components/SimulationView.jsx  # SIM-1/2 씬
grep -c "sampleSceneParams" frontend/src/components/SimulationView.jsx  # SIM-2 랜덤화
grep -c "/api/train/upload" app.py                    # 6A
grep -c "get_snapshot" app.py                         # HW-1
```

### 4-4. 빌드 + 런타임 (Antigravity — payoff 증명)
- `npm run build` 에러 없음.
- 시뮬레이션 뷰에서 **"데이터셋 생성(24장)"** → 진행률 0→24 → `alert`/토스트로 `24장 생성 → manifest 작성 (sim_…)`.
- 서버에서 `uploads/sim_<ts>/manifest.json` 확인 → `n_images:24`. **이 manifest를 기존 학습이 그대로 읽을 수 있음**(6A 포맷).
- 캡처 이미지들이 **서로 다른 각도/조명/자세**인지(랜덤화 효과). Antigravity 녹화/스샷 첨부.

## 5. 검증 절차 (내가 수행)
"푸시 완료" → 재clone → 4-1 grep, 4-2 node+python smoke, 4-3 회귀. 4-4는 Antigravity 캡처/서버 manifest로. 통과 시 **SIM-4(결함 합성 — 정상/결함 라벨)** 또는 "합성 데이터로 실제 학습 1회"로.

## 6. 커밋
- 브랜치: `feat/sim3-capture-to-manifest`
- 메시지(예): `feat(sim): capture randomized frames to dataset + 6A-format manifest (POST /api/sim/dataset)`

## 7. 주의
- **`preserveDrawingBuffer:true` 빠뜨리면 빈 PNG** — 1순위.
- **manifest 포맷은 6A와 동일 유지** — 학습 연결의 핵심. 키를 바꾸지 말 것.
- 캡처 중 **OrbitControls 비활성화**(camera 직접 구동) → 끝나면 복구.
- 단일 클래스 `"synthetic"`만 — 정상/결함 구분은 SIM-4.
- 24장 base64는 수 MB JSON — 정상. 매우 큰 N(수백 장)은 후속에서 배치/스트리밍으로.
- (선택) payoff를 더 보이려면 `/api/sim/dataset`가 6A의 `run_dummy_training`을 바로 기동하게 할 수 있으나, **범위 유지 위해 기본은 데이터셋 생성까지만.**
