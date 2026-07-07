# ARIA VIS3D-1 명세서 — 이미지 → 3D 입체화 (높이맵 표면) for Antigravity

> 새 능력. **"내가 넣은 검사 이미지를 3D로 입체화."** (지금 SIM은 합성데이터용 *작가 씬* — 별개)
> v1: 이미지 밝기 → 표면 높이(three.js `displacementMap`, ML 불필요). 깊이추정 모델은 **seam으로 후속 교체**.

## 0. 개념 정리 (혼동 방지)

- **기존 SIM(1~4):** 3D 씬(placeholder 큐브) → 도메인 랜덤화 → 캡처 → *합성 학습 데이터*. (3D = 데이터 소스)
- **이것(VIS3D):** 업로드한 *실제 검사 이미지* → 3D 표면으로 입체화. (이미지 = 3D 소스)
  스크래치/찍힘이 **3D 굴곡**으로 보여 검사 가시성↑. 둘은 공존한다(데이터생성 vs 검사가시화).

## 1. 범위 (Scope)

**포함:** 새 탭 **"이미지 3D"** + `ImageTo3D.jsx` — 이미지 업로드 → 세분 평면에 `displacementMap`(밝기→높이) + 텍스처 → OrbitControls + 높이 스케일 슬라이더.
**제외(다음):**
- ML 깊이추정(Depth-Anything 등) — **seam 교체**로 후속(밝기맵 → 정밀 깊이맵).
- 이상 히트맵 드레이프(결함을 색으로) — 다음 슬라이스.
- 검사 파이프라인 직결(방금 검사한 이미지를 바로 3D로) — 다음.

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `frontend/src/components/ImageTo3D.jsx` (신규) | 업로드 + R3F 높이맵 표면 + 스케일 슬라이더 |
| `frontend/src/App.jsx` | 3번째 탭 **"이미지 3D"** 추가 |

## 3. 작업 명세 (What)

### 3-A. `ImageTo3D.jsx` (신규)
```jsx
import { useState, Suspense } from 'react'
import { Canvas, useLoader } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { TextureLoader } from 'three'

function ReliefSurface({ url, scale }) {
  const tex = useLoader(TextureLoader, url)
  const img = tex.image
  const aspect = img && img.width && img.height ? img.width / img.height : 1
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} castShadow receiveShadow>
      {/* 세분이 충분해야 굴곡이 보임 (256x256) */}
      <planeGeometry args={[4 * aspect, 4, 256, 256]} />
      <meshStandardMaterial
        map={tex}
        displacementMap={tex}          // 밝기 → 정점 변위(높이)
        displacementScale={scale}
        metalness={0.1} roughness={0.85}
      />
    </mesh>
  )
}

export default function ImageTo3D() {
  const [url, setUrl] = useState(null)
  const [scale, setScale] = useState(0.6)
  const onPick = (e) => {
    const f = e.target.files?.[0]; if (!f) return
    setUrl(URL.createObjectURL(f))
  }
  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <div style={{ position: 'absolute', top: 12, left: 16, zIndex: 10,
                    display: 'flex', flexDirection: 'column', gap: 8,
                    fontFamily: 'monospace', fontSize: 12, color: '#9aa0aa' }}>
        <label style={{ padding: '6px 12px', borderRadius: 8, cursor: 'pointer',
                        border: '1px solid rgba(31,184,205,0.45)',
                        background: 'rgba(31,184,205,0.12)', color: '#1FB8CD',
                        whiteSpace: 'nowrap', width: 'fit-content' }}>
          이미지 업로드 → 3D
          <input type="file" accept="image/*" hidden onChange={onPick} />
        </label>
        {url && (
          <label>높이 {scale.toFixed(2)}
            <input type="range" min="0" max="1.5" step="0.05" value={scale}
                   onChange={(e) => setScale(parseFloat(e.target.value))} />
          </label>
        )}
      </div>
      <Canvas shadows camera={{ position: [0, 3, 4], fov: 50 }}>
        <color attach="background" args={['#0b0d12']} />
        <ambientLight intensity={0.5} />
        <directionalLight position={[5, 8, 5]} intensity={1.1} castShadow />
        {url && (
          <Suspense fallback={null}>
            <ReliefSurface url={url} scale={scale} />
          </Suspense>
        )}
        <OrbitControls makeDefault enableDamping />
      </Canvas>
      {!url && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex',
                      alignItems: 'center', justifyContent: 'center',
                      pointerEvents: 'none', color: '#5b626d',
                      fontFamily: 'monospace' }}>
          이미지를 업로드하면 3D 표면(높이맵)으로 입체화됩니다
        </div>
      )}
    </div>
  )
}
```

### 3-B. `App.jsx` — 3번째 탭
```jsx
import ImageTo3D from './components/ImageTo3D'
// view 상태: 'inspection' | 'simulation' | 'image3d'
// nav에 탭 추가:
{tab('image3d', '이미지 3D')}
// 본문 분기:
{view === 'inspection' ? <Dashboard />
  : view === 'simulation' ? <SimulationView />
  : <ImageTo3D />}
```

## 4. 수용 기준

### 4-1. Greppable
```
test -f frontend/src/components/ImageTo3D.jsx && echo OK
grep -n "displacementMap\|planeGeometry\|TextureLoader\|type=\"file\"" frontend/src/components/ImageTo3D.jsx
grep -n "ImageTo3D\|'image3d'\|이미지 3D" frontend/src/App.jsx
```

### 4-2. 빌드 (Antigravity)
- `npm run build` 에러 없음(R3F/three 이미 의존성). **빌드 후 dist가 8080에 반영되는지도 확인**(빌드/서빙 이슈 재발 방지).

### 4-3. 회귀 가드
```
grep -c "Dashboard" frontend/src/App.jsx              # 검사 뷰 유지
grep -c "SimulationView" frontend/src/App.jsx          # 시뮬레이션 유지
grep -c "frontend/dist/index.html" app.py              # 서빙
grep -c "/api/sim/dataset" app.py                      # SIM 파이프라인 유지
```

### 4-4. 런타임 (당신/Antigravity — 핵심)
- **이미지 3D** 탭 → 검사 이미지(스크래치 있는 부품 등) 업로드 → **표면이 입체적으로 굴곡**지고, **높이 슬라이더**로 굴곡 강도 조절, 마우스로 회전/줌.
- 어두운 결함부가 *낮게/홈처럼* 보이는지(밝기→높이). Antigravity 녹화 첨부.

## 5. 검증 절차 (내가 수행)
"푸시 완료" → 재clone → 4-1 grep, 4-3 회귀. 4-2 빌드·4-4 입체화는 Antigravity 캡처. 통과 시 — **(a) 이상 히트맵 드레이프**(결함 색 강조) 또는 **(b) 깊이추정 모델 seam 교체**(밝기→정밀 깊이) 중 선택.

## 6. 커밋
- 브랜치: `feat/vis3d1-image-to-relief`
- 메시지(예): `feat(vis3d): lift uploaded image into 3D relief surface (displacementMap heightmap)`

## 7. 주의
- **세분(256×256) 필수** — 적으면 굴곡이 안 보인다.
- v1은 **밝기→높이 근사** — 정밀 깊이는 후속 seam(밝기맵을 깊이맵으로 교체). 지금 ML 욕심 금지.
- 큰 이미지는 텍스처 메모리↑ — 필요 시 업로드 시 리사이즈(후속).
- 이 기능은 **기존 SIM(합성데이터)과 별개** — 둘 다 유지. 탭으로 분리.
- 빌드 후 8080 반영 확인(직전 "흰 화면"이 빌드 누락이었으므로).
