import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// 开发期将 /api 代理到 FastAPI（默认 8000），前后端联调无需跨域配置。
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    // 本沙箱（WorkBuddy）会把 Node 的 fs.rmSync 劫持成「安全删除」二进制，
    // 该二进制不稳定地超时/失败，导致 Vite 清空 dist 这一步必崩。
    // 关闭自动清空后构建可正常完成；部署到无此拦截的环境时可改回 true。
    emptyOutDir: false,
  },
})
