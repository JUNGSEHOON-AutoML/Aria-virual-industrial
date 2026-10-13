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
