"""ARIA API — 모듈형 FastAPI 백엔드 (구 monolithic app.py 대체, :8200).

ML 로직은 기존 `aria/` 패키지를 그대로 재사용한다(재작성 없음).
server/ 는 깨끗한 HTTP/WS 글루 레이어:
- config: 경로·포트·CORS
- ws: 단일 WebSocket 신호 채널(ConnectionManager)
- routers/: 도메인별 라우터(inspector, sim, class, analyze, state ...)
- app: create_app() 조립

실행: `uvicorn server.app:app --host 0.0.0.0 --port 8200`
"""
