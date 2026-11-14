import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies mirror the nginx routes used in Docker.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api/portal': { target: 'http://localhost:8000', rewrite: p => p.replace(/^\/api\/portal/, '') },
      '/api/engine': { target: 'http://localhost:8100', rewrite: p => p.replace(/^\/api\/engine/, '') },
      '/api/gateway': { target: 'http://localhost:9000', rewrite: p => p.replace(/^\/api\/gateway/, '') },
    },
  },
})
