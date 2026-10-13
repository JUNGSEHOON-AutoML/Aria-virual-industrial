# PROGRESS

마일스톤 | 상태 | 게이트 | 다음 작업
--- | --- | --- | ---
M0 | 완료 | gates/m0.json | 통과; M1 진행
M1 | 자동 게이트 통과 · 실제 GPU 미확인 | gates/m1.json | M2 진행; 화풍 피드백은 토큰 범위
M2 | 완료 | gates/m2.json | 9 API tests·재생 게이트 통과; M3 진행
M3 | 완료 | gates/m3.json | 원시 점수·판정 일치, 검색 선택·장식 핸들러 0; M4 진행
M4 | 완료 | gates/m4.json | KPI 3종 일치·대기 0/2/2564 일치·설비 가림 0%; M5 확인
M5 | 실험 대기 (구현·404 게이트 완료) | gates/m5.json | A 1449/2970; 완료 후 실데이터 REPORT 대조
M6 | 완료 (파일럿) | gates/m6.json | 새 클론·즉시 재시작·163 tests·golden diff 0·60초 녹화; 최종 데모 확인

M2 후속 동작 가시성 수정 완료: `gates/motion.json` 통과. 같은 생존 부품 7개의 위치 변화·로봇 회전·일시정지·10× 재고 보존·7개 단위 assertion·콘솔 오류 0 확인. CPU 빌드 성공, 골든 diff 0.

M1 Site 후속 준비: 9절 원문 병합 완료. origin=[x,z]·rotation=yaw·lanes=모델 ID 목록 경계 및 기존 컨베이어 형상 배열 분리; gates/site.json 7개 검사·CPU 빌드 통과.
M7: M1→M6 이후 대기, 예산 4h. 범위·게이트는 BuildSpec 9절/9.6절. 이번 변경에서 캠퍼스 구현은 착수하지 않음.
