# ARIA 명세서 — ① 3x3 검사 결과물 갤러리 + 클릭 360° 검사 스캔 for Antigravity

> 목표: 부품이 분류를 마치면 그 클래스의 **검사 결과물 9개를 3x3 입체 격자**로 띄운다(많이·입체로 보려고). 사용자가 **하나를 클릭하면** 그게 무대 중앙으로 확대되고 **검사 카메라가 360° 회전하며 스캔**(회전 링/빔 연출). 다시 클릭하면 격자로 복귀.
> 거부된 "큐브 면에 사진"(부품 텍스처 + 단일 패널)은 **제거**하고 이 갤러리로 대체.

## 1. 범위 (Scope)

**포함:** `class_samples` 9개+OK/NG 라벨; `<ResultGallery>`(3x3 입체 패널, 클릭); 선택 시 카메라 360° 궤도 + 스캔 링; 갤러리 트리거(클래스 검사 완료 또는 "결과물 보기"); 부품 큐브 텍스처·단일 LineImagePanel 제거.
**제외(후속):** 픽셀 히트맵 셰이더(스캔 링으로 대체), 모델 점수 기반 판정(폴더 라벨로), 환경 밝기/규모(②).

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `app.py` `class_samples` | n=9 기본 + 항목별 OK/NG 라벨 |
| `frontend/src/sim/factory.jsx` | ResultGallery + ScanRig; 부품 텍스처/단일 패널 제거 |
| `frontend/src/components/SimulationView.jsx` | 갤러리 상태·트리거·선택·카메라 궤도 |

## 3. 작업 명세 (What)

### 3-A. 백엔드 — 결과물 9개 + 라벨
```python
@app.get("/api/class/samples")
async def class_samples(classId: str, mvtec_path: str, n: int = 9):
    from pathlib import Path; import urllib.parse
    test = Path(mvtec_path) / "test"
    if not test.is_dir(): return {"ok": False, "error": f"test 없음: {test}"}
    def url(p): return "/api/image?path=" + urllib.parse.quote(str(p))
    items = []
    for p in sorted((test / "good").glob("*"))[:max(1, n // 3)]:
        if p.suffix.lower() in (".png",".jpg",".jpeg",".bmp"): items.append({"url": url(p), "label": "OK"})
    for d in sorted(test.iterdir()):
        if d.is_dir() and d.name != "good":
            for p in sorted(d.glob("*"))[:2]:
                if p.suffix.lower() in (".png",".jpg",".jpeg",".bmp"):
                    items.append({"url": url(p), "label": "NG", "defect": d.name})
                if len(items) >= n: break
        if len(items) >= n: break
    return {"ok": True, "classId": classId, "items": items[:n]}
```
> 라벨은 폴더 기준(good→OK, 결함→NG) = 진짜 검사 대상. (모델 점수 판정은 후속.)

### 3-B. factory.jsx — ResultGallery (3x3 입체) + 클릭
```jsx
import { useTexture, Billboard, Text } from '@react-three/drei'
import { Suspense, useState } from 'react'

function ResultTile({ item, pos, onClick }) {
  const tex = useTexture(item.url)
  const col = item.label === 'NG' ? '#f87171' : '#34d399'
  return (
    <group position={pos} onPointerDown={(e)=>{ e.stopPropagation(); onClick() }}>
      <mesh><boxGeometry args={[0.92,0.92,0.08]} /><meshStandardMaterial color={col} emissive={col} emissiveIntensity={0.25} /></mesh>{/* 입체 테두리 */}
      <mesh position={[0,0,0.05]}><planeGeometry args={[0.8,0.8]} /><meshBasicMaterial map={tex} toneMapped={false} /></mesh>
    </group>
  )
}
// items 9개 → 3x3 격자
function ResultGallery({ items=[], center=[0,2.2,0], onSelect }) {
  const gap = 1.05
  return (<group position={center}>
    {items.slice(0,9).map((it,i) => {
      const r = Math.floor(i/3), c = i%3
      return <Suspense key={i} fallback={null}>
        <ResultTile item={it} pos={[(c-1)*gap, (1-r)*gap, 0]} onClick={()=>onSelect(i)} />
      </Suspense>
    })}
  </group>)
}
```
**ScanRig (선택된 결과물 360° 스캔 연출):** 회전하는 링 + 위아래 쓸어내리는 빔.
```jsx
function ScanRig({ active }) {
  const ring = useRef(), beam = useRef()
  useFrame((s,dt) => { if(!active) return
    if (ring.current) ring.current.rotation.z += dt*2.2
    if (beam.current) beam.current.position.y = Math.sin(s.clock.elapsedTime*2)*0.5
  })
  if (!active) return null
  return (<group>
    <mesh ref={ring} rotation={[Math.PI/2,0,0]}><torusGeometry args={[0.9,0.03,8,48]} /><meshStandardMaterial color="#1FB8CD" emissive="#1FB8CD" emissiveIntensity={1.2} /></mesh>
    <mesh ref={beam}><planeGeometry args={[1.8,0.04]} /><meshBasicMaterial color="#1FB8CD" transparent opacity={0.6} /></mesh>
  </group>)
}
```
**부품 텍스처·단일 패널 제거:** `FactoryParts`의 `textureUrl`/`useTexture`(부품 면 사진)와 `<LineImagePanel>`(라인 위 단일 사진) 호출 삭제 → 부품은 다시 단색 OK/NG.

### 3-C. SimulationView — 갤러리 상태·트리거·카메라 360° 궤도
```jsx
const [galleryItems, setGalleryItems] = useState([])   // 현재 보여줄 9개
const [galleryClass, setGalleryClass] = useState(null)
const [selectedIdx, setSelectedIdx]   = useState(null) // 선택된 결과물

// 클래스 검사 완료 후(루프 또는 버튼): 9개 샘플 로드
async function showResults(cid) {
  const s = await classSamples(cid, `${mvtecRoot}/${cid}`)   // classSamples는 items 반환
  if (s?.ok) { setGalleryItems(s.items); setGalleryClass(cid); setSelectedIdx(null) }
}
// factoryLoop의 classValidate 직후: await showResults(cid)

// 캔버스 안:
<ResultGallery items={galleryItems} center={[0,2.4,0.5]} onSelect={setSelectedIdx} />
{selectedIdx != null && <ScanRig active />}
<CameraOrbit active={selectedIdx != null} target={[0,2.4,0.5]} controlsRef={controlsRef} />
// 빈 곳 클릭 시 선택 해제
<mesh position={[0,0,0]} onPointerMissed={()=>setSelectedIdx(null)} visible={false}><boxGeometry/></mesh>
```
**CameraOrbit (선택 시 360° 회전 검사):**
```jsx
function CameraOrbit({ active, target, controlsRef }) {
  const { camera } = useThree(); const a = useRef(0)
  useFrame((_,dt) => {
    if (!active || !controlsRef.current) return
    a.current += dt*0.7                                   // 360° 천천히 궤도
    const R = 3.2
    camera.position.set(target[0]+Math.cos(a.current)*R, target[1]+1.2, target[2]+Math.sin(a.current)*R)
    controlsRef.current.target.set(...target); controlsRef.current.update()
  })
  return null
}
```
> 선택 해제되면 OrbitControls 사용자 조작 복귀(강제 락 아님).

UI: 활성 클래스 옆 "🔍 결과물 보기" 버튼 → `showResults(cid)`.

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "n: int = 9\|items.append\|\"label\"" app.py
grep -n "ResultGallery\|ResultTile\|ScanRig\|onPointerDown\|CameraOrbit" frontend/src/sim/factory.jsx frontend/src/components/SimulationView.jsx
grep -n "galleryItems\|selectedIdx\|showResults\|onPointerMissed" frontend/src/components/SimulationView.jsx
echo "거부된 큐브텍스처/단일패널 제거:"; grep -c "textureUrl\|LineImagePanel" frontend/src/sim/factory.jsx   # 0
```

### 4-2. Smoke (내가 실행) + 회귀
- `class_samples`: good+defect 섞어 **9개** + 각 OK/NG 라벨, test 없으면 에러.
- 회귀: `grep -c "loopRef\|factoryGroupRef\|api/class/validate" ...`; `python -m py_compile app.py`.

### 4-3. 런타임 (당신)
- 클래스 검사 후(또는 "결과물 보기") → **3x3 입체 결과물 9개**가 뜸(OK 초록/NG 빨강 테두리).
- **하나 클릭** → 카메라가 그 결과물 둘레를 **360° 돌며** 회전 링/빔으로 스캔하는 연출. 빈 곳 클릭 → 복귀.

## 5. 검증 (내가 수행)
재clone → 4-1 grep(갤러리·스캔·궤도·큐브텍스처 제거) + 4-2 smoke(9개+라벨)+회귀+py_compile. 클릭·360 궤도·스캔 렌더는 R3F라 Antigravity 녹화.

## 6. 커밋
- main 직접. 메시지: `feat(sim): 3x3 inspection-result gallery + click-to-360 scan (replaces cube-texture)`

## 7. 주의
- **거부된 "큐브에 사진"(부품 텍스처+단일 패널) 제거** — 갤러리로 대체.
- 클릭 = R3F `onPointerDown`(메쉬 레이캐스트), 해제 = `onPointerMissed`.
- 카메라 360°는 선택 중에만, 해제 시 OrbitControls 복귀(강제 락 금지 — 버퍼링 재발 방지).
- 라벨은 폴더 기준(진짜 검사 대상). 모델 점수 판정·픽셀 히트맵은 후속.
- 갤러리/스캔은 캡처 가드 영향 없음(데이터 캡처와 무관). 단 `<FactoryLine>` 외부에 둘 거면 캡처 시 같이 숨길지 판단(결과물은 캡처 대상 아니므로 숨겨도 무방).
- 다음: ② 환경(밝고 넓고 바쁘게)+좌측 설정.
