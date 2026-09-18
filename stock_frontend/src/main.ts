import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { initMonitor, reportError, trackTiming } from '@/utils/monitor'
import './style.css'
// G27：虚拟滚动组件基础样式（RecycleScroller 的滚动容器与 item 定位）
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)

// 前端监控（5.3）：Vue 组件错误 + 应用挂载耗时埋点
app.config.errorHandler = (err, _instance, info) => reportError(err, { info })
const mountStart = performance.now()
app.mount('#app')
initMonitor()
trackTiming('app_mount', performance.now() - mountStart)
