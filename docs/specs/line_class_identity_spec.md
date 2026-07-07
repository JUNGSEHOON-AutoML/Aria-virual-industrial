# ARIA 명세서 — 가상 산업현장 Slice A: 라인 = MVTec 클래스 정체성 + 비전캠 제거 for Antigravity

> 목표: 불필요한 VISION CAM(ARIA-01) 제거 + **각 라인을 MVTec AD 클래스 하나에 대응**(라벨·매핑). 라인마다 클래스 정체성이 보이게.
> 이번은 *정체성/라벨*(프론트). 라인별 *진짜 학습/판정*(클래스별 메모리뱅크)은 Slice B.

## 1. 범위 (Scope)

**포함:** VISION CAM 라벨 + 장식용 CameraRig 제거; `ProductionLine`에 `classId` + 라인 클래스 라벨; 3개 라인 → 3개 MVTec 클래스 매핑(설정형).
**제외(Slice B):** 클래스별 bank.npy, MVTec 클래스 인테이크, 라인별 실제 OK/NG 바인딩 — 다음.

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `frontend/src/components/SimulationView.jsx` | VISION CAM 라벨 + `<CameraRig/>` 제거 |
| `frontend/src/sim/factory.jsx` | ProductionLine `classId` + 라벨; 3라인 클래스 매핑 |

## 3. 작업 명세 (What)

### 3-A. 비전캠 제거 (SimulationView)
`SceneLabels`에서 **"VISION CAM — ARIA-01" `<Text>` 블록 제거**(현재 L152~162). `PART [PLACEHOLDER]` 라벨은 유지(검사대 부품 표시).
`InspectionCell`에서 **`<CameraRig />` 제거**(장식용 오버헤드 카메라). 
- ⚠️ **캡처 카메라 로직은 건드리지 말 것** — 실제 캡처는 R3F 카메라(`glRef`/`GLBridge`)를 쓰며 `CameraRig`는 *시각 장식*일 뿐. GLBridge·captureDataset·glRef는 그대로.

### 3-B. 라인 = 클래스 (factory.jsx)
파일 상단 설정형 클래스 목록:
```jsx
// 라인별 MVTec AD 클래스 (설정형 — 원하는 클래스로 교체 가능)
export const MVTEC_CLASSES = ['bottle', 'carpet', 'screw']
```
`ProductionLine`에 `classId` 추가 + 라인 시작부에 클래스 라벨:
```jsx
function ProductionLine({ z = 3, ngProb = 0.12, cap = 10, classId = '' }) {
  const [ok, setOk] = useState(0); const [ng, setNg] = useState(0)
  const onResult = (v) => v === 'OK' ? setOk(c => c + 1) : setNg(c => c + 1)
  return (
    <group position={[0, 0, z - 3]}>
      <ConveyorBelt />
      <FactoryParts ngProb={ngProb} onResult={onResult} cap={cap} />
      <InspectionGantry />
      <ResultBins okCount={ok} ngCount={ng} />
      {classId && (
        <Text position={[-5.6, 1.05, 0]} fontSize={0.32} color="#1FB8CD"
          anchorX="left" anchorY="middle" rotation={[0, 0, 0]}
          characters="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 -–—·">
          {`LINE · ${classId.toUpperCase()}`}
        </Text>
      )}
    </group>
  )
}
```
`FactoryLine`에서 3라인에 클래스 매핑:
```jsx
import { /* 기존 */ } from '...'   // Text가 이미 import 돼 있어야(없으면 drei에서 추가)
// ...
<ProductionLine z={3}   classId={MVTEC_CLASSES[0]} ngProb={ngProb}        cap={10} />
<ProductionLine z={5}   classId={MVTEC_CLASSES[1]} ngProb={ngProb * 0.8}  cap={10} />
<ProductionLine z={6.5} classId={MVTEC_CLASSES[2]} ngProb={ngProb * 1.2}  cap={10} />
```

## 4. 수용 기준

### 4-1. Greppable
```
grep -c "VISION CAM" frontend/src/components/SimulationView.jsx          # 0 (제거)
grep -c "CameraRig" frontend/src/components/SimulationView.jsx           # 정의는 남아도 <CameraRig/> 사용 0
grep -n "MVTEC_CLASSES\|classId" frontend/src/sim/factory.jsx
grep -c "classId={MVTEC_CLASSES" frontend/src/sim/factory.jsx            # 3 (라인별 매핑)
grep -n "LINE · \|classId.toUpperCase" frontend/src/sim/factory.jsx       # 라인 클래스 라벨
```

### 4-2. 회귀 가드
```
grep -c "<ProductionLine" frontend/src/sim/factory.jsx                   # 여전히 3
grep -c "factoryGroupRef\|toDataURL\|GLBridge\|glRef" frontend/src/components/SimulationView.jsx  # 캡처 경로 보존
grep -c "loopRef\|factoryLoop\|armStall" frontend/src/components/SimulationView.jsx               # 루프 보존
```
- `npm run build`(Node20) 무에러.

### 4-3. 런타임 (당신/Antigravity)
- 오버헤드 **비전캠(ARIA-01)이 사라짐**.
- 3개 라인 각각에 **`LINE · BOTTLE` / `LINE · CARPET` / `LINE · SCREW`** 라벨이 붙어, 라인마다 다른 클래스임이 보임.
- 컨베이어·작업자·설비·캡처 가드 전과 동일.
- Antigravity 녹화(비전캠 제거 전/후 + 라인 라벨).

## 5. 검증 (내가 수행)
재clone → 4-1 grep(VISION CAM 0·classId·3매핑·라벨), 4-2 회귀(라인 3·캡처·루프). 렌더는 Antigravity(R3F 헤드리스 불가).

## 6. 커밋
- main 직접 또는 `feat/line-class-identity` → main FF.
- 메시지: `feat(sim): map each line to an MVTec class (label) + remove VISION CAM rig`

## 7. 주의
- **캡처 카메라 로직 보존** — `CameraRig`는 장식, 실제 캡처는 GLBridge/glRef. 후자 건드리지 말 것.
- 클래스 목록은 **설정형**(`MVTEC_CLASSES`) — bottle/carpet/screw는 예시, 원하는 걸로 교체.
- 이번은 **라벨/정체성만** — 라인별 *진짜* 학습/판정(클래스별 bank, MVTec 인테이크)은 **Slice B**.
- 학습은 2D MVTec 이미지 위 — 3D는 데이터 생성·오케스트레이션 층(정직한 선 유지).
- main 단일 라인 유지.
