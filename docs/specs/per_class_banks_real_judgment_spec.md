# ARIA 명세서 — 가상 산업현장 Slice B: 라인별 클래스 학습 + 진짜 이상판정 for Antigravity

> 목표: 각 라인이 자기 MVTec 클래스의 **메모리뱅크를 학습**하고, 그 클래스의 **test셋(진짜 NG 라벨)으로 escape율을 판정**한다. 라인 OK/NG가 *그 클래스의 실제 결과*로 움직인다.
> 논문의 **클래스 조건부 메모리** 구현 + **원점 비평을 진짜 NG로 종결**. 기존 `build_bank`·`cosine_score`·`run_validation` 재사용.

## 0. 핵심 — 기존 자산이 그대로 맞물림

- `feature_bank.build_bank(paths)` / `cosine_score(img,bank)`는 **클래스 무관** → `classId`만 얹으면 클래스별 뱅크.
- MVTec test 구조가 `_label_of`와 일치: `test/good/*`→정상, `test/{defect}/*`→이상 → **진짜 NG escape율**.
- 클래스별 뱅크는 `banks/{classId}.npy`.

## 1. 범위 (Scope)

**포함:** `POST /api/class/train`(클래스 train/good → `banks/{classId}.npy`), `POST /api/class/validate`(클래스 test → 진짜 escape/fp/FAT), 클래스별 결과 WS broadcast; 프론트 — 클래스별 결과 상태 + 라인 바인딩(ngProb=실제 escape, 라벨에 escape/FAT) + "클래스별 가동" 트리거.
**제외(B2):** factoryLoop가 클래스들을 자동 순회, 픽셀 히트맵, 도메인 랜덤화 합성뷰 증강 — 후속.

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `app.py` | `/api/class/train` · `/api/class/validate` + 클래스 결과 broadcast |
| `frontend/src/apiClient.js` | `classTrain`·`classValidate` |
| `frontend/src/components/SimulationView.jsx` | classResults 상태(WS) + 라인 바인딩 + 가동 트리거 |
| `frontend/src/sim/factory.jsx` | ProductionLine이 클래스 결과로 ngProb·라벨 |

## 3. 작업 명세 (What)

### 3-A. 백엔드 — 클래스별 학습/검증 (app.py)
```python
import numpy as np, threading, asyncio
from pathlib import Path
from scorer.feature_bank import build_bank, cosine_score
from validation.validate import run_validation
BANKS_DIR = BASE_DIR / "banks"; BANKS_DIR.mkdir(exist_ok=True)
IMG_EXT = (".png", ".jpg", ".jpeg", ".bmp")

@app.post("/api/class/train")
async def class_train(payload: dict = Body(...)):
    cid = payload.get("classId"); root = Path(payload.get("mvtec_path", ""))
    good_dir = root / "train" / "good"
    goods = sorted(str(p) for p in good_dir.glob("*") if p.suffix.lower() in IMG_EXT)
    if not cid or not goods:
        return {"ok": False, "error": f"good 이미지 없음: {good_dir}"}
    loop = asyncio.get_running_loop()
    def emit(state, detail):
        asyncio.run_coroutine_threadsafe(manager.broadcast(
            {"type": "agent_status", "agent": cid.upper(), "state": state, "detail": detail}), loop)
    def worker():
        try:
            emit("running", f"{len(goods)} good 학습")
            bank = build_bank(goods, run_id=cid)                 # 진짜 FM 특징(클래스 무관 함수 재사용)
            np.save(str(BANKS_DIR / f"{cid}.npy"), bank)
            emit("done", f"bank {bank.shape[0]} 패치")
        except Exception as e:
            emit("idle", f"실패: {e}")
    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True, "classId": cid, "n_good": len(goods)}

@app.post("/api/class/validate")
async def class_validate(payload: dict = Body(...)):
    cid = payload.get("classId"); root = Path(payload.get("mvtec_path", ""))
    bank_path = BANKS_DIR / f"{cid}.npy"
    if not bank_path.exists():
        return {"ok": False, "error": f"bank 없음 — 먼저 학습: {cid}"}
    test_imgs = [str(p) for p in (root / "test").rglob("*") if p.suffix.lower() in IMG_EXT]
    if not test_imgs:
        return {"ok": False, "error": f"test 이미지 없음: {root/'test'}"}
    bank = np.load(bank_path)
    manifest = {"images": test_imgs, "work_dir": str(BANKS_DIR)}
    result = run_validation(manifest, score_fn=lambda p: cosine_score(p, bank),
                            criteria=payload.get("criteria"))      # _label_of: test/good=정상, 그 외=이상(진짜 NG)
    result["classId"] = cid
    await manager.broadcast({"type": "class_result", "classId": cid,
        "escape_rate": result.get("escape_rate"), "fp_rate": result.get("fp_rate"),
        "fat_verdict": result.get("fat_verdict"), "threshold": result.get("threshold")})
    return result
```
> `run_validation`의 `_label_of`가 MVTec test 폴더명을 그대로 정상/이상으로 매핑 → **진짜 NG escape율**.

### 3-B. apiClient
```js
export async function classTrain(classId, mvtec_path)    { return post('/api/class/train',    { classId, mvtec_path }) }
export async function classValidate(classId, mvtec_path) { return post('/api/class/validate', { classId, mvtec_path }) }
```

### 3-C. SimulationView — 클래스 결과 상태 + 가동
```jsx
// 서버상의 MVTec 루트(설정형). 클래스 경로 = `${MVTEC_ROOT}/${classId}`
const MVTEC_ROOT = '/userHome/userhome4/sehoon/datasets/mvtec'   // ← 실제 경로로
const [classResults, setClassResults] = useState({})            // { bottle:{escape_rate,fp_rate,fat_verdict}, ... }

// WS onmessage:
if (d.type === 'class_result') setClassResults(prev => ({ ...prev, [d.classId]: d }))

// 트리거: 클래스별로 학습→검증 순차
async function runAllClasses() {
  for (const cid of MVTEC_CLASSES) {
    const path = `${MVTEC_ROOT}/${cid}`
    const t = await classTrain(cid, path); if (!t?.ok) continue
    await waitTrainingDone().catch(()=>{})        // 기존 하트비트 재사용(학습 done 대기)
    await classValidate(cid, path)                // 결과는 WS class_result로 classResults에 들어옴
  }
}
// 버튼: <button onClick={runAllClasses}>클래스별 가동 (학습+판정)</button>
// FactoryLine에 classResults 전달
<FactoryLine ... classResults={classResults} />
```
> `MVTEC_CLASSES`는 factory.jsx에서 export 중 → import해서 순회.

### 3-D. factory.jsx — 라인이 클래스 결과로
```jsx
export default function FactoryLine({ looping, cycle, validation, trainState, ngProb, classResults = {} }) {
  // ...
  <ProductionLine z={3}   classId={MVTEC_CLASSES[0]} result={classResults[MVTEC_CLASSES[0]]} cap={10} />
  <ProductionLine z={5}   classId={MVTEC_CLASSES[1]} result={classResults[MVTEC_CLASSES[1]]} cap={10} />
  <ProductionLine z={6.5} classId={MVTEC_CLASSES[2]} result={classResults[MVTEC_CLASSES[2]]} cap={10} />
}
function ProductionLine({ z=3, cap=10, classId='', result=null }) {
  // 실제 escape율이 있으면 그걸로 NG 확률, 없으면 기본
  const ngProb = result?.escape_rate != null ? Math.min(0.5, Math.max(0.02, result.escape_rate)) : 0.12
  // ... 라벨에 결과 표시
  <Text ...>{`LINE · ${classId.toUpperCase()}`}</Text>
  {result?.fat_verdict && <Text position={[-5.6,0.7,0]} fontSize={0.22}
     color={result.fat_verdict==='PASS' ? '#34d399':'#f87171'} anchorX="left">
     {`escape ${(result.escape_rate*100||0).toFixed(0)}% · ${result.fat_verdict}`}</Text>}
}
```
> 검증 후 라인 부품 NG 비율이 *그 클래스의 진짜 escape율*을 반영하고, 라인 라벨에 escape·FAT가 뜬다.

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "api/class/train\|api/class/validate\|BANKS_DIR\|banks/" app.py
grep -n "classTrain\|classValidate" frontend/src/apiClient.js
grep -n "classResults\|class_result\|runAllClasses\|MVTEC_ROOT" frontend/src/components/SimulationView.jsx
grep -n "result?.escape_rate\|classResults\[" frontend/src/sim/factory.jsx
```

### 4-2. Headless smoke (내가 실행 — stub, DINO/MVTec 없이)
- `run_validation`을 **stub score_fn + MVTec식 경로**로: `test/good/a.png`(정상), `test/broken/b.png`(이상) → `_label_of`가 정상/이상 정확히 가르고 escape율 계산하는지.
- `build_bank_from_features` + `cosine_score_features` 정상<이상(기존 S1 smoke 재확인).
- (실제 DINO·MVTec는 GPU/데이터 필요 → Antigravity/당신 런타임.)

### 4-3. 회귀 + 구문
```
grep -c "loopRef\|factoryLoop\|build_bank\|bank.npy" app.py frontend/src/components/SimulationView.jsx
python -m py_compile app.py validation/validate.py scorer/feature_bank.py
```

### 4-4. 런타임 (당신/Antigravity — 핵심)
- `MVTEC_ROOT` 실제 경로 설정 → **"클래스별 가동"** → 각 클래스 학습(에이전트 칩 점등) → **진짜 test셋으로 검증** → 라인마다 `escape X% · PASS/FAIL`이 뜨고, 부품 NG 비율이 그 클래스 escape율을 반영.
- `banks/bottle.npy` 등 생성 확인.

## 5. 검증 (내가 수행)
재clone → 4-1 grep, 4-2 smoke(MVTec 라벨 매핑·정상<이상), 4-3 회귀+py_compile. 실제 학습/판정은 GPU·MVTec라 Antigravity.

## 6. 커밋
- `feat/per-class-banks-real-judgment` → main FF. 메시지: `feat(class): per-class memory banks + real NG validation from MVTec (one class per line)`

## 7. 주의
- **진짜 NG로 escape 측정** — MVTec test의 라벨 결함. 이게 비평을 *진짜로* 닫음(합성 아님).
- `MVTEC_ROOT`는 **서버 실제 경로** — 클래스 경로 = `{ROOT}/{classId}`, 각 클래스에 `train/good`·`test/` 있어야.
- 클래스별 뱅크는 한 번 만들면 재사용(`banks/{cid}.npy`) — 매번 재학습 불필요.
- 학습은 2D 이미지 위(MVTec) — 3D는 데이터 생성·오케스트레이션. 정직한 선 유지.
- 무거움: 클래스당 good 수십~수백장 DINO 추출 — 첫 학습 수십 초~분. 하트비트가 커버.
- main 단일 라인 유지.
- B2(후속): factoryLoop가 클래스 자동 순회 + 도메인 랜덤화 합성뷰로 뱅크 증강(논문 coverage).
