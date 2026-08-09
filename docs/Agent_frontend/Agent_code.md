Agent的前端编码记录,你需要按照：
编码时间：
编码内容（描述）：
的格式对该文档进行编写，要求编码内容简练而说明主要内容，
一次编写的编码内容描述在200字以内，如果超出字数而不能说明主要内容则新开一次编码记录。
每一次阶段下的细分任务都需要新开一次编码记录。

---

编码时间：2026-08-09
编码内容（描述）：1.1 工程脚手架——Vite8+Vue3+TS 工程初始化于 stock_frontend；配 @ 别名与 /api 开发代理（→8000）；路由 /login、/market、/market/detail、/ai 及登录守卫；Pinia 建 userStore/themeStore/marketStore；ESLint(flat)+Prettier。验收：typecheck/lint/build 全绿，四路由可达。

编码时间：2026-08-09
编码内容（描述）：1.2 设计体系——CSS 变量实现暗黑/明亮双主题（默认暗黑，html[data-theme] 切换），themeStore 持久化 localStorage 并在 App 启动时应用；封装 BaseButton/BaseCard/BaseInput/BaseSelect/ListRow；语义色红涨绿跌工具类与 color.ts 格式化。切换主题全局即时换色。

编码时间：2026-08-09
编码内容（描述）：1.3 API 封装层——axios 实例 baseURL=/api/v1，请求拦截注入 Bearer token，响应拦截统一 toast 错误、401 登出跳登录；api/{types,auth,market,ai}.ts 类型化接口（含标的/K线/快照/关注/会话/策略占位）。经 vite 代理实测登录后请求自动带 token。

编码时间：2026-08-09
编码内容（描述）：1.4 登录/注册页——Tab 切换表单与前端校验（用户名3-32/密码≥6/确认密码/昵称）；注册成功自动登录（后端注册即签发 JWT）；登录成功存 token 跳 /market；AppBar 顶部展示头像/昵称、主题切换、退出。注册→登录→/users/me 全流程经后端实测通过。