import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Docker 컨테이너(172.20.0.2)에서 호스트 백엔드(8000)에 접근
// Linux Docker: host.docker.internal 미동작 → 게이트웨이 IP 직접 사용
// BACKEND_HOST 환경변수로 오버라이드 가능
const BACKEND_HOST = process.env.BACKEND_HOST || 'backend'
const BACKEND_PORT = process.env.BACKEND_PORT || '8080'
const BACKEND_URL = `http://${BACKEND_HOST}:${BACKEND_PORT}`
const WS_URL = `ws://${BACKEND_HOST}:${BACKEND_PORT}`

export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: BACKEND_URL,
        changeOrigin: true,
        proxyTimeout: 600_000,  // 10분 — VLM 추론 대기
        timeout: 600_000,
      },
      '/ws': {
        target: WS_URL,
        ws: true,
        proxyTimeout: 600_000,
        timeout: 600_000,
      },
      '/static': {
        target: BACKEND_URL,
        changeOrigin: true,
        proxyTimeout: 60_000,
        timeout: 60_000,
      },
      '/outputs': {
        target: BACKEND_URL,
        changeOrigin: true,
        proxyTimeout: 60_000,
        timeout: 60_000,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
