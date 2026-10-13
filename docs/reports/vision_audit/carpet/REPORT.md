# carpet 비전 분석

P1 저장 점수·맵을 CPU로 분석했다. 새 추론·임계값 변경·테스트 GT 기반 튜닝은 없다. 모델별 7개 분석 항목과 갤러리는 아래에 있다.

- [coreset](coreset/REPORT.md)
- [ccifps](ccifps/REPORT.md)
- [random_same_k](random_same_k/REPORT.md)

## 모델 간 판정 차이
6개 이미지. 모든 점수·임계값·판정은 CSV 원값이다.
|이미지|coreset 점수/판정|ccifps 점수/판정|random_same_k 점수/판정|
|---|---|---|---|
|carpet/test/color/002.png|0.11224192380905151/OK|0.10400509834289551/OK|0.11115634441375732/NG|
|carpet/test/color/005.png|0.11254876852035522/OK|0.11355072259902954/NG|0.11254870891571045/NG|
|carpet/test/color/014.png|0.10710763931274414/OK|0.11041438579559326/NG|0.11122399568557739/NG|
|carpet/test/good/009.png|0.12214356660842896/NG|0.11435413360595703/NG|0.10938328504562378/OK|
|carpet/test/good/019.png|0.08569598197937012/OK|0.0959547758102417/OK|0.11041009426116943/NG|
|carpet/test/metal_contamination/011.png|0.12130743265151978/NG|0.12466806173324585/NG|0.10407507419586182/OK|

화면은 이 폴더 report.json의 동일 바이트를 읽는다. 원본·히트맵·GT 그림은 로컬 전용이며 Git에 포함하지 않는다.
