# ARIA HMI 고도화 명세 — Gemini 이상안 반영 (가독성 · 3D 명확성 · 행동 유도)

> 목표: 현재 Operator HMI를 Gemini 이상안 수준으로 끌어올린다 — (1) 점수 비교 게이지, (2) KPI 위계,
> (3) 3D 명확성, (4) 행동 유도 알람. **슬롯·signalStore·viewport 구조는 유지**(고도화이지 재작성 아님).

> ## ⚠️ 최우선 정정 — Anomaly Score 로직 (절대 뒤집지 말 것)
> PatchCore 점수는 **anomaly score = 낮을수록 정상**(정상 패치와의 거리). 따라서 **OK if score < τ, NG if score ≥ τ.**
> → 화면의 `0.418 < 0.500 = OK`는 **정답이며 버그 아님.** Gemini가 "0.418은 NG여야 한다"고 한 건 *오독*.
> **verdict 계산식은 변경 금지.** 바꾸는 것은 *시각화*뿐(아래 §1 게이지로 "왜 OK인지"를 보이게).

---

## 0. Gemini 분석 채택/정정 표
| 항목 | Gemini 제안 | 우리 처리 |
|---|---|---|
| 점수 모순 | "0.418은 NG여야" | ❌ 오독. 로직 유지. ✅ **점수 비교 게이지**로 가독성만 해결 |
| 수율 위계 | YIELD 최우선·맥락 | ✅ 채택 |
| 카운트 시각화 | OK/NG 게이지 | ✅ 채택 |
| 3D 명확성 | 밝기↑·설비 상호작용·NG 강조 | ✅ 채택(경량 범위) |
| 행동 유도 알람 | 오류+해결링크·대시보드 | ✅ 채택 |

---

## 1. 개선 ① 점수 비교 게이지 (핵심 — 가독성)
검사결과 패널에 추가:
- 가로 게이지: 범위 `[0, max(1.0, 2τ)]`. **녹색 OK 구간 `[0, τ)` / 적색 NG 구간 `[τ, max]`**.
- 현재 점수 마커 + 수치(0.418), τ 눈금(0.500) 표시.
- 라벨: **"Anomaly Score — 낮을수록 정상(정상 패치와의 거리)"**. → "왜 0.418이 OK인지" 즉시 이해.
- verdict 색은 게이지 구간 색과 일치(OK=녹, NG=적).

---

## 2. 개선 ② KPI 위계
- **YIELD 최우선**: 가장 크게 + 아래 맥락 한 줄 **"목표 90% 대비 -40%p (경고)"**, 목표 미달이면 경고색(황/적).
- **OK/NG 비율 게이지**: 숫자 나열 대신 비율 바(녹 OK / 적 NG) + 수치 병기.
- 나머지 진단 KPI(TACT·ACK·QUEUE·DROP)는 기존대로 Expert/진단 드로어.
- 위계 원칙: YIELD > VERDICT > OK/NG > STATE 순으로 시각 강조.

---

## 3. 개선 ③ 3D 명확성 (경량 범위)
- **조명 향상**: ambient/hemisphere/key 상향 → 설비 식별 가능(현 다크 대비 밝게). PLANNER 톤을 기본 가깝게.
- **설비 상호작용 시각화(투명 지오메트리)**:
  - 비전 카메라 **초점 콘**(반투명 cone/frustum)으로 검사 FOV 표시.
  - (로봇 프롭 사용 시) **작업영역 엔벨로프**(반투명 반구/토러스)로 가동 반경 표시.
- **OK/NG 부품 발광**: OK=연녹 발광, **NG=강한 적색 발광 + 점멸**, NG 발생 위치에 마커/링.
- ⚠️ 로봇 팔은 **경량 애니메이션 프롭 + 엔벨로프 시각화**일 뿐 **키네매틱스/물리 트윈 아님**(URDF·IK·충돌솔버 금지). 이상안 룩만 충족.

---

## 4. 개선 ④ 행동 유도 알람 (Actionable)
- 알람을 `{part_id, error_code, label, action}`으로 구조화. 단순 ID 나열 → **오류명 + 조치 링크**.
  - 예: `P111379 · 카메라 교정 오류 [해결 매뉴얼]`, `P111377 · 로봇 동기화 오류 [재시작]`.
- **error_code → action 매핑 테이블**:
  | code | label | action |
  |---|---|---|
  | CAM_CALIB | 카메라 교정 오류 | manual(/docs/cam_calib) |
  | ROBOT_SYNC | 로봇 동기화 오류 | restart(/api/inspector/restart) |
  | NG_SCORE | 이상 검출 | open detail(heatmap) |
- **[문제 해결 대시보드 열기]** 버튼: 활성 결함 목록 + 권장 조치를 모은 드로어/모달.
- 소스: `diagnostic_result`/`inspector_result`에서 code 도출. code가 아직 없으면 **클라이언트 매핑 테이블로 임시** 처리(백엔드 code 확장은 별도).

---

## 5. 데이터 바인딩 (실제 타입만 — 유령 엔드포인트 금지)
| 표출 | 소스 |
|---|---|
| score/verdict/part_id/PatchCore/게이지 | `inspector_result` |
| YIELD·OK/NG 카운트/게이지 | 누적(`inspector_result`)·`class_result` 파생 |
| 알람·error_code | `inspector_result`(NG)·`diagnostic_result` |
| 조치(restart/recalib/노드정지) | `/api/inspector|action` |
| 해결 매뉴얼 | 정적 docs 링크 |
> 게이지·초점콘·엔벨로프·발광은 **표현 레이어**(데이터 가공 아님).

---

## 6. 유지 / 금지
**유지**: 슬롯·signalStore·viewport 구조, Operator/Expert 모드, API 매핑.
**금지**: ⛔ **verdict 로직 변경(anomaly score 뒤집기)**, 키네매틱스/물리 엔진, 새 엔드포인트,
realvirtual(AGPL)·rparak(Unity) 코드/에셋 복사, 로봇 기구학 트윈으로의 이탈.

---

## 7. 단계 + 런타임 게이트
- **G1 점수 게이지** — 녹/적 구간 + 마커 + "낮을수록 정상" 라벨. 게이트: 0.418이 녹색 OK 구간에 표시.
- **G2 KPI 위계** — YIELD 최대+맥락경고, OK/NG 비율 게이지. 게이트: 한눈에 수율 위기 인지.
- **G3 3D 명확성** — 밝기↑ + 초점콘 + OK/NG 발광 + NG 마커. 게이트: NG 부품 위치 즉시 보임.
- **G4 행동 알람** — 오류명+조치링크 + 문제해결 대시보드. 게이트: 알람에서 바로 조치 실행/문서 이동.
- 시각 게이트는 **본인 브라우저에서 직접 확인** 후 done(빌드 아님).

---

## 8. Claude Code 미션 브리프 (그대로 전달)
```
목표: Operator HMI를 Gemini 이상안 수준으로 고도화. 슬롯/signalStore/viewport 구조 유지(재작성 금지).

★최우선: PatchCore 점수는 anomaly score(낮을수록 정상). OK if score<τ. 0.418<0.5=OK는 정답이니
verdict 로직 절대 변경 금지. 아래는 '표현'만 바꾼다.

[G1] 검사결과 패널에 점수 비교 게이지: 녹 OK구간[0,τ)/적 NG구간[τ,max], 현재점수 마커+수치, τ눈금,
     라벨 "Anomaly Score — 낮을수록 정상". 0.418이 녹색 구간에 보이게.
[G2] KPI 위계: YIELD를 가장 크게 + "목표 90% 대비 -40%p(경고)" 맥락 + 미달시 경고색. OK/NG는 비율 게이지바.
[G3] 3D 명확성: 조명 상향(설비 식별), 비전 카메라 초점 콘(반투명), OK=연녹/NG=적색 발광+점멸+NG마커.
     (로봇은 경량 프롭+작업영역 반투명 엔벨로프만 — 키네매틱스/물리/URDF 금지.)
[G4] 행동 알람: 알람을 {part_id,error_code,label,action}로 구조화, 오류명+조치링크(해결매뉴얼/재시작).
     error_code→action 매핑 테이블. [문제 해결 대시보드 열기] 드로어(활성결함+권장조치). 
     code 소스=diagnostic_result/inspector_result, 없으면 클라이언트 매핑 임시.
[바인딩] 실제 /ws/chat 타입만(inspector_result/class_result/diagnostic_result) + /api/inspector|action. 새 ws 금지.
[DONE] G1~G4 브라우저 런타임 확인(점수게이지·수율위계·NG가시성·조치실행). 빌드 아님.
```

## 9. DO / DON'T
- ✅ 점수 게이지·YIELD 위계·3D 밝기/발광/초점콘·행동 알람. 표현 레이어 개선.
- ⛔ verdict 로직(anomaly score) 변경, 키네매틱스/물리, 새 엔드포인트, AGPL/Unity 코드 복사, 로봇 트윈 이탈.
