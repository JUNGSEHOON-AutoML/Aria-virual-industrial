# bottle 비전 분석

P1 저장 점수·맵을 CPU로 분석했다. 새 추론·임계값 변경·테스트 GT 기반 튜닝은 없다. 모델별 7개 분석 항목과 갤러리는 아래에 있다.

- [coreset](coreset/REPORT.md)
- [ccifps](ccifps/REPORT.md)
- [random_same_k](random_same_k/REPORT.md)

## 모델 간 판정 차이
1개 이미지. 모든 점수·임계값·판정은 CSV 원값이다.
|이미지|coreset 점수/판정|ccifps 점수/판정|random_same_k 점수/판정|
|---|---|---|---|
|bottle/test/good/001.png|0.07678711414337158/NG|0.10078614950180054/OK|0.08471459150314331/OK|

화면은 이 폴더 report.json의 동일 바이트를 읽는다. 원본·히트맵·GT 그림은 로컬 전용이며 Git에 포함하지 않는다.
