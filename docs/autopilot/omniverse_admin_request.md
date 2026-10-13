# Omniverse 관리자 요청서 — O2 보류

측정: 2026-10-13T08:22:10.200193+00:00

O0 환경 조건 실패: driver, unused_rtx, kit_storage, os

항목 | 현재 값 | 필요한 값
--- | --- | ---
OS | Ubuntu 20.04.6 LTS | Ubuntu 22.04 / 24.04
Driver | 550.54.14 | 570.169 / 580.95.05 / 595.58.03; newer is unverified
GPU | 4 RTX candidates; idle check=False | Unoccupied RTX; reserve only after experiment completion
Kit path | /userHome/userhome4/sehoon/Aria-virual-industrial-main/outputs/omniverse/kit: 64.16 GB free | 250 GB free
RAM | 95.61 GiB available | 16 GiB available (conservative)
Display | unset | headless_streaming_deferred_to_O2

## 다른 볼륨 (할당·쓰기·설치하지 않음)

- `/`: 30.86 GB; 250 GB 충족=False; 쓰기 가능=False
- `/boot`: 2.46 GB; 250 GB 충족=False; 쓰기 가능=False
- `/userHome/userhome3`: 964.71 GB; 250 GB 충족=True; 쓰기 가능=False
- `/userHome/userhome2`: 221.69 GB; 250 GB 충족=False; 쓰기 가능=False
- `/userHome/userhome1`: 1039.66 GB; 250 GB 충족=True; 쓰기 가능=False
- `/userHome/userhome4`: 64.16 GB; 250 GB 충족=False; 쓰기 가능=False

공용 서버 드라이버·OS 업그레이드는 다른 사용자 CUDA 작업과 실행 환경에 영향을 준다. 관리자에게 본 실험 및 다른 사용자 작업 종료 후 점검/재부팅 일정을 요청한다. 충분한 용량의 설치·캐시 경로도 관리자가 할당해야 한다.

Codex는 드라이버·CUDA·시스템 패키지·GPU 프로세스를 변경하지 않았으며 Kit/Replicator를 설치하거나 실행하지 않았다. GPU 유휴 관측은 본 실험 완료의 근거가 아니다. O2 진입 전에 O0 전체 재검사 및 본 실험 종료 확인이 필요하다. O1은 독립 CPU 작업으로 진행한다.

기술 요구사항 확인 출처: https://docs.omniverse.nvidia.com/dev-guide/latest/common/technical-requirements.html
