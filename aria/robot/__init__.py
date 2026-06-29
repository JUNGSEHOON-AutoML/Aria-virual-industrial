"""ARIA 로봇 학습 서브시스템 (격리 추가 — 이상탐지 파이프라인 무변경).

설계 방법론: docs/specs/robot_arm_learning_env_methodology.md
- env/     : MuJoCo 물리 환경 (진실 소스). Three.js는 모니터 뷰.
- (후속) teleop/ recorder/ policy/ rollout/

R-1 단계: env (씬 정의 + reset/step + 도메인 랜덤화)만 포함.
"""
