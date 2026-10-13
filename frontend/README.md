
기본 화면은 3개 공장을 보여 주는 **캠퍼스**입니다. 지붕 또는 공장 간판·상단 홀 선택·미니맵을 누르면 홀 내부 3개 모델 레인이 열립니다. 아래 **재생**을 누르면 같은 sim 시계로 저장된 부품·NG·B 재검사 대기열을 재생합니다. 상단 **캠퍼스**로 돌아옵니다. 기존 단일 실행 화면은 `cnotta.html?view=line` 또는 **단일 실행** 링크로 엽니다. 운영(Live)은 다음 L2 단계이며 현재 화면은 저장 실행 Replay입니다.

배치는 `frontend/src/campus/campus.layout.json`에서 변경합니다. 로고 경로는 `frontend/public/brand/identity.json` 한 곳에 정의되어 있습니다. 원본이 도착하면 같은 brand 폴더의 `cnotta-mark.svg`·`cnotta-wordmark.svg`를 윤곽선 SVG(fill path, viewBox 포함)로 교체하면 지붕의 두 입체 로고와 상단·입구 마크가 함께 반영됩니다. 교체 후 `tools/gates/capture_campus.py`와 `python -m tools.gates.m7`로 글자 높이·가독성을 재검증합니다.

캠퍼스는 클래스·모델·seed 0·inline·0.5 m/s·profile이 일치하는 완료 파일만 읽습니다. 본 실험이 진행 중이어도 `complete.json`이 있는 개별 실행을 기존 hash 검증 후 읽을 수 있습니다. 없는 레인은 **완료 대기**이며 30초마다 목록을 다시 확인합니다. 부분 실행 공개는 최종 요약·95% CI 검증 완료를 뜻하지 않습니다.
