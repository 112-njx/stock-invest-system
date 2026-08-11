import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { initMonitor, reportError, trackTiming } from '@/utils/monitor'
import './style.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)

// 前端监控（5.3）：Vue 组件错误 + 应用挂载耗时埋点
app.config.errorHandler = (err, _instance, info) => reportError(err, { info })
const mountStart = performance.now()
app.mount('#app')
initMonitor()
trackTiming('app_mount', performance.now() - mountStart)
