/** 前端构建配置：接入 Vue、Tailwind CSS，并统一路径别名与开发代理。 */
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  // 统一源码根目录别名，避免页面层级变化导致相对路径逐级增长。
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000' },
  },
})
