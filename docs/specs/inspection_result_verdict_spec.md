# ARIA 명세서 — 검사 결과 시각화: 큼직한 OK/NG 판정 (for Antigravity)

> "검사 느낌"의 마지막 한 조각. **히트맵은 이미 있다**(InspectionViewer가 `heatmap_url`을 이미지 위에 오버레이, L487-489). 빠진 건 **합격/불합격 선언**이다.
> 이번 슬라이스 = SCAN 결과에 **OK / NG 판정 뱃지**를 부품 이미지 위에 크게 + 히트맵에 라벨.

## 0. 이미 있는 것 (다시 만들지 말 것)

- 백엔드 히트맵 오버레이 생성: `cmdiad_inference.py:298-302` (JET 컬러맵 블렌딩) → `heatmap_path`.
- API 반환: `heatmap_url`(app.py L177). 프론트 오버레이: `InspectionViewer.jsx` L285/338/487-489.
- 점수·임계값·defect location 표시: 이미 있음(L170-189, L250).
**→ 히트맵·점수 파이프라인은 손대지 않는다. OK/NG 판정만 추가한다.**

## 1. 범위 (Scope)

**포함:**
- `InspectionViewer.jsx`에 **OK/NG 판정 뱃지** — 점수 vs 임계값으로 산출, 부품 이미지 위에 크게.
- DIAGNOSTIC REPORT에 판정 한 줄.
- (가벼움) 히트맵 위 "결함 영역" 라벨.

**제외:** 히트맵 생성/추론/모델/학습 변경 — 전부 그대로. 단순 단일 이미지 검사 흐름 유지.

## 2. 변경 대상

| 파일 | 변경 |
|------|------|
| `frontend/src/components/InspectionViewer.jsx` | 판정 산출 + 뱃지(이미지 위) + DIAGNOSTIC 판정 줄 + 히트맵 라벨 |

## 3. 작업 명세 (What)

### 3-A. 판정 산출 (기존 score/threshold 재사용)
기존 `score`, `threshold`, `isContentMode`, `isAnomaly` 근처에 추가:
```jsx
const hasScore   = score != null && !isContentMode            // 실제 추론이 돈 경우만
const isNG       = hasScore && score > threshold
const verdict    = !hasScore ? null : (isNG ? 'NG' : 'OK')
const verdictColor = isNG ? '#f87171' : '#34d399'             // NG=빨강, OK=초록
```
> 일반 이미지(content mode)·미추론 상태에선 `verdict=null` → 뱃지 숨김(억지 판정 금지).

### 3-B. 부품 이미지 위 OK/NG 뱃지 (VISION HUD)
이미지/히트맵을 감싸는 컨테이너(L482 `<img>` 인근, `position:relative`) 안에:
```jsx
{verdict && (
  <div style={{
    position: 'absolute', top: 16, left: '50%', transform: 'translateX(-50%)',
    zIndex: 5, padding: '6px 30px', borderRadius: 10,
    fontFamily: 'monospace', fontSize: 34, fontWeight: 700, letterSpacing: 6,
    color: verdictColor, background: 'rgba(0,0,0,0.55)',
    border: `2px solid ${verdictColor}`, boxShadow: `0 0 26px ${verdictColor}66`,
  }}>
    {verdict}
  </div>
)}
```
> 부모가 `position:relative`인지 확인(아니면 추가). 히트맵 오버레이(`zIndex` 기본)보다 위에 오도록 `zIndex:5`.

### 3-C. DIAGNOSTIC REPORT 판정 줄
점수 블록 인근에:
```jsx
{verdict && (
  <span style={{ fontFamily:'monospace', fontWeight:700, fontSize:14,
                 color: verdictColor, letterSpacing: 2 }}>
    판정: {verdict} {isNG ? '· 결함 감지' : '· 정상'}
  </span>
)}
```

### 3-D. (가벼움) 히트맵 라벨
히트맵 오버레이(L487-489) 근처에 작은 캡션:
```jsx
{heatmapUrl && (
  <span style={{ position:'absolute', bottom:8, left:8, zIndex:5,
    fontFamily:'monospace', fontSize:10, color:'#9aa0aa',
    background:'rgba(0,0,0,0.5)', padding:'2px 6px', borderRadius:4 }}>
    결함 영역 (히트맵)
  </span>
)}
```

## 4. 수용 기준

### 4-1. Greppable
```
grep -n "verdict\|isNG\|'NG'\|'OK'\|verdictColor" frontend/src/components/InspectionViewer.jsx
grep -c "heatmapUrl" frontend/src/components/InspectionViewer.jsx   # 기존 오버레이 보존 >0
```

### 4-2. 빌드
- `npm run build` 무에러 + 빌드 후 8080 반영.

### 4-3. 회귀 가드 (히트맵·파이프라인 보존)
```
grep -c "heatmap_url\|heatmapUrl" frontend/src/components/InspectionViewer.jsx   # 보존
grep -c "applyColorMap\|heatmap_path" cmdiad_inference.py                        # 백엔드 히트맵 보존
grep -c "frontend/dist/index.html" app.py
grep -c "/api/train/upload\|/api/sim/dataset\|get_snapshot" app.py
```

### 4-4. 런타임 (당신 — 비로소 "검사 느낌")
- 검사 탭 → 이미지 업로드 → **SCAN** → 이미지 위에 **큼직한 OK(초록)** 뱃지 + DIAGNOSTIC "판정: OK · 정상".
- **NG + 히트맵을 보려면**: *학습된 모델(memory_bank) + 결함 이미지*로 SCAN → **NG(빨강)** 뱃지 + 결함 영역 히트맵. (SIM-4로 만든 합성 결함 이미지를 쓰면 바로 테스트 가능.)
- Antigravity 녹화: OK 케이스 1장, (가능하면) NG 케이스 1장.

## 5. 검증 절차 (내가 수행)
"푸시 완료" → 재clone → 4-1 grep(판정 로직·뱃지), 4-3 회귀(히트맵 보존). 4-2 빌드·4-4 판정 뱃지는 Antigravity 캡처. 통과 시 — NG 검증 실행(합성 결함으로 escape율) 또는 (B) 시뮬 의미화로.

## 6. 커밋
- 브랜치: `feat/inspection-verdict-badge`
- 메시지(예): `feat(inspection): prominent OK/NG verdict over inspected image (heatmap already wired)`

## 7. 주의
- **히트맵·추론·모델 건드리지 말 것** — 이미 작동. OK/NG 뱃지만 추가.
- content-mode/미추론(score=null)에선 **뱃지 숨김** — 억지 판정 금지.
- 뱃지가 히트맵 위에 보이도록 부모 `position:relative` + `zIndex`.
- 진짜 NG·히트맵은 *학습된 모델 + 결함 이미지*가 있어야 보인다(없으면 OK만). 이건 정상.
