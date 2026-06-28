# ARIA 명세서 — ② 라인 클로즈업 + 실제 MVTec 이미지(2D→3D) for Antigravity

> 목표: 자동순환이 클래스를 돌 때, **그 라인으로 카메라가 부드럽게 클로즈업**되고, **실제 MVTec 이미지를 라인 위 패널에 띄우고 컨베이어 부품에 그 이미지를 입힌다.** = "2D 이미지를 3D로 변환해 검사하는 장면."
> ① (버퍼링 수정: factoryLoop=클래스 순회) 위에서 동작.

## 1. 범위 (Scope)

**포함:** 백엔드 클래스 샘플 이미지 제공(+안전 이미지 서버); 프론트 — 활성 라인으로 카메라 클로즈업(부드러운 lerp); 라인 위 이미지 패널 + 활성 라인 부품에 이미지 텍스처.
**제외:** 픽셀 히트맵 오버레이, 부품마다 다른 이미지(한 클래스=대표 1~몇 장), 실시간 추론 애니메이션 디테일.

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `app.py` | `GET /api/class/samples` + `GET /api/image`(안전 서버) |
| `frontend/src/api/apiClient.js` | `classSamples` |
| `frontend/src/components/SimulationView.jsx` | activeClass 상태, 카메라 클로즈업, 샘플 로딩 |
| `frontend/src/sim/factory.jsx` | 라인 이미지 패널 + 부품 텍스처 |

## 3. 작업 명세 (What)

### 3-A. 백엔드 — 샘플 이미지 + 안전 서버
```python
import urllib.parse
@app.get("/api/class/samples")
async def class_samples(classId: str, mvtec_path: str, n: int = 4):
    from pathlib import Path
    test = Path(mvtec_path) / "test"
    if not test.is_dir():
        return {"ok": False, "error": f"test 없음: {test}"}
    # good 몇 장 + defect 몇 장 섞어 대표 샘플
    goods   = sorted((test / "good").glob("*"))[:max(1, n // 2)]
    defects = [p for d in sorted(test.iterdir()) if d.is_dir() and d.name != "good"
                 for p in sorted(d.glob("*"))[:1]][:n - len(goods)]
    paths = [str(p) for p in (goods + defects) if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp")]
    urls = ["/api/image?path=" + urllib.parse.quote(p) for p in paths]
    return {"ok": True, "classId": classId, "samples": urls}

@app.get("/api/image")
async def serve_image(path: str):
    from pathlib import Path
    p = Path(path).resolve()
    # 안전: 데이터/업로드 루트 하위만 허용 (경로 탈출 방지)
    allowed = [BASE_DIR.resolve(), (BASE_DIR / "data").resolve(), UPLOAD_DIR.resolve()]
    if not any(str(p).startswith(str(a)) for a in allowed) or not p.is_file():
        return JSONResponse({"error": "허용되지 않은 경로"}, status_code=403)
    return FileResponse(str(p))
```
> 이미 `FileResponse`·`StaticFiles` 사용 중이라 패턴 동일. 로컬 랩 도구이므로 루트 하위 화이트리스트로 충분.

### 3-B. apiClient
```js
export async function classSamples(classId, mvtec_path) {
  return get(`/api/class/samples?classId=${encodeURIComponent(classId)}&mvtec_path=${encodeURIComponent(mvtec_path)}`)
}
```

### 3-C. SimulationView — activeClass + 카메라 클로즈업
```jsx
const [activeClass, setActiveClass] = useState(null)        // 현재 순회 중 클래스 (①의 setActiveClass가 채움)
const [classSamplesMap, setClassSamplesMap] = useState({})  // { bottle: [url,...] }

// ① factoryLoop 안에서 클래스 시작 시:
setActiveClass(cid)
if (!classSamplesMap[cid]) {
  const s = await classSamples(cid, `${mvtecRoot}/${cid}`)
  if (s?.ok) setClassSamplesMap(prev => ({ ...prev, [cid]: s.samples }))
}

// 활성 라인 z 계산 (factory와 동일 규칙: baseZ=3, gap=2)
const lines = (selectedClasses.length ? selectedClasses : MVTEC_CLASSES)
const activeZ = activeClass ? 3 + lines.indexOf(activeClass) * 2 : null

// Canvas 안에 카메라 포커스 헬퍼 마운트
<CameraFocus targetZ={activeZ} controlsRef={controlsRef} />
// FactoryLine에 활성 클래스·샘플 전달
<FactoryLine classes={selectedClasses} classResults={classResults}
  activeClass={activeClass} samplesMap={classSamplesMap} ... />
```
**CameraFocus (Canvas 내부, useThree/useFrame로 부드럽게 이동):**
```jsx
function CameraFocus({ targetZ, controlsRef }) {
  const { camera } = useThree()
  useFrame(() => {
    if (targetZ == null || !controlsRef.current) return
    const ctrl = controlsRef.current
    // 활성 라인 약간 위/옆에서 바라보기
    const desired = { x: 2.5, y: 2.2, z: targetZ + 2.5 }
    camera.position.lerp(desired, 0.04)                  // 부드러운 접근(와리가리 아님)
    ctrl.target.lerp({ x: 0, y: 0.6, z: targetZ }, 0.06)
    ctrl.update()
  })
  return null
}
```
> 사용자가 드래그하면 OrbitControls가 우선 — lerp는 0.04로 약해 충돌 없이 양보. (강제 락 아님 → 버퍼링 없음.)

### 3-D. factory.jsx — 이미지 패널 + 부품 텍스처
`ProductionLine`이 활성 시 샘플 이미지를 패널/부품에 사용:
```jsx
import { useTexture } from '@react-three/drei'

function LineImagePanel({ url }) {                          // 라인 위 떠 있는 2D 패널
  const tex = useTexture(url)
  return (<mesh position={[-3.5, 1.6, 0]}>
    <planeGeometry args={[1.4, 1.4]} />
    <meshBasicMaterial map={tex} toneMapped={false} />
  </mesh>) }

function ProductionLine({ z=3, classId='', result=null, active=false, sampleUrl=null, cap=10 }) {
  const ngProb = result?.escape_rate != null ? Math.min(0.5, Math.max(0.02, result.escape_rate)) : 0.12
  return (
    <group position={[0, 0, z - 3]}>
      <ConveyorBelt />
      <FactoryParts ngProb={ngProb} onResult={...} cap={cap} textureUrl={active ? sampleUrl : null} />
      <InspectionGantry />
      <ResultBins .../>
      <Text ...>{`LINE · ${classId.toUpperCase()}`}</Text>
      {active && sampleUrl && <Suspense fallback={null}><LineImagePanel url={sampleUrl} /></Suspense>}
    </group>
  )
}
```
**FactoryParts**: `textureUrl`이 있으면 부품 머티리얼에 map 적용(부품이 그 MVTec 이미지를 "운반"):
```jsx
function FactoryParts({ ngProb, onResult, cap = 10, textureUrl = null }) {
  const tex = textureUrl ? useTexture(textureUrl) : null
  // ... 부품 메쉬:
  <meshStandardMaterial map={tex || undefined}
     color={tex ? '#ffffff' : (verdict==='NG'?'#f87171':verdict==='OK'?'#34d399':'#9aa3b2')}
     emissiveIntensity={0.25} />
}
```
**FactoryLine**: 활성 클래스에 sampleUrl 전달:
```jsx
{lines.map((cid, i) => (
  <ProductionLine key={cid} z={3 + i*2} classId={cid} result={classResults[cid]}
    active={cid === activeClass}
    sampleUrl={(samplesMap[cid] && samplesMap[cid][0]) || null} cap={10} />
))}
```

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "api/class/samples\|def class_samples\|api/image\|def serve_image" app.py
grep -n "classSamples" frontend/src/api/apiClient.js
grep -n "activeClass\|classSamplesMap\|CameraFocus\|activeZ" frontend/src/components/SimulationView.jsx
grep -n "LineImagePanel\|useTexture\|textureUrl\|sampleUrl\|active" frontend/src/sim/factory.jsx
```

### 4-2. Headless smoke (내가 실행)
- `class_samples` 로직: good+defect 섞어 n개 URL 반환, 빈/없는 test 처리.
- `serve_image` 화이트리스트: 루트 밖 경로 403, 루트 안 파일 통과(경로 판정만).

### 4-3. 회귀 + 구문
```
grep -c "factoryGroupRef\|loopRef\|api/class/train\|api/class/validate" app.py frontend/src/components/SimulationView.jsx
python -m py_compile app.py
```

### 4-4. 런타임 (당신)
- 자동순환 중 **활성 라인으로 카메라가 부드럽게 클로즈업**(점프·버퍼링 없음), 사용자 드래그 시 양보.
- 활성 라인 **위에 실제 MVTec 이미지 패널**이 뜨고, **그 라인 부품에 이미지가 입혀짐**.
- 클래스가 바뀌면 다음 라인으로 포커스 이동.

## 5. 검증 (내가 수행)
재clone → 4-1 grep, 4-2 smoke(samples 구성·경로 화이트리스트), 4-3 회귀+py_compile. 카메라 lerp·텍스처 렌더는 R3F라 Antigravity 녹화.

## 6. 커밋
- main 직접. 메시지: `feat(sim): per-line close-up + real MVTec image on panel/parts (2D→3D inspection scene)`

## 7. 주의
- **카메라 lerp는 약하게(0.04)** — 강제 락 금지(그게 버퍼링의 원인이었음). 사용자 조작 우선.
- `useTexture`는 Suspense 필요 — 패널/부품 텍스처는 `<Suspense fallback>`로 감싸 로딩 중 깨지지 않게.
- 이미지 서버는 **루트 하위 화이트리스트**(경로 탈출 403). 임의 파일 노출 금지.
- 한 라인 = 대표 이미지 1~몇 장(부품마다 다른 이미지는 후속) — 성능·단순성.
- ① 먼저(버퍼링 수정) → ② (이게 ①의 setActiveClass/클래스순회에 얹힘).
- main 단일 라인 유지.
