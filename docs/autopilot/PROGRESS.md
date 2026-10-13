# PROGRESS

마일스톤 | 상태 | 게이트 | 다음 작업
--- | --- | --- | ---
M0 | 완료 | gates/m0.json | 통과; M1 진행
M1 | 자동 게이트 통과 · 실제 GPU 미확인 | gates/m1.json | M2 진행; 화풍 피드백은 토큰 범위
M2 | 완료 | gates/m2.json | 9 API tests·재생 게이트 통과; M3 진행
L1 | 완료 (CPU) | gates/l1.json | 9개 리포트·CSV/화면 일치·176 tests·골든 diff 0
V1 | 대기 | — | L1 다음·L2 이전, 4h; CPU·허용 이미지·라이선스 조건 적용
V2 | 대기 (입력 범위 충돌) | — | 4h; 별도 3D-AD 입력을 자동 추가하지 않음
V3 | 대기 (입력 범위 충돌) | — | 3h; 정상 학습 이미지를 자동 추가하지 않음
L2 | 대기 | — | 기존 라이브 DES·검사·로봇 연결
L3 | 대기 | — | L2 이후 기존 IndustrialAgent/MCP에 A1–A5 연결
L4 | 대기 | — | L3 이후 기존 순찰 경로에 4족 모델 연결
M3 | 완료 | gates/m3.json | 원시 점수·판정 일치, 검색 선택·장식 핸들러 0; M4 진행
M4 | 완료 | gates/m4.json | KPI 3종 일치·대기 0/2/2564 일치·설비 가림 0%; M5 확인
M5 | 실험 대기 (구현·404 게이트 완료) | gates/m5.json | A 1449/2970; 완료 후 실데이터 REPORT 대조
M6 | 완료 (기존 Replay 파일럿) | gates/m6.json | 운영 연결 뒤 재검증
M7 | 대기 | — | 9절 캠퍼스 맵, L1–L4·M1–M6 이후

M2 후속 동작 가시성 수정 완료: `gates/motion.json` 통과. 같은 생존 부품 7개의 위치 변화·로봇 회전·일시정지·10× 재고 보존·7개 단위 assertion·콘솔 오류 0 확인. CPU 빌드 성공, 골든 diff 0.

M1 Site 후속 준비: 9절 원문 병합 완료. origin=[x,z]·rotation=yaw·lanes=모델 ID 목록 경계 및 기존 컨베이어 형상 배열 분리; gates/site.json 7개 검사·CPU 빌드 통과.
M7: M1→M6 이후 대기, 예산 4h. 범위·게이트는 BuildSpec 9절/9.6절. 이번 변경에서 캠퍼스 구현은 착수하지 않음.

LiveOps 확장 순서: M1→M2→L1→V1→V2→V3→L2→L3→L4→M3→M4→M5→M6→M7. 기존 M3–M6 산출물은 보존하며 운영 모드 연결 후 재검증한다. L1 CPU 분석 완료; L2/L3/L4는 아직 미구현이며 기존 기능 재사용 조사 후 순서대로 연결.

결함 3D 명세 병합 완료: BuildSpec 11절·V1–V3 표/예산 등록. 구현·모델 다운로드는 미착수. 본 실험 종료 전 CPU만, L1 오류/판정 차이 이미지에 한정, 코드·가중치 개별 라이선스 확인·assets/third_party 기록 후에만 다운로드, Hunyuan3D 금지.
