import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 开发环境代理到后端 FastAPI，生产由 Nginx 反向代理
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    target: 'es2018',
    // 路由已懒加载（动态 import）；vendor 三方依赖单独分包，利于长缓存与并行加载
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('lightweight-charts')) return 'charts'
          if (id.includes('axios')) return 'axios'
          if (id.includes('vue') || id.includes('pinia') || id.includes('vue-router')) return 'vue-vendor'
          return undefined
        },
      },
    },
  },
})
