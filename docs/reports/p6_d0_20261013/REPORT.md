# P6 D0 룩데브 — 사용자 승인 대기

`dt-wip-20261013`의 `204cdae`에서 `dt-dashboard-p6`를 만들고 D0 정적 장면만 구현했다. 실험 프로세스, GPU 설정, DES 엔진·평가기·원자료는 수정하지 않았다. D1 재생 API와 D2–D4 기능은 구현하지 않았다.

## 산출물

- 독립 진입점: `frontend/d0.html`, `frontend/src/d0/`.
- 장면: 반쪽 벽 검사동, 도로·트럭·나무 8그루, 투입·비전 부스·분류기·OK/NG/HOLD 레인, 로봇 셀, 팔레트, 오프라인 재검사 랙·작업대·작업자·빈.
- 기존 CAD `dims.json`을 직접 import해 컨베이어·부스·분류기 치수를 적용했다. M0609는 기존 URDF에서 계산한 고정 자세와 기존 Collada 형상을 사용한다. 제어 동작이나 새 실험은 실행하지 않는다.
- 지정 팔레트, MeshStandardMaterial(roughness 0.85 / metalness 0), RoundedBox, 정사영 45°/내려다보기 35°, 회전 ±20°, 지정 광원과 ContactShadows, ACES Filmic(exposure 1.25)을 적용했다.
- city 프리셋과 동일한 Potsdamer Platz 1K HDRI를 로컬에서 읽는다. Three r160에서는 각 재질의 envMapIntensity 0.25도 명시했다. Pretendard는 로컬 WOFF2를 쓴다.
- 글꼴·HDRI는 내려받기 전에 라이선스를 확인했다. 출처·SHA-256·라이선스는 `assets/third_party/`와 배포용 `frontend/public/d0/`에 보존한다. [Pretendard OFL](https://github.com/orioncactus/pretendard/blob/v1.3.9/LICENSE), [Poly Haven CC0](https://polyhaven.com/license).

레퍼런스 6장은 모두 720×404 PNG다. 원본과 비교 이미지 전체는 `.gitignore`의 `/docs/specs/assets/p6_ref/` 아래에만 보관한다. 공개 보고서에는 이미지를 삽입하지 않는다. Git 추적 파일 0개를 확인했다.

내부 비교 이미지(각 오른쪽 ARIA 화면은 1440×900, 왼쪽은 ref_01·ref_03):

- `docs/specs/assets/p6_ref/d0_review/overview-compare.png`
- `docs/specs/assets/p6_ref/d0_review/line-compare.png`
- `docs/specs/assets/p6_ref/d0_review/reinspection-compare.png`

## 검증과 게이트

| 항목 | 결과 |
|---|---|
| CPU production build | 통과. 3D 진입 번들이 500 kB를 넘는 Vite 경고는 남음 |
| 세 시점 1440×900 / 글꼴 로드 | 통과 |
| 브라우저 예외 / HTTP 오류 / 백엔드 API 요청 | 각각 0 |
| 접지 어셈블리 41개 월드 바운딩박스 | 바닥과 2cm 이상 떨어지거나 잠긴 어셈블리 0 |
| 장면 정지 | 고정 배치. DES·판정·대기열 생성 타이머와 난수 없음 |
| 실제 GPU 화풍 / FPS 확인 | 미실시 |
| 사용자 화풍 승인 | 대기 |
| D1 진입 | 하지 않음 |

렌더러는 ANGLE SwiftShader다. 이 캡처는 구조·배치 검토용이며 실제 GPU 승인 근거가 아니다. 접지 검사는 어셈블리 AABB 검사로, 로봇 각 링크의 연결성·모든 세부 부품의 지지·충돌·물리 안전성을 보증하지 않는다. 소품 개수와 자세는 룩데브용 고정 예시이며 측정 결과나 재검사 대기열 수치가 아니다. 화면에도 데이터 연결 전임을 표시했다.

## 실행과 검토

현재 로컬 미리보기: `http://127.0.0.1:5276/d0.html`.

서버 포트 5276을 사용자 PC의 5276으로 포워딩한 뒤 Chrome에서 같은 URL을 연다. 실제 GPU 사용 여부를 확인하고 뷰포트 1440×900에서 전체 보기·검사 라인·재검사 구역 버튼으로 확인한다. 화풍과 객체 접지를 확인한 사용자 승인 전에는 D1로 넘어가지 않는다(명세 7절).

```sh
cd /userHome/userhome4/sehoon/Aria-virual-industrial-main/frontend
/userHome/userhome4/sehoon/miniconda3/envs/aria/bin/node node_modules/vite/bin/vite.js --config vite.d0.config.js
```

CPU 빌드:

```sh
cd /userHome/userhome4/sehoon/Aria-virual-industrial-main/frontend
/userHome/userhome4/sehoon/miniconda3/envs/aria/bin/node node_modules/vite/bin/vite.js build --config vite.d0.config.js
```

산출 디렉터리는 `/tmp/aria-p6-d0-dist`다. 기존 frontend production output을 덮어쓰지 않는다. 서버의 기본 `/usr/bin/node`는 구버전이므로 위의 기존 aria 환경 Node를 사용한다.

소프트웨어 미리보기 재캡처(기존 httpx/websockets와 Chrome 사용, 새 설치 없음):

```sh
cd /userHome/userhome4/sehoon/Aria-virual-industrial-main
/userHome/userhome4/sehoon/miniconda3/envs/aria/bin/python tools/capture_p6_d0.py
```

실험 진행 상태는 기존 `docs/validation/aria_dt_full_policy_a_20261013/progress.json`에서 확인한다. 대시보드 구현 완료는 본 실험 완료를 뜻하지 않는다.
