# ARIA 명세서 — ① 자동순환 버퍼링 수정 (캡처 루프 → 클래스 순회) for Antigravity

> 증상: "자동 순환 시작" 시 카메라가 와리가리 + 버퍼링.
> 원인(확정): `factoryLoop`→`runCycle`이 매 사이클 `captureDataset(24)` 호출 → OrbitControls를 끄고 **카메라를 24번 랜덤 순간이동 + 동기 toDataURL 24회**(SimulationView L334~363). 3초마다 반복 → 카메라 점프(와리가리) + 화면 멈춤(버퍼링).
> 핵심: 이 캡처 루프는 *옛 합성-캡처* 레거시. 진짜 워크플로는 **클래스별 가동**(MVTec). → 자동순환을 **선택 클래스 순회(classTrain→classValidate)**로 교체하면 버퍼링 사라지고 의미도 생김.

## 1. 범위 (Scope)

**포함:** `factoryLoop`를 캡처 루프에서 **선택 클래스 자동 순회**로 교체. `captureDataset`는 **수동 버튼 전용**으로 남김(루프에서 제거).
**제외:** 카메라 클로즈업·이미지 텍스처(= ② 명세서).

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `frontend/src/components/SimulationView.jsx` | `factoryLoop` 교체, `runCycle` 미사용 |

## 3. 작업 명세 (What)

### 3-A. factoryLoop 교체 — 캡처 대신 클래스 순회
```jsx
async function factoryLoop() {
  setLoopError(null); setLooping(true); loopRef.current = true
  let cyc = 0
  const classes = (selectedClasses && selectedClasses.length) ? selectedClasses : MVTEC_CLASSES
  while (loopRef.current) {
    for (const cid of classes) {
      if (!loopRef.current) break
      setActiveClass?.(cid)                              // (②에서 클로즈업이 읽음; 없으면 생략)
      const path = `${mvtecRoot}/${cid}`
      try {
        const t = await classTrain(cid, path)            // 진짜 클래스 학습
        if (t?.ok) {
          await waitTrainingDone().catch(() => {})       // 하트비트로 학습 done 대기
          await classValidate(cid, path)                 // 진짜 검증 → class_result(WS)로 라인 갱신
        }
      } catch (e) { console.warn('[loop] class 실패:', cid, e) }
      if (!loopRef.current) break
      await sleep(1500)                                  // 라인 간 텀
    }
    setCycle(++cyc)                                       // 현황판 사이클
    if (!loopRef.current) break
    await sleep(3000)
  }
  setLooping(false)
}
```
- **`captureDataset`/`runCycle`를 factoryLoop에서 완전히 제거.** (카메라 하이재킹 원천 차단.)
- `runCycle`/`simTrain`/`simValidate`/`captureDataset`는 **수동 "데이터셋 생성(24장)" 버튼에서만** 유지(기존 버튼 onClick 그대로). 루프만 안 부르면 됨.

> 주의: `captureDataset`는 그대로 두되 **루프에서 호출하는 곳만 삭제**. 수동 버튼은 정상 동작 유지.

## 4. 수용 기준

### 4-1. Greppable
```
# factoryLoop가 더 이상 captureDataset/runCycle을 부르지 않음
awk '/async function factoryLoop/,/^  }/' frontend/src/components/SimulationView.jsx | grep -c "captureDataset\|runCycle"   # 0
# factoryLoop가 클래스 순회
awk '/async function factoryLoop/,/^  }/' frontend/src/components/SimulationView.jsx | grep -c "classTrain\|classValidate\|selectedClasses"  # ≥1
# captureDataset는 수동 버튼용으로 잔존
grep -c "onClick={() => captureDataset" frontend/src/components/SimulationView.jsx   # ≥1
```

### 4-2. 회귀
```
grep -c "waitTrainingDone\|armStall\|loopRef" frontend/src/components/SimulationView.jsx   # 하트비트·루프 제어 보존
grep -c "factoryGroupRef\|GLBridge" frontend/src/components/SimulationView.jsx              # 캡처 가드·카메라 보존
```
- `npm run build`(Node20) 무에러.

### 4-3. 런타임 (당신 — 핵심)
- "자동 순환 시작" → **카메라가 더 이상 와리가리/버벅이지 않음**. 대신 선택 클래스가 순차로 학습→판정되며 라인 escape·FAT가 갱신.
- 수동 "데이터셋 생성" 버튼은 여전히 동작(그건 캡처라 잠깐 카메라 고정은 정상).

## 5. 검증 (내가 수행)
재clone → 4-1(factoryLoop에 capture 0·클래스 순회 있음·수동버튼 잔존), 4-2 회귀. 실제 부드러움은 당신 런타임.

## 6. 커밋
- main 직접. 메시지: `fix(loop): autocycle runs per-class pipeline instead of camera-hijacking capture (stops buffering)`

## 7. 주의
- `setActiveClass`/`setCycle`이 없으면 그 줄은 생략 가능(②에서 도입). 핵심은 **captureDataset를 루프에서 빼는 것**.
- 자동순환이 이제 *진짜 학습/판정*이라 느림(클래스당 수십 초~분) — 정상. 버퍼링(카메라 점프)과는 다름.
- 수동 캡처 버튼은 유지 — 합성 데이터가 필요할 때만.
