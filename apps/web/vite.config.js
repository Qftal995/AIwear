import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  /** 后端 API 地址，开发时将所有 /api 请求代理到此地址（可在 .env.development 中设置 PROXY_TARGET） */
  const proxyTarget = env.PROXY_TARGET || 'http://localhost:8081'
  const pythonTarget = env.VITE_PYTHON_TARGET || 'http://localhost:5001'

  return {
    plugins: [vue()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      open: true,
      proxy: {
        // Python ai-service endpoints (order matters: specific before general)
        '/api/mcp':       { target: pythonTarget, changeOrigin: true },
        '/api/rag':       { target: pythonTarget, changeOrigin: true },
        '/api/traces':    { target: pythonTarget, changeOrigin: true },
        '/api/chat':      { target: pythonTarget, changeOrigin: true },
        '/api/health':    { target: pythonTarget, changeOrigin: true },
        '/api/session-stats': { target: pythonTarget, changeOrigin: true },
        '/api/tool':      { target: pythonTarget, changeOrigin: true },
        '/api/wardrobe':  { target: pythonTarget, changeOrigin: true },
        '/api/validate-image':  { target: pythonTarget, changeOrigin: true },
        '/api/upload-image':    { target: pythonTarget, changeOrigin: true },
        '/api/search-image':    { target: pythonTarget, changeOrigin: true },
        // Java backend (catch-all)
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
  }
})

