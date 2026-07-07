# ARIA SIM-2 명세서 — 씬 파라미터화 + 도메인 랜덤화 (for Antigravity IDE)

> 3D 시뮬레이션 트랙 2단계. SIM-1의 고정 씬을 **변주 가능**하게 만든다.
> 목적: 같은 장면만 나오면 캡처해도 똑같은 데이터다 → **부품 자세·조명을 랜덤화**해야 SIM-3 캡처가 *다양한 학습 데이터*가 된다.

## 0. 핵심 설계 — 랜덤화는 "seam"이다

`sampleSceneParams()`를 **순수 함수 seam**으로 만든다. SIM-2는 버튼으로 1회 샘플링하지만,
**SIM-3는 같은 함수를 N번 호출**해 N장의 다양한 프레임을 캡처한다. 즉 SIM-2가 데이터 생성의 토대.

## 1. 범위 (Scope)

**포함:** `sampleSceneParams()` + `RANGES`(랜덤화 seam), 부품 자세(위치·회전)·조명(ambient·key·색온도) 랜덤화 배선, "랜덤화/자동" 컨트롤 패널 + 현재값 readout.
**제외(다음):**
- **카메라 각도 랜덤화 → SIM-3**(OrbitControls와 충돌하므로 전용 캡처 카메라로).
- 프레임 캡처 → manifest 내보내기 → SIM-3.
- 결함 합성 → SIM-4. 실측 부품 GLTF, 재질 랜덤화(후속).

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `frontend/src/sim/randomization.js` (신규) | `RANGES` + `sampleSceneParams()` 순수 함수 (재사용 seam) |
| `frontend/src/components/SimulationView.jsx` | `params` 상태 + 랜덤화/자동 + 조명·부품에 params 주입 + 컨트롤 패널 |

## 3. 작업 명세 (What)

### 3-A. `frontend/src/sim/randomization.js` (신규) — 랜덤화 seam
```javascript
export const RANGES = {
  part:  { x: [-0.15, 0.15], z: [-0.15, 0.15], rotY: [0, Math.PI * 2], tilt: [-0.12, 0.12] },
  light: { ambient: [0.20, 0.60], key: [0.60, 1.60] },
}
const rand = ([lo, hi]) => lo + Math.random() * (hi - lo)

// 색온도: warm ↔ cool 보간
function sampleColor() {
  const t = Math.random()
  const lerp = (a, b) => Math.round((a + (b - a) * t) * 255)
  return `rgb(${lerp(1.0, 0.86)},${lerp(0.94, 0.92)},${lerp(0.86, 1.0)})`
}

export function sampleSceneParams() {
  return {
    part:  {
      x: rand(RANGES.part.x), z: rand(RANGES.part.z),
      rotY: rand(RANGES.part.rotY),
      rotX: rand(RANGES.part.tilt), rotZ: rand(RANGES.part.tilt),
    },
    light: { ambient: rand(RANGES.light.ambient), key: rand(RANGES.light.key), color: sampleColor() },
  }
}
```

### 3-B. `SimulationView.jsx` — 배선
**상태/제어** (컴포넌트 최상단):
```jsx
import { useState, useEffect } from 'react'
import { sampleSceneParams } from '../sim/randomization'
// ...
const [params, setParams] = useState(sampleSceneParams)
const [auto, setAuto] = useState(false)
useEffect(() => {
  if (!auto) return
  const id = setInterval(() => setParams(sampleSceneParams()), 2000)
  return () => clearInterval(id)
}, [auto])
```

**조명에 주입** (Canvas 내 ambient/directional 교체):
```jsx
<ambientLight intensity={params.light.ambient} />
<directionalLight position={[4, 6, 4]} intensity={params.light.key}
                  color={params.light.color} castShadow />
```

**부품에 자세 주입** — `InspectionCell`에 prop 전달 → `InspectionPart`로:
```jsx
<InspectionCell partPose={params.part} />
```
`InspectionPart`가 pose를 받아 group transform에 적용(기존 floating 애니메이션은 유지):
```jsx
function InspectionPart({ pose = { x:0, z:0, rotX:0, rotY:0, rotZ:0 } }) {
  // ...기존 useRef/useFrame 유지...
  return (
    <group position={[pose.x, 0, pose.z]} rotation={[pose.rotX, pose.rotY, pose.rotZ]}>
      {/* 기존 부품 mesh + 스캔 링 그대로 */}
    </group>
  )
}
```
> `InspectionCell`은 `partPose`를 `<InspectionPart pose={partPose} />`로 넘기기만.

**컨트롤 패널** (오버레이, 우상단):
```jsx
<div style={{ position:'absolute', top:12, right:16, zIndex:10, display:'flex',
              flexDirection:'column', gap:6, fontFamily:'monospace', fontSize:11 }}>
  <div style={{ display:'flex', gap:6 }}>
    <button onClick={() => setParams(sampleSceneParams())}
            style={{ padding:'6px 12px', borderRadius:8, cursor:'pointer',
                     border:'1px solid rgba(31,184,205,0.45)', background:'rgba(31,184,205,0.12)',
                     color:'#1FB8CD' }}>랜덤화</button>
    <button onClick={() => setAuto(a => !a)}
            style={{ padding:'6px 12px', borderRadius:8, cursor:'pointer',
                     border:'1px solid rgba(255,255,255,0.1)', background:'transparent',
                     color: auto ? '#3DCAA5' : '#6b7280' }}>{auto ? '자동 ■' : '자동 ▶'}</button>
  </div>
  <div style={{ color:'#9aa0aa' }}>
    ambient {params.light.ambient.toFixed(2)} · key {params.light.key.toFixed(2)} ·
    yaw {(params.part.rotY * 180 / Math.PI).toFixed(0)}°
  </div>
</div>
```

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "export function sampleSceneParams\|export const RANGES" frontend/src/sim/randomization.js
grep -n "sampleSceneParams\|setParams\|auto\|partPose" frontend/src/components/SimulationView.jsx
grep -n "pose" frontend/src/components/SimulationView.jsx   # InspectionPart가 pose 수신
```

### 4-2. Headless smoke (내가 실행 — node)
- `sampleSceneParams()`가 `part`·`light` 키를 반환하고 값이 `RANGES` 안:
  `part.rotY ∈ [0, 2π]`, `light.ambient ∈ [0.2,0.6]`, `light.key ∈ [0.6,1.6]`, `light.color`는 `rgb(...)` 문자열. (순수 함수라 GPU/브라우저 불필요.)

### 4-3. 회귀 가드
```
grep -c "frontend/dist/index.html" app.py        # 서빙 일원화
grep -c "Canvas\|OrbitControls" frontend/src/components/SimulationView.jsx  # SIM-1 씬 유지
grep -c "SimulationView" frontend/src/App.jsx     # 토글 유지
grep -c "/api/train/upload" app.py                # 6A
grep -c "get_snapshot" app.py                     # HW-1
```

### 4-4. 빌드 + 런타임 (Antigravity)
- `npm run build` 에러 없음.
- 시뮬레이션 뷰에서 **"랜덤화"** 클릭 → 부품 자세(회전/위치)와 조명(밝기/색)이 **눈에 띄게 변함**.
- **"자동 ▶"** → 2초마다 변주 순환. 녹화 첨부.

## 5. 검증 절차 (내가 수행)
"푸시 완료" → 재clone → 4-1 grep, 4-2 node smoke, 4-3 회귀. 4-4는 Antigravity 빌드/녹화. 통과 시 **SIM-3(전용 캡처 카메라 + 프레임 캡처 → 기존 manifest 내보내기)** — 합성 데이터가 학습으로 이어지는 슬라이스.

## 6. 커밋
- 브랜치: `feat/sim2-domain-randomization`
- 메시지(예): `feat(sim): domain randomization seam (part pose + lighting) with randomize/auto controls`

## 7. 주의
- **`sampleSceneParams`는 순수 함수로 유지**(부수효과·DOM 접근 금지) — SIM-3가 N회 호출해 캡처에 재사용한다.
- **카메라 각도는 건드리지 말 것**(OrbitControls 충돌) — SIM-3 전용 캡처 카메라로.
- 기존 useFrame 애니메이션(부유·레이저)은 유지 — 랜덤화는 *베이스* 자세/조명만 바꾼다.
- 범위 엄수: 캡처·manifest·결함은 SIM-3/4.
