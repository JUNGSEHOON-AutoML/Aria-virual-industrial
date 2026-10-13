# 홈 디렉터리 공간 정리 결과

대상: `/userHome/userhome4/sehoon`. 2026-10-13 사용자 승인 목록만 삭제했다.

- 오래된 pip 캐시: 744개, 2026-08-14 이전 수정 파일. 검사 이후 변경된 파일이 없는지 재확인했다.
- 구버전 VS Code 서버: 5개. 최신 `Stable-04c0d99f4fb0d8afe6ce4f0c58e31e183ac3e4b1`과 현재 활성 프로그램은 보존했다.
- 삭제 전 여유: 28,909,735,936 bytes.
- 삭제 후 여유: 37,157,089,280 bytes.
- 실제 여유 증가: **8,247,353,344 bytes (약 8.247 GB)**.

실험 게이트 필요 여유 36,918,390,180 bytes를 넘었다. 본 실행 직전에 여유 공간을 다시 확인한다. 캐시는 필요 시 다운로드되며 구버전 VS Code 클라이언트로 접속하면 해당 서버를 다시 설치할 수 있다.

연구 결과·모델·데이터·Conda 환경·현재 FreeCAD 런타임은 삭제하지 않았다. `CCIFPS-AutoML/experiments` 약 86.20GB도 보존했다. MVTec 압축파일은 목록 대조만 수행했고 삭제하지 않았다.

정확한 삭제 경로는 `cleanup_result.json`, 승인 전 후보는 `pip_candidates.json`과 `vscode_candidates.json`에 있다. `home-usage-before.txt`는 정리 전 스캔이며 현재 사용량과 다를 수 있다.
