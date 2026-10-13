import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5276, strictPort: true, fs: { allow: ['..'] } },
  build: { outDir: '/tmp/aria-p6-d0-dist', emptyOutDir: false, rollupOptions: { input: 'd0.html' } },
})
