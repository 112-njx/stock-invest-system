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
    allowedHosts: ['2d83faea.r27.cpolar.top'],
    proxy: {
      // 开发环境代理到后端 FastAPI，生产由 Nginx 反向代理
      // G29：ws=true 让 WS 也走本代理，保证与页面同源 → Cookie 正常携带
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true,
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
          // 其余三方依赖统一进 vendor chunk（含 axios/vue/pinia/vue-router）。
          // 不要把 axios 单独切一块：axios 1.19 内部对命名空间助手有跨 chunk 引用，
          // 与项目 http.ts chunk 形成循环依赖，生产构建下求值顺序错误，
          // 运行时报 "e is not a function"（dev 预打包单文件不暴露）。
          return 'vendor'
        },
      },
    },
  },
})
