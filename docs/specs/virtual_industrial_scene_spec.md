# ARIA 명세서 — 가상 산업현장 씬 (게임형·24시간 가동) · Slice 1: 살아있는 공장 라인 for Antigravity

> 목표: 시뮬 공간을 *추상 루프*에서 **게임 같은 살아있는 공장**으로. 컨베이어가 24시간 멈춤 없이 부품을 흘리고, 검사기(검사 게이트)를 지나, OK/NG 결과물로 분류된다. 학습 중엔 러닝코어가 점등, 상태판에 사이클·escape율·FAT 판정이 뜬다.
> **기존 검사대(턴테이블+부품 = 데이터 캡처 대상)는 그대로** 두고, 그 주위에 공장 환경을 *추가*. 캡처 시엔 공장을 숨겨 데이터셋을 깨끗이 유지.

## 0. 핵심 원칙

- **24시간 움직임 = 파이프라인과 무관한 상시 ambient 애니메이션.** 컨베이어·부품 흐름은 `looping`이 꺼져 있어도 *항상* 돈다(useFrame). 파이프라인 이벤트(학습/검증/FAT)는 그 위에 *덧칠*된다.
- **캡처 무결성**: 데이터셋 캡처(toDataURL) 순간엔 공장 그룹을 `visible=false`로 숨겨 *검사대 부품만* 찍힌다.
- 성능: 동시 부품 수 상한, 단순 지오메트리(박스/실린더), 부품 그림자 off.

## 1. 범위 (Scope) — Slice 1

**포함:** 컨베이어 + 상시 부품 스폰/이동(24h) + 검사 게이트 + OK/NG 빈·카운터 + 상태판(사이클·escape·FAT) + 러닝코어(학습 중 점등). 캡처 시 공장 숨김.
**제외(후속 슬라이스):** 작업자/안전 시나리오, 다중 라인, 실제 낮/밤(24h 조명) 사이클, 부품별 *실제* 추론, 파티클/포스트프로세싱.

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `frontend/src/sim/factory.jsx` (신규) | `<FactoryLine/>` + 하위 컴포넌트 |
| `frontend/src/components/SimulationView.jsx` | Canvas에 `<FactoryLine/>` 배치 + 상태 전달 + 캡처 시 숨김 |

## 3. 작업 명세 (What)

### 3-A. `frontend/src/sim/factory.jsx` (신규)
`<FactoryLine looping cycle validation trainState />`가 아래를 합성. 모든 모션은 `useFrame`.

**(1) ConveyorBelt** — 바닥 옆 벨트(긴 박스) + 흐르는 줄무늬(텍스처 offset 또는 세그먼트 이동). 상시 회전감.
```jsx
function ConveyorBelt() {
  const stripes = useRef()
  useFrame((_, dt) => { if (stripes.current) stripes.current.position.x = (stripes.current.position.x + dt*1.2) % 1 })
  return (<group position={[0,0.5,3]}> {/* 검사대 옆 라인 */}
    <mesh receiveShadow><boxGeometry args={[10,0.1,1.2]} /><meshStandardMaterial color="#23262f" metalness={0.5} roughness={0.6}/></mesh>
    <group ref={stripes}>{[...Array(20)].map((_,i)=>(
      <mesh key={i} position={[-5+i*0.5,0.06,0]}><boxGeometry args={[0.12,0.02,1.1]}/><meshStandardMaterial color="#1FB8CD" emissive="#1FB8CD" emissiveIntensity={0.25}/></mesh>))}</group>
  </group>) }
```

**(2) FactoryParts** — *24시간 흐름의 핵심.* 일정 간격마다 부품 스폰 → +x 이동 → 게이트 통과 시 OK/NG 판정 → OK/NG 빈으로 분기 → 도착 후 소멸. `looping`과 무관하게 항상.
```jsx
function FactoryParts({ ngProb, onResult }) {
  const parts = useRef([])           // {id,x,verdict,lane}
  const acc = useRef(0); const id = useRef(0)
  const [,force] = useState(0)
  useFrame((_, dt) => {
    acc.current += dt
    if (acc.current > 1.1 && parts.current.length < 18) {     // ~1.1s마다 스폰(상한 18)
      acc.current = 0; id.current++
      parts.current.push({ id:id.current, x:-5, verdict:null, lane:0 })
    }
    for (const p of parts.current) {
      p.x += dt * 1.6
      if (p.verdict === null && p.x >= 0) {                   // 게이트(x=0)에서 판정
        p.verdict = Math.random() < ngProb ? 'NG' : 'OK'
        p.lane = p.verdict === 'OK' ? -0.35 : 0.35
        onResult?.(p.verdict)
      }
    }
    parts.current = parts.current.filter(p => p.x < 5.2)      // 끝에서 소멸
    force(n => n+1)
  })
  return (<group position={[0,0.62,3]}>{parts.current.map(p => (
    <mesh key={p.id} position={[p.x, 0, p.lane]} castShadow>
      <boxGeometry args={[0.28,0.18,0.28]} />
      <meshStandardMaterial
        color={p.verdict==='NG' ? '#f87171' : p.verdict==='OK' ? '#34d399' : '#9aa3b2'}
        emissive={p.verdict==='NG' ? '#f87171' : p.verdict==='OK' ? '#34d399' : '#000'} emissiveIntensity={0.35}/>
    </mesh>))}</group>) }
```
- `ngProb`는 SimulationView가 최신 검증에서 도출(아래 3-B). 검증 전엔 작은 기본값(예 0.12).

**(3) InspectionGantry (검사기)** — 게이트(x=0) 위 아치 + 아래로 쓸어내리는 스캔광(useFrame로 좌우/상하 sweep). 부품이 통과할 때 깜빡.

**(4) ResultBins + Counter (결과물)** — 벨트 끝 OK(초록)·NG(빨강) 빈 두 개 + 누적 카운터(drei `<Text>`로 `OK n · NG m`). `onResult`가 카운트 증가.

**(5) StatusBoard** — 공장 위 빌보드(drei `<Text>` 또는 `<Html>`). 표시: `사이클 {cycle}`, `escape {validation.escape_rate}`, `FAT {validation.fat_verdict}`(PASS 초록/FAIL 빨강), `{looping?'가동중':'대기'}`.

**(6) LearningCore (학습)** — 중앙 부유 코어(아이코사/구). `trainState?.status==='running'`이면 emissive 강해지고 빠르게 회전/맥동, 아니면 잔잔. = *학습이 도는 게 보임*.

### 3-B. SimulationView 통합
```jsx
// 최신 검증에서 NG 확률 도출(없으면 기본)
const ngProb = validation?.escape_rate != null
  ? Math.min(0.5, (validation.escape_rate + (validation.fp_rate||0)) || 0.12)
  : 0.12
// Canvas 안, 기존 검사 씬과 나란히:
<group ref={factoryGroupRef}>
  <FactoryLine looping={looping} cycle={cycle} validation={validation} trainState={trainState} ngProb={ngProb} />
</group>
```
**캡처 시 숨김** — captureDataset의 toDataURL 직전/직후:
```jsx
if (factoryGroupRef.current) factoryGroupRef.current.visible = false   // 데이터셋엔 검사대 부품만
// ... 기존 toDataURL ...
if (factoryGroupRef.current) factoryGroupRef.current.visible = true
```

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "FactoryLine\|ConveyorBelt\|FactoryParts\|InspectionGantry\|ResultBins\|StatusBoard\|LearningCore" frontend/src/sim/factory.jsx
grep -n "FactoryLine\|factoryGroupRef\|ngProb" frontend/src/components/SimulationView.jsx
grep -n "factoryGroupRef.current.visible" frontend/src/components/SimulationView.jsx   # 캡처 숨김
```

### 4-2. 회귀 가드
```
grep -c "loopRef\|factoryLoop\|captureDataset\|sampleSceneParams" frontend/src/components/SimulationView.jsx   # 루프·캡처 보존
grep -c "preserveDrawingBuffer\|toDataURL" frontend/src/components/SimulationView.jsx                          # 캡처 경로 보존
```
- `npm run build`(Node20) 무에러.

### 4-3. 런타임 (당신/Antigravity)
- 시뮬 진입 즉시 **컨베이어가 돌고 부품이 계속 흐름**(루프 정지 상태에서도 = 24h ambient).
- 게이트에서 부품이 **OK(초록)/NG(빨강)로 갈려 빈에 쌓이고 카운터 증가**.
- **▶ 자동 순환** 돌리면: 러닝코어가 학습 중 점등 → 검증 후 **상태판에 escape율·FAT PASS/FAIL** 뜨고, 이후 부품 NG 비율이 실제 escape율을 반영.
- **데이터 생성/캡처 시** 공장이 잠깐 숨고 검사대 부품만 찍힘(데이터셋 오염 없음).
- Antigravity 녹화: 상시 흐름 + OK/NG 분류 + 학습 점등 + FAT 표시.

## 5. 검증 (내가 수행)
재clone → 4-1 grep(컴포넌트·통합·캡처숨김), 4-2 회귀. 빌드·실제 모션·캡처 무결성은 Antigravity 녹화(R3F는 헤드리스로 못 돌림 — 구조만 확인).

## 6. 커밋
- 브랜치: `feat/virtual-industrial-scene` · 메시지: `feat(sim): living factory line — continuous conveyor, OK/NG routing, status board, learning core (capture-safe)`

## 7. 주의
- **상시 모션은 파이프라인과 분리** — `looping`이 꺼져도 컨베이어/부품은 돈다(24h). 파이프라인은 *덧칠*만.
- **캡처 무결성 필수** — 공장 숨김 없이 toDataURL 하면 데이터셋이 오염됨. `factoryGroupRef.visible` 토글 빠뜨리지 말 것.
- 컨베이어 부품의 OK/NG는 **시각화(집계 기반 확률)**지 부품별 실제 추론이 아님 — 솔직 표기. 실제 추론은 후속(부품마다 capture→cosine은 무거움).
- **성능**: 동시 부품 ≤18, 단순 지오메트리, 부품 그림자 off. 프레임 저하 시 상한↓.
- main 단일 라인 위 작업(FAT 게이트 머지 후) — 새 분기 남발 금지.
- 후속 슬라이스: 작업자/안전 시나리오, 다중 라인, 실제 낮/밤 24h 조명, 부품별 실추론.
