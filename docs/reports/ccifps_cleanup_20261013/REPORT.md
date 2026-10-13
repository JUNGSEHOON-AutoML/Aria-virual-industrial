# CCIFPS-AutoML 저장 공간 정리 — 2026-10-13

사용자의 명시적 승인에 따라 필수 파일을 보존하고 로컬 실험 원자료를 삭제했다. GitHub 백업을 확인하지 못한 원자료도 삭제할 수 있다는 추가 승인을 받은 뒤 수행했다.

- 삭제: 645개 파일, 56,498,463,147 bytes (56.50 GB).
- 파일시스템 가용 공간: 34.25 GB → 90.75 GB. 실행 중인 시뮬레이션의 쓰기 때문에 삭제 용량과 가용 공간 증가에는 차이가 있다.
- 보존: 19,734개 파일. 데이터, Git 이력과 미커밋 소스, 설정·보고서, ARIA가 사용하는 공식 특징 캐시 전체 및 참조 소스를 포함한다. 나머지 작은 실험 파일도 보존했다.
- 보존 위치: `/userHome/userhome4/sehoon/Aria-virual-industrial-main/archive/ccifps_preserved_20261013`.
- 기존 `/userHome/userhome4/sehoon/CCIFPS-AutoML` 경로는 위 보존 위치를 가리키는 심볼릭 링크다. ARIA `data` 링크도 정상이다.
- 원자료가 제거된 실험은 완전한 재실행 증거로 간주하면 안 된다. 보존 폴더의 `EXPERIMENT_RAW_DATA_REMOVED.txt`에 표시했다.

## 검증

이동 전후 보존 파일 전체의 inode·크기·수정 시각·모드를 대조했다. Git status가 변경되지 않았으며, 필수 파일 경로와 15개 클래스의 특징 캐시 존재, 공식 소스 SHA-256 일치를 확인했다. 소스 코드는 수정하지 않았다. 실행 중인 DES 입력과 설정도 수정하지 않았다.

`deleted_files.json`에는 삭제한 각 파일의 원래 상대 경로·크기·삭제 전 SHA-256이 있다. `result.json`은 삭제 결과, `verification.json`은 보존 검증 결과다. 보존 원본에는 비공개 로컬 설정이 포함될 수 있으므로 archive는 기존 정책대로 Git 추적 대상에서 제외한다.

본 실행은 `docs/validation/aria_dt_full_policy_a_20261013/progress.json`에 진행 상태를 기록하며, 완료 후 같은 디렉터리에 `REPORT.md`를 생성한다. 이번 정리 완료는 본 실행 완료를 뜻하지 않는다.
