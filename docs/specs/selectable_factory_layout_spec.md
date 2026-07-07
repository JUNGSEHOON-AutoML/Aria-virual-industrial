# ARIA 명세서 — 선택형 공장 레이아웃 + 데이터셋 디렉토리 연결 for Antigravity

> 목표: 하드코딩된 3클래스/고정 경로를 걷어내고 — **사용자가 MVTec 디렉토리를 지정 → 클래스를 골라 → 고른 수만큼 라인이 생기는** 동적 공장. "내가 선택하는 레이아웃" + 디렉토리 연결을 함께 해결.
> 핫픽스로 뱅크 빌드가 풀린 위에서 동작. 기존 `/api/class/train·validate` 재사용.

## 1. 범위 (Scope)

**포함:** `GET /api/mvtec/scan`(루트 스캔 → 유효 클래스 목록); 프론트 — 루트 입력 + 스캔 + 클래스 다중 선택; FactoryLine이 **선택 클래스 수만큼 라인 동적 생성**; "클래스별 가동"이 선택 클래스 순회.
**제외:** 디렉토리 파일 브라우저 GUI(경로 입력으로 충분), 클래스별 개별 기준(criteria), 합성뷰 증강(B2).

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `app.py` | `GET /api/mvtec/scan` |
| `frontend/src/api/apiClient.js` | `mvtecScan` |
| `frontend/src/components/SimulationView.jsx` | 루트 입력·스캔·클래스 선택 + 동적 전달 |
| `frontend/src/sim/factory.jsx` | FactoryLine이 classes 배열로 라인 동적 생성 |

## 3. 작업 명세 (What)

### 3-A. 백엔드 — 디렉토리 스캔
```python
@app.get("/api/mvtec/scan")
async def mvtec_scan(root: str):
    from pathlib import Path
    base = Path(root)
    if not base.is_dir():
        return {"ok": False, "error": f"디렉토리 없음: {root}"}
    classes = []
    for d in sorted(base.iterdir()):                       # 유효 클래스 = train/good + test 가진 하위폴더
        if d.is_dir() and (d / "train" / "good").is_dir() and (d / "test").is_dir():
            classes.append(d.name)
    return {"ok": True, "root": str(base), "classes": classes}
```

### 3-B. apiClient
```js
export async function mvtecScan(root) {
  return get(`/api/mvtec/scan?root=${encodeURIComponent(root)}`)
}
```

### 3-C. SimulationView — 경로·스캔·선택
```jsx
const [mvtecRoot, setMvtecRoot] = useState('/userHome/userhome4/sehoon/datasets/mvtec') // 기본(편집 가능)
const [availableClasses, setAvailableClasses] = useState([])
const [selectedClasses, setSelectedClasses]   = useState([])

async function scanRoot() {
  const r = await mvtecScan(mvtecRoot)
  if (r?.ok) { setAvailableClasses(r.classes); setSelectedClasses(r.classes.slice(0, 3)) }   // 기본 앞 3개 선택
  else alert(r?.error || '스캔 실패')
}
function toggleClass(cid) {
  setSelectedClasses(prev => prev.includes(cid) ? prev.filter(c => c !== cid) : [...prev, cid])
}
// "클래스별 가동"은 selectedClasses 순회 (하드코딩 MVTEC_CLASSES 대신)
async function runAllClasses() {
  for (const cid of selectedClasses) {
    const path = `${mvtecRoot}/${cid}`
    const t = await classTrain(cid, path); if (!t?.ok) continue
    await waitTrainingDone().catch(()=>{})
    await classValidate(cid, path)
  }
}
// FactoryLine에 선택 클래스 전달
<FactoryLine classes={selectedClasses} classResults={classResults} looping={looping} cycle={cycle} validation={validation} trainState={trainState} />
```
UI(컨트롤 패널):
```jsx
<div style={{ display:'flex', gap:6, alignItems:'center', fontSize:12 }}>
  <input value={mvtecRoot} onChange={e=>setMvtecRoot(e.target.value)}
    placeholder="MVTec 루트 경로" style={{ flex:1, padding:'4px 8px', background:'#11141a', color:'#cbd5e1', border:'1px solid #2a2f3a', borderRadius:6 }} />
  <button onClick={scanRoot} style={{ padding:'4px 10px' }}>스캔</button>
</div>
{availableClasses.length > 0 && (
  <div style={{ display:'flex', flexWrap:'wrap', gap:6, marginTop:6 }}>
    {availableClasses.map(c => (
      <button key={c} onClick={()=>toggleClass(c)} style={{
        padding:'3px 9px', borderRadius:12, fontSize:11, cursor:'pointer',
        border:`1px solid ${selectedClasses.includes(c)?'#1FB8CD':'#3a4150'}`,
        background: selectedClasses.includes(c)?'rgba(31,184,205,0.18)':'transparent',
        color: selectedClasses.includes(c)?'#1FB8CD':'#8b94a3' }}>{c}</button>
    ))}
  </div>
)}
```

### 3-D. factory.jsx — 동적 라인
```jsx
import { MVTEC_CLASSES } from './...'  // 기본 폴백용(기존 export 유지)
export default function FactoryLine({ classes = [], classResults = {}, looping, cycle, validation, trainState }) {
  const lines = (classes && classes.length) ? classes : MVTEC_CLASSES   // 선택 없으면 기본
  const baseZ = 3, gap = 2.0
  return (
    <group>
      {lines.map((cid, i) => (
        <ProductionLine key={cid} z={baseZ + i * gap} classId={cid}
          result={classResults[cid]} cap={10}
          ngProb={classResults[cid]?.escape_rate ?? 0.12} />
      ))}
      <Workers /> <Equipment />
      <StatusBoard cycle={cycle} validation={validation} looping={looping} />
      <LearningCore trainState={trainState} />
    </group>
  )
}
```
> 라인 수 = 선택 클래스 수(동적). z 간격으로 평행 배치. (기존 고정 3라인 블록은 이 map으로 대체.)

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "api/mvtec/scan\|def mvtec_scan" app.py
grep -n "mvtecScan" frontend/src/api/apiClient.js
grep -n "mvtecRoot\|availableClasses\|selectedClasses\|scanRoot\|toggleClass" frontend/src/components/SimulationView.jsx
grep -n "classes.map\|lines.map\|classes = \[\]" frontend/src/sim/factory.jsx
grep -c "selectedClasses" frontend/src/components/SimulationView.jsx        # runAllClasses가 선택 클래스 순회
```

### 4-2. Headless smoke (내가 실행 — 스캔 로직)
- 임시 디렉토리에 `root/bottle/train/good/`·`root/bottle/test/` + `root/junk/`(불완전) 생성 → mvtec_scan 로직이 **bottle만** 반환하고 junk 제외하는지.

### 4-3. 회귀 + 구문
```
grep -c "api/class/train\|api/class/validate" app.py        # 클래스 파이프라인 보존
grep -c "factoryGroupRef\|GLBridge\|loopRef" frontend/src/components/SimulationView.jsx  # 캡처·루프 보존
python -m py_compile app.py
```

### 4-4. 런타임 (당신)
- 루트 경로 입력 → **"스캔"** → 디렉토리의 유효 클래스(예: bottle, cable, capsule…)가 칩으로 뜸.
- 클래스 **골라** → 라인이 *고른 수만큼* 생김(동적 레이아웃).
- **"클래스별 가동"** → 선택 클래스만 학습/판정 → 각 라인 escape·PASS/FAIL.

## 5. 검증 (내가 수행)
재clone → 4-1 grep, 4-2 스캔 smoke(유효 클래스만 반환), 4-3 회귀+py_compile. 실제 디렉토리·렌더는 당신 런타임.

## 6. 커밋
- main 직접. 메시지: `feat(layout): selectable factory layout — scan MVTec dir + pick classes → dynamic lines`

## 7. 주의
- 동적 라인 — z 간격 배치, **선택 6개 넘기면 성능/카메라 프레이밍 주의**(cap·라인수 합리적으로).
- 선택 없을 때 **기본 폴백**(MVTEC_CLASSES) — 빈 공장 방지.
- 모든 라인 여전히 `<FactoryLine>` 그룹 안 → 캡처 가드 그대로.
- `mvtecRoot` 기본값은 당신 실제 경로로 — 또는 입력해서 스캔.
- 클래스 경로 규약 = `{root}/{classId}`에 `train/good`·`test/` (MVTec 표준). 다르면 스캔이 걸러냄.
- main 단일 라인 유지.
