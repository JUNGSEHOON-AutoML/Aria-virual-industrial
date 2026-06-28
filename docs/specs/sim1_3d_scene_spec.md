# ARIA SIM-1 명세서 — 3D 산업현장 시뮬레이션 뷰 (for Antigravity IDE)

> 3D 시뮬레이션 트랙의 첫 슬라이스. **"UI를 열면 3D 산업 검사 현장이 나온다"** 만.
> 도메인 랜덤화·결함 합성·데이터 내보내기·고정밀 렌더는 다음 슬라이스(SIM-2~). **한 번에 안 만든다.**

## 0. 목표 (Why)

통합 React UI에 **3D 산업 검사 현장(디지털 트윈)** 을 띄운다. 브라우저 내 렌더(React Three Fiber).
이 씬은 나중에 그대로 **합성 데이터 생산자**가 된다(렌더 → 기존 6A/6B `manifest` seam → 학습).
SIM-1은 그 토대 — **씬이 보이고, 돌려볼 수 있다**까지.

## 1. 범위 (Scope)

**포함:** R3F 의존성 추가 + `SimulationView.jsx`(기본 검사 현장 씬: 작업대·부품·카메라 리그·조명·그리드, OrbitControls) + App에 **검사/시뮬레이션 뷰 토글**.
**제외(다음):** 도메인 랜덤화(SIM-2), 프레임 캡처→manifest(SIM-3), 결함 합성(SIM-4), GLTF 실측 부품 로딩, Omniverse/오프라인 고정밀 렌더, 물리 시뮬레이션.

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `frontend/package.json` | `three`, `@react-three/fiber`, `@react-three/drei` 추가 |
| `frontend/src/components/SimulationView.jsx` (신규) | R3F Canvas + 검사 현장 씬 + OrbitControls |
| `frontend/src/App.jsx` | `view` 상태('inspection'\|'simulation') + 상단 토글 + 분기 렌더 |

## 3. 작업 명세 (What)

### 3-A. 의존성
```
cd frontend && npm install three @react-three/fiber @react-three/drei
```

### 3-B. `SimulationView.jsx` (신규) — 기본 검사 현장
```jsx
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Grid } from '@react-three/drei'

function InspectionCell() {
  return (
    <group>
      {/* 작업대/컨베이어 */}
      <mesh position={[0, 0.25, 0]} castShadow receiveShadow>
        <boxGeometry args={[3, 0.5, 1]} /><meshStandardMaterial color="#3a3f4b" />
      </mesh>
      {/* 검사 대상 부품 (placeholder — SIM 후속에서 실측 부품으로 교체) */}
      <mesh position={[0, 0.8, 0]} castShadow>
        <boxGeometry args={[0.6, 0.6, 0.6]} />
        <meshStandardMaterial color="#d0d3d8" metalness={0.3} roughness={0.55} />
      </mesh>
      {/* 검사 카메라 리그 */}
      <mesh position={[0, 1.9, 0]}>
        <cylinderGeometry args={[0.08, 0.08, 0.3, 16]} />
        <meshStandardMaterial color="#1FB8CD" emissive="#1FB8CD" emissiveIntensity={0.4} />
      </mesh>
    </group>
  )
}

export default function SimulationView() {
  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <div style={{ position: 'absolute', top: 12, left: 16, zIndex: 10,
                    fontFamily: 'monospace', fontSize: 12, letterSpacing: 2,
                    color: 'var(--text-secondary, #9aa0aa)' }}>
        SIMULATION — 산업 현장 디지털 트윈
      </div>
      <Canvas shadows camera={{ position: [4, 3, 4], fov: 50 }}>
        <color attach="background" args={['#0b0d12']} />
        <ambientLight intensity={0.45} />
        <directionalLight position={[5, 8, 5]} intensity={1.1} castShadow />
        <InspectionCell />
        <Grid args={[24, 24]} cellColor="#222730" sectionColor="#39424f"
              infiniteGrid fadeDistance={30} position={[0, 0, 0]} />
        <OrbitControls enableDamping makeDefault />
      </Canvas>
    </div>
  )
}
```
> drei `Environment`(HDRI 다운로드)는 **쓰지 않는다** — 오프라인/네트워크 이슈 회피. 위 라이트만으로 충분.
> 부품은 placeholder 박스 — 실측 부품(GLTF)·결함은 SIM 후속 슬라이스.

### 3-C. `App.jsx` — 뷰 토글
```jsx
import { useState } from 'react'
import Dashboard from './components/Dashboard'
import SimulationView from './components/SimulationView'

export default function App() {
  const [view, setView] = useState('inspection')  // 시작 화면을 시뮬레이션으로 하려면 'simulation'
  const tab = (id, label) => (
    <button onClick={() => setView(id)}
      style={{ padding: '6px 14px', fontFamily: 'monospace', fontSize: 12,
               letterSpacing: 1, cursor: 'pointer', borderRadius: 8,
               border: '1px solid rgba(255,255,255,0.08)',
               background: view === id ? 'rgba(31,184,205,0.12)' : 'transparent',
               color: view === id ? 'var(--cyan, #1FB8CD)' : 'var(--text-secondary,#9aa0aa)' }}>
      {label}
    </button>
  )
  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <nav style={{ display: 'flex', gap: 8, padding: '8px 16px',
                    borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        {tab('inspection', '검사')}
        {tab('simulation', '시뮬레이션')}
      </nav>
      <div style={{ flex: 1, minHeight: 0 }}>
        {view === 'inspection' ? <Dashboard /> : <SimulationView />}
      </div>
    </div>
  )
}
```

## 4. 수용 기준

### 4-1. Greppable (배선)
```
grep -n "@react-three/fiber\|@react-three/drei\|\"three\"" frontend/package.json
test -f frontend/src/components/SimulationView.jsx && echo OK
grep -n "Canvas\|OrbitControls" frontend/src/components/SimulationView.jsx
grep -n "SimulationView\|setView\|'simulation'" frontend/src/App.jsx
```

### 4-2. 빌드 (Antigravity 수행)
- `cd frontend && npm install && npm run build` → 에러 없이 `dist/` 생성(R3F가 Vite 빌드에 포함).

### 4-3. 회귀 가드
```
grep -c "frontend/dist/index.html" app.py        # 서빙 일원화 유지
grep -c "/api/train/upload" app.py                # 6A 유지
grep -c "get_snapshot" app.py                     # HW-1 유지
grep -c "Dashboard" frontend/src/App.jsx          # 검사 뷰 유지(토글로 접근)
grep -c "inspect_via_registry" autonomous_agent.py # 1~4단계 유지
```

### 4-4. 런타임 (당신/Antigravity — 핵심)
- `http://<host>:8080/` 접속 → 상단 **검사 / 시뮬레이션** 토글.
- **시뮬레이션** 클릭 → 3D 검사 현장(작업대+부품+카메라 리그+그리드)이 뜨고, **마우스로 회전/줌**이 됨.
- 검사 토글로 돌아가면 기존 대시보드 정상.
- Antigravity 브라우저로 3D 씬 스크린샷/녹화 첨부.

## 5. 검증 절차 (내가 수행)
"푸시 완료" → 재clone → 4-1 grep, 4-3 회귀. 4-2 빌드·4-4 3D 렌더는 Antigravity 캡처로. 통과 시 **SIM-2(씬 파라미터화 + 도메인 랜덤화)**.

## 6. 커밋
- 브랜치: `feat/sim1-3d-scene`
- 메시지(예): `feat(sim): 3D industrial inspection scene (R3F) behind 검사/시뮬레이션 view toggle`

## 7. SIM 트랙 로드맵 (참고 — 지금은 SIM-1만)
- **SIM-1 (지금):** 3D 검사 현장이 UI에 뜬다.
- **SIM-2:** 씬 파라미터화 + 도메인 랜덤화(조명·자세·카메라).
- **SIM-3:** 렌더 프레임 캡처 → **기존 6A/6B `manifest`로 내보내기**(합성 데이터 → 학습 연결).
- **SIM-4:** 결함 합성(정상/결함 라벨) → 산업 결함 데이터 부족 해소.
- (후속) 실측 부품 GLTF, Omniverse 고정밀, sim-to-real 갭 검증.

## 8. 주의
- **범위 엄수:** SIM-1은 "씬이 뜨고 돌아간다"까지. 데이터 생성·결함·실측 부품은 다음.
- drei `Environment`(HDRI) 사용 금지(오프라인 안정성). 라이트로만.
- three는 큰 의존성 — 빌드 시간 증가는 정상. 서빙 일원화(8080이 dist 서빙)는 그대로 유지.
- 실제 재현하려는 산업 현장/부품이 정해지면 알려주면 placeholder를 그 형상으로 SIM-2에서 교체.
