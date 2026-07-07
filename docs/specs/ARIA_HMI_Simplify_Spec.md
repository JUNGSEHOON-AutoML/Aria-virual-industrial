# ARIA HMI 간결화 · 정리 명세 (Operator/Expert 분리, rparak UX 참고)

> **목표** — 일반 사용자도 한눈에 읽도록 HMI를 간결화한다.
> (1) 레거시 탭 제거 → **트윈 HMI 단일 화면**, (2) **Operator(기본)/Expert 모드**로 점진적 공개,
> (3) 핵심 KPI만 크게, 나머지는 접기, (4) 모바일/태블릿 반응형.
>
> **rparak 참고 범위(정직)** — rparak/Unity3D_Robotics_Overview는 Unity·로봇 트윈(MIT)이라
> 코드/로봇 내용은 가져오지 않는다. **UX 철학만**: "3D + 작고 집중된 컨트롤 패널", 모바일/태블릿/PC에서
> 일반 사용자용, 정보 과잉 금지. (realvirtual AGPL과 달리 MIT지만, 스택이 Unity라 이식 불가 → 참고만.)
>
> **재작성 금지** — 슬롯·signalStore·viewport·API매핑은 유지. "기본 노출 슬롯 + 모드 플래그"만 바꾼다.

---

## 1. 변경 1 — 레거시 탭 제거 (즉시)
- 상단 네비의 **검사 / 시뮬레이션 / 검사노드** 및 `LEGACY` 라벨 **삭제**.
- **트윈 HMI**만 남긴다. 단일 화면이므로 탭 바 자체를 없애고 좌측 타이틀(`ARIA · DIGITAL TWIN`)만 유지.
- 해당 레거시 라우트/컴포넌트도 제거(이전 M5의 "구 UI 삭제"를 여기서 완결).

---

## 2. 변경 2 — Operator(기본) / Expert 모드 (점진적 공개)
상단에 모드 토글 **[운영 | 전문가]** 추가. 기본 = **운영**.

| 영역 | Operator(기본) | Expert(토글 시 추가) |
|---|---|---|
| KPI | **4개 핵심**: STATE · YIELD · OK/NG · VERDICT(PASS/FAIL) | + TACT · ACK max · QUEUE · DROP · FAT (진단) |
| 좌측 | (숨김) | HIERARCHY 트리(Plant→Line→Station) |
| 중앙 | **3D 뷰(크게, 주연)** | 동일 |
| 우측 | 현재 검사결과: verdict + 부품 썸네일 + heatmap (간결) | + detector 상세(score/bbox), escape율 등 |
| 하단 | **간이 알람 티커**(최근 3건 NG) | 전체 ALARMS 리스트 + LIVE 지연 ECharts |
| 액션 | 노드 가동/정지 · **긴급 정지**(항상) | + MOCK/PATCHCORE/COMBINED · 클래스 스캔 |

> 원칙: 운영자는 "지금 잘 돌고 있나 / OK·NG / 문제 있나"만 즉시 본다. 진단·튜닝·세부는 전문가 모드.

---

## 3. 변경 3 — KPI 축소 (8 → 4)
- 운영 KPI 4: **STATE**(RUN/STOP, 색), **YIELD**(%), **OK/NG**(누적), **VERDICT**(현재 라인 PASS/FAIL, 색 크게).
- 나머지(TACT·ACK max·QUEUE·DROP·FAT)는 **전문가 모드 또는 진단 드로어**로 이동.
- 색 규약 단순화: 정상=녹, 경고=황, 불량/정지=적. 숫자 크게, 라벨 작게.

---

## 4. 변경 4 — 반응형 (rparak: 모바일/태블릿/PC)
- 좁은 화면(<900px): 패널을 세로 스택. **3D는 항상 주연**, 우측/하단 패널은 **바텀시트**로 접기.
- 터치 타깃 ≥ 44px. 트리·전체알람·ECharts는 모바일 기본 숨김(전문가에서만).

---

## 5. 유지 (재작성 금지)
- 슬롯 레이아웃·`signalStore`·`apiClient`·API 매핑(`inspector_*`,`class_result`...)·viewport 3D 씬.
- 변경은 **(a) 레거시 탭/라우트 제거, (b) 모드 플래그(`uiMode: operator|expert`)에 따른 슬롯/KPI 노출 제어, (c) 반응형 레이아웃**뿐.

---

## 6. 단계 + 런타임 게이트
- **S1** 레거시 탭/라우트 제거 → 트윈 HMI 단일 화면. 게이트: 상단에 트윈 HMI만.
- **S2** `uiMode` 도입 + Operator 기본(KPI 4 + 간결 우/하단). 게이트: 기본 화면이 한눈에 읽힘.
- **S3** Expert 토글 → 트리·진단 KPI·ECharts·detector 모드 복귀. 게이트: 토글로 콕핏 전체 노출.
- **S4** 반응형. 게이트: 모바일 폭에서 3D 주연 + 패널 바텀시트.
- 검증은 빌드가 아니라 **브라우저 런타임**(기본 화면 간결함·토글 동작·모바일 스택)을 본인이 직접 확인.

---

## 7. Claude Code 미션 브리프 (그대로 전달)
```
목표: 트윈 HMI를 일반 사용자도 읽기 쉽게 간결화. 슬롯/signalStore/viewport/API매핑은 재작성 금지 —
"레거시 제거 + 모드 플래그에 따른 노출 제어 + 반응형"만.

[S1] 상단 레거시 탭(검사/시뮬레이션/검사노드)과 LEGACY 라벨, 해당 라우트/컴포넌트 삭제. '트윈 HMI' 단일 화면.
[S2] uiMode(operator|expert) 도입, 기본 operator. 상단에 [운영|전문가] 토글.
     operator: KPI 4개(STATE·YIELD·OK/NG·VERDICT) + 3D(크게) + 우측 간결(verdict·썸네일·heatmap)
               + 하단 간이 알람 티커(최근 3 NG) + 액션(노드 가동/정지·긴급정지).
     expert(추가 노출): HIERARCHY 트리, 진단 KPI(TACT·ACK·QUEUE·DROP·FAT), 전체 ALARMS,
               LIVE ECharts, detector 모드(MOCK/PATCHCORE/COMBINED), 클래스 스캔, detector 상세.
[S3] KPI 8→4 축소(나머지는 expert/진단 드로어). 색: 정상=녹/경고=황/불량·정지=적. 숫자 크게.
[S4] 반응형: <900px 세로 스택, 3D 주연, 우/하단 바텀시트, 터치 ≥44px.
[DON'T] 슬롯/signalStore/viewport/3D 재작성 금지. 새 엔드포인트 금지. rparak/realvirtual 코드·에셋 복사 금지.
[DONE WHEN] 트윈 HMI 단일화면 + operator 기본이 한눈에 읽힘 + expert 토글로 콕핏 복귀 + 모바일 스택.
            (브라우저 런타임으로 확인, 빌드 아님)
```

## 8. DO / DON'T
- ✅ 레거시 제거 · Operator 기본 · 점진적 공개 · 반응형 · 색/크기 단순화.
- ⛔ 슬롯/signalStore/viewport 재작성, 새 엔드포인트, rparak(Unity·로봇)·realvirtual(AGPL) 코드/에셋 복사,
   로봇 기구학 방향으로의 이탈.
