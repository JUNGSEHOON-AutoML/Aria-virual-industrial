# ARIA 명세서 — 가상 산업현장 Slice 2: 공장 규모 확장 (다중 라인 + 작업자 + 설비) for Antigravity

> 목표: 한 줄짜리 라인을 **진짜 공장 현장**으로 — 평행 다중 라인이 동시에 돌고, 작업자가 배치되고, 로봇팔·제어판·바닥 표시·기둥 등 설비가 채워진다. 전부 상시(24h) 가동.
> **순수 추가 시각화**(factory.jsx). 캡처 가드·루프·스코어러 무변경.

## 0. 핵심 발견 / 원칙

- 현재 컴포넌트들이 `z=3`을 내부에 박아둠 → **바깥 그룹에 z 오프셋만 주면** 같은 라인을 다른 z에 복제(내부 수정 0).
- 검사대(캡처 대상)는 **z≈0**. 추가 라인은 **뒤쪽(z=5, 6.5)** 에 둬 검사대와 겹치지 않게.
- **캡처 무결성 유지**: 새 라인·작업자·설비 *전부 `<FactoryLine>` 그룹 안*에 → SimulationView의 `factoryGroupRef` 숨김이 그대로 다 가린다. (그룹 밖에 두지 말 것.)
- 성능: 라인당 부품 상한↓(예 10), 단순 지오메트리, 작업자/설비 그림자 최소.

## 1. 범위 (Scope) — Slice 2

**포함:** `ProductionLine`(기존 4컴포넌트를 z 오프셋 그룹으로 래핑 + 라인별 카운트) → **3개 라인**; `Workers`(저폴리 인물 + idle 애니); `Equipment`(로봇팔 sweep ×2, 제어판, 바닥 위험표시, 기둥/오버헤드 빔).
**제외(후속):** 부품별 실추론, 작업자 안전 시나리오/충돌, 낮/밤 24h 조명, 라인 간 물류 이동.

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `frontend/src/sim/factory.jsx` | ProductionLine 추출 + 다중 라인 + Workers + Equipment |

> SimulationView·캡처 가드·백엔드 **무변경**(이미 `<FactoryLine>` 통째로 숨김).

## 3. 작업 명세 (What)

### 3-A. ProductionLine 추출 (기존 단일 라인 → 파라미터화)
기존 `FactoryLine` 안의 belt+parts+gantry+bins 묶음을 **z 오프셋 그룹**으로 래핑한 컴포넌트로 추출. *내부 컴포넌트는 그대로* 재사용.
```jsx
function ProductionLine({ z = 3, ngProb = 0.12, cap = 10 }) {
  const [ok, setOk] = useState(0); const [ng, setNg] = useState(0)
  const onResult = (v) => v === 'OK' ? setOk(c => c + 1) : setNg(c => c + 1)
  return (
    <group position={[0, 0, z - 3]}>   {/* 기존이 z=3 기준 → (z-3) 오프셋으로 임의 z 배치 */}
      <ConveyorBelt />
      <FactoryParts ngProb={ngProb} onResult={onResult} cap={cap} />
      <InspectionGantry />
      <ResultBins okCount={ok} ngCount={ng} />
    </group>
  )
}
```
- `FactoryParts`에 **`cap` prop 추가**(기본 18, 다중 라인에선 10) — 동시 부품 상한:
  `if (acc.current > 1.1 && parts.current.length < cap) { ... }`

### 3-B. FactoryLine = 3개 라인 + 작업자 + 설비
```jsx
export default function FactoryLine({ looping, cycle, validation, trainState, ngProb }) {
  return (
    <group>
      <ProductionLine z={3}   ngProb={ngProb}        cap={10} />   {/* 기존 라인(메인) */}
      <ProductionLine z={5}   ngProb={ngProb * 0.8}  cap={10} />
      <ProductionLine z={6.5} ngProb={ngProb * 1.2}  cap={10} />
      <Workers />
      <Equipment />
      <StatusBoard cycle={cycle} validation={validation} looping={looping} />
      <LearningCore trainState={trainState} />
    </group>
  )
}
```
> StatusBoard/LearningCore는 *전역 1개*(파이프라인 표시). 다중 라인은 ambient.

### 3-C. Workers (작업자) — 저폴리 인물 + idle 애니
```jsx
function Worker({ position, hue = '#f59e0b', phase = 0 }) {
  const ref = useRef()
  useFrame((s) => { if (ref.current) {
    ref.current.position.y = position[1] + Math.sin(s.clock.elapsedTime * 1.5 + phase) * 0.03   // 가벼운 들숨/움직임
    ref.current.rotation.y = Math.sin(s.clock.elapsedTime * 0.4 + phase) * 0.25
  }})
  return (<group ref={ref} position={position}>
    <mesh position={[0,0.55,0]} castShadow><cylinderGeometry args={[0.16,0.2,0.7,8]} /><meshStandardMaterial color="#2d3340"/></mesh>{/* 몸통 */}
    <mesh position={[0,1.0,0]} castShadow><sphereGeometry args={[0.15,12,12]} /><meshStandardMaterial color="#e8c39e"/></mesh>{/* 머리 */}
    <mesh position={[0,1.08,0]}><sphereGeometry args={[0.17,12,12,0,Math.PI*2,0,Math.PI/2]} /><meshStandardMaterial color={hue} metalness={0.3}/></mesh>{/* 안전모 */}
  </group>) }
function Workers() {
  const spots = [[-3.2,0,2.0,0],[1.5,0,2.0,1.2],[-1.0,0,4.0,2.0],[3.0,0,5.6,0.7],[-3.5,0,6.2,3.1]]
  return (<group>{spots.map(([x,y,z,p],i)=>(<Worker key={i} position={[x,y,z]} phase={p} hue={i%2?'#1FB8CD':'#f59e0b'} />))}</group>) }
```
(라인 옆 통로/스테이션 위치. 안전모 색 교차로 생기.)

### 3-D. Equipment (설비) — 로봇팔·제어판·바닥표시·구조물
```jsx
function RobotArm({ position }) {        // 천천히 sweep하는 관절 팔
  const j1 = useRef(); const j2 = useRef()
  useFrame((s) => { const t = s.clock.elapsedTime
    if (j1.current) j1.current.rotation.y = Math.sin(t*0.5)*0.6
    if (j2.current) j2.current.rotation.z = Math.sin(t*0.7)*0.5 + 0.3 })
  return (<group position={position}>
    <mesh castShadow><cylinderGeometry args={[0.25,0.3,0.3,12]} /><meshStandardMaterial color="#2d3240" metalness={0.7}/></mesh>{/* 베이스 */}
    <group ref={j1} position={[0,0.2,0]}>
      <mesh position={[0,0.4,0]} castShadow><boxGeometry args={[0.14,0.8,0.14]} /><meshStandardMaterial color="#3a4150" metalness={0.6}/></mesh>
      <group ref={j2} position={[0,0.8,0]}>
        <mesh position={[0.3,0,0]} castShadow><boxGeometry args={[0.6,0.12,0.12]} /><meshStandardMaterial color="#3a4150" metalness={0.6}/></mesh>
        <mesh position={[0.6,0,0]}><boxGeometry args={[0.1,0.18,0.18]} /><meshStandardMaterial color="#1FB8CD" emissive="#1FB8CD" emissiveIntensity={0.4}/></mesh>{/* 그리퍼 */}
      </group>
    </group>
  </group>) }
function Equipment() {
  return (<group>
    <RobotArm position={[-4.5, 0.5, 4.2]} />
    <RobotArm position={[4.5, 0.5, 5.8]} />
    {/* 제어판 */}
    <group position={[-5.5, 0.5, 3]}>
      <mesh position={[0,0.5,0]} castShadow><boxGeometry args={[0.5,1,0.8]} /><meshStandardMaterial color="#23262f" metalness={0.5}/></mesh>
      <mesh position={[0.26,0.7,0]}><boxGeometry args={[0.02,0.4,0.6]} /><meshStandardMaterial color="#1FB8CD" emissive="#1FB8CD" emissiveIntensity={0.5}/></mesh>
    </group>
    {/* 바닥 위험표시(통로 라인) */}
    {[2.5, 4.0, 7.4].map((z,i)=>(
      <mesh key={i} position={[0,0.011,z]} rotation={[-Math.PI/2,0,0]}><planeGeometry args={[11,0.12]} /><meshStandardMaterial color="#f5c518"/></mesh>))}
    {/* 기둥 + 오버헤드 빔(공장 골조) */}
    {[[-6,8],[6,8],[-6,1],[6,1]].map(([x,z],i)=>(
      <mesh key={i} position={[x,2,z]} castShadow><boxGeometry args={[0.3,4,0.3]} /><meshStandardMaterial color="#3a4150" metalness={0.4}/></mesh>))}
    <mesh position={[0,3.9,4.5]}><boxGeometry args={[13,0.2,0.2]} /><meshStandardMaterial color="#3a4150"/></mesh>
  </group>) }
```

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "function ProductionLine\|function Worker\|function Workers\|function RobotArm\|function Equipment" frontend/src/sim/factory.jsx
grep -c "<ProductionLine" frontend/src/sim/factory.jsx          # ≥3 (다중 라인)
grep -n "cap = \|length < cap" frontend/src/sim/factory.jsx      # 부품 상한 prop
grep -n "ConveyorBelt\|FactoryParts\|InspectionGantry\|ResultBins\|StatusBoard\|LearningCore" frontend/src/sim/factory.jsx | head  # 기존 보존
```

### 4-2. 회귀 가드 (캡처·루프·스코어러 무변경)
```
grep -c "factoryGroupRef" frontend/src/components/SimulationView.jsx          # 캡처 가드 그대로(변경 없어야)
grep -c "loopRef\|factoryLoop\|armStall" frontend/src/components/SimulationView.jsx  # 루프 보존
grep -c "toDataURL\|preserveDrawingBuffer" frontend/src/components/SimulationView.jsx
test -f scorer/feature_bank.py && echo "S1 보존"
```
- `npm run build`(Node20) 무에러.

### 4-3. 런타임 (당신/Antigravity)
- **3개 라인이 동시에** 부품을 흘리고 OK/NG로 분류 — 진짜 공장 느낌.
- **작업자들이 라인 옆에 서서** 살짝 움직임(idle), **로봇팔이 천천히 sweep**, 제어판 점등, 바닥 위험표시·기둥·오버헤드 빔.
- 상태판·러닝코어는 전과 동일(전역).
- **데이터 생성/캡처 시** 공장 *전체*(새 라인·작업자·설비 포함)가 숨고 검사대 부품만 찍힘 — 가드가 그룹 통째로 가리는지 육안 확인.
- 프레임률 확인(3라인×10부품 + 설비). 저하 시 cap/라인수↓.
- Antigravity 녹화.

## 5. 검증 (내가 수행)
재clone → 4-1 grep(ProductionLine ≥3·Worker·RobotArm·기존보존), 4-2 회귀(캡처·루프·스코어러 무변경). 빌드·실제 렌더·캡처 무결성은 Antigravity(R3F 헤드리스 불가 — 구조만).

## 6. 커밋
- 브랜치 없이 **main에 직접**(작은 시각화) 또는 `feat/factory-scale-multiline` → main FF.
- 메시지: `feat(sim): factory-scale floor — multi-line, workers, equipment (capture-safe)`

## 7. 주의
- **전부 `<FactoryLine>` 그룹 안** — 캡처 가드가 통째로 숨기려면 그룹 밖에 두면 안 됨.
- 추가 라인은 **z=5, 6.5(뒤쪽)** — 검사대(z≈0)와 안 겹치게.
- **성능**: 라인당 cap=10, 단순 지오메트리, 작업자/설비 그림자 최소. 저하 시 라인 2개로.
- SimulationView·백엔드·캡처 로직 **건드리지 말 것**(factory.jsx만).
- 작업자/로봇팔은 *분위기 연출*(idle/sweep) — 실제 작업·물류·충돌 아님(후속).
- main 단일 라인 유지 — 분기 남발 금지.
