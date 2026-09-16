# V0.3 开发参考指南 — 22 项生产级优化

> V0.3 核心目标：将 V0.1+V0.2 的功能从"个人 Demo 可用"升级为"可交付真实用户的生产级作品"。
> 共 22 项优化，分两大类：前端修改/功能增加（13 项）、底层架构优化（9 项）。
> 每项包含「说明」（优化什么）和「优化方案」（具体怎么做），开发前必须阅读对应条目。

---

## 一、前端修改 / 功能增加（13 项）

### 1.1 用户可见的新功能（9 项）

---

### P0-1 双 token + 会话管理

**说明**：当前单 JWT 无刷新机制、无吊销、无活跃会话管理。token 被盗无法吊销，过期强制重登录，无"退出登录"后端端点。

**优化方案**：
- **双 token 机制**：access token（JWT，15min 有效期）+ refresh token（随机字符串，7d 有效期，HttpOnly Secure Cookie 存储）
- **refresh token 轮换**：每次刷新签发新 refresh token，旧 token 加入 Redis 黑名单（TTL=剩余有效期）；同一 refresh token 被使用两次时吊销该用户所有 refresh token（复用检测，疑似被盗）
- **access token 黑名单**：Redis SET `token_blacklist:{jti}`，登出/踢出/改密时加入，TTL=access token 剩余有效期
- **新增端点**：
  - `POST /api/v1/auth/refresh` — 刷新 token（Cookie 携带 refresh token）
  - `POST /api/v1/auth/logout` — 当前设备登出（吊销 access+refresh）
  - `GET /api/v1/auth/sessions` — 活跃设备列表
  - `DELETE /api/v1/auth/sessions/{id}` — 踢出指定设备
- **前端**：token 存储从 localStorage 改为 HttpOnly Cookie（配合 P0-7），axios `withCredentials=true`，401 时自动调 refresh 接口，refresh 失败跳登录页；
- 个人设置页增加"登录设备管理"入口

---

### P0-2 AI 限流 + 成本控制
### 待修改
**说明**：当前 AI 接口无用户级限流，所有用户共享 DeepSeek API Key，无 per-user 用量统计，存在账单无上限风险，无法做免费额度/付费分层。

**优化方案**：
- 用户栏设置增加APIKey输入栏,让用户自己输入自己的api-key即可。
---

### P0-3 记忆数据隐私
### 待修改
**说明**：需求文档承诺"记忆文件保存在用户本地"，实际记忆文本存于服务端 `data/memory/`（人类可读文件）与数据库 `memory_chunks`，语义向量原存于 ChromaDB（`data/chroma/`，V0.3 按 P1-12 统一迁移至 pgvector），均为明文无加密。属于虚假承诺且存在数据泄露风险（服务器被入侵=所有用户交易体系泄露）。V0.3 采用方案 B（改承诺+加密），方案 A（浏览器本地化）列为未来增强。

**优化方案**：
- **明确产品定位**：用户协议和隐私政策中说明"记忆数据存储在服务端并加密存储"，移除所有"本地存储"表述
- **记忆文件加密**：AES-256-GCM 加密 `data/memory/{user_id}/` 下所有文件，加密密钥从环境变量 `MEMORY_ENCRYPTION_KEY`（32 字节随机）读取，写入时加密、读取时解密
- **向量库加密策略（配合 P1-12 pgvector）**：记忆文本 content 加密存储；embedding 向量保持明文（加密后无法计算相似度，沿用原策略）。迁移 pgvector 后，加密文本与明文向量同在 `memory_chunks` 表，改由数据库访问权限与磁盘加密保护；迁移完成前的 ChromaDB 持久化目录权限设为 `0700`
- **memory_chunks 表**：content 字段改为加密存储（ENC(content)），检索时先解密原文
- **记忆访问审计**：`audit_log` 表记录每次记忆读取/写入/删除（user_id, action, memory_id, ip, created_at）
- **传输加密**：配合 P0-7 全链路 HTTPS
- **前端**：M 区记忆面板增加"数据存储说明"提示，告知用户记忆存服务端加密存储

---

### P0-4 密码找回 + 邮箱验证 + 登录保护

**说明**：当前注册邮箱可选且不验证，无密码重置流程，无登录暴力保护。用户忘密码则账户永久丢失，账户可被撞库攻击。

**优化方案**：
- **注册改造**：email 改为必填，注册后发送验证邮件（含 10min 有效验证链接），未验证邮箱用户每日首次登录提示验证
- **邮箱验证端点**：`GET /api/v1/auth/verify-email?token=xxx`（JWT 含 user_id+exp，签名密钥独立）
- **密码重置流程**：
  1. `POST /api/v1/auth/forgot-password` — 输入邮箱，发送重置邮件（1h 有效 token）
  2. `GET /api/v1/auth/reset-password?token=xxx` — 前端重置密码页
  3. `POST /api/v1/auth/reset-password` — 提交新密码，验证 token 后更新密码并吊销该用户所有 refresh token
- **登录暴力保护**：Redis 计数器 `login_fail:{username}`，连续失败 5 次锁定 15min，返回 423；成功登录后清零
- **邮件服务**：SMTP 配置（`SMTP_HOST/PORT/USER/PASS/FROM`），支持 STARTTLS/SSL；邮件模板 HTML+纯文本双格式（配合 P1-8）
- **前端**：登录页增加"忘记密码"链接→重置密码页；注册页邮箱必填+验证提示；个人设置页增加"修改密码""修改邮箱"入口

---

### P0-8 金融合规 + 用户协议 + 免责声明
**说明**：当前 AI 输出包含具体买卖建议，无用户协议/隐私政策/免责声明页面，无注册强制同意流程，无底部版权信息。存在法律合规风险（无牌照提供投资建议、无隐私政策违反个保法）。

**优化方案**：
- **法律页面**：新增 `/terms`（用户协议）、`/privacy`（隐私政策）、`/disclaimer`（免责声明）三个静态页面
  - 用户协议：服务条款、用户行为规范、知识产权、免责条款、争议解决
  - 隐私政策：收集信息类型、使用方式、存储方式、用户权利（访问/更正/删除）、数据安全措施
  - 免责声明：明确"本产品为研究辅助工具，不构成投资建议，AI 输出仅供参考，投资决策风险自负"
- **注册强制同意**：注册页增加"我已阅读并同意《用户协议》《隐私政策》《免责声明》"勾选框（默认不勾选），未勾选不能注册
- **AI 输出免责声明**：每次 AI 回复末尾自动追加固定文本"以上分析由 AI 生成，仅供研究参考，不构成投资建议。投资有风险，决策需谨慎。"
- **产品定位声明**：关于页明确标注"本产品为量化研究辅助工具，非证券投资咨询服务"
- **底部版权信息**：所有页面底部固定显示"© 2026 stock-agent-聂久翔 | 免责声明 | 隐私政策"链接
- **前端**：路由增加 `/terms`、`/privacy`、`/disclaimer`；注册页增加协议勾选；I 区增加"关于/法律"入口

---

### P1-5 数据导出 + 账户删除

**说明**：当前无数据导出端点，无账户删除端点，用户数据锁定在系统内。不符合《个人信息保护法》第四十五条数据复制权和第四十七条删除权要求。

**优化方案**：
- **数据导出**：
  - `POST /api/v1/users/me/export` — 异步创建导出任务（Celery），生成全量数据 ZIP 包，包含：用户信息(JSON)、关注列表(JSON)、支撑压力位(JSON)、交易策略(JSON+代码文件)、回测任务与结果(JSON)、会话与消息(JSON)、Agent 配置与运行记录(JSON)、记忆文件(原始 md)
  - `GET /api/v1/users/me/export/{task_id}` — 查询导出任务状态和下载链接
  - 导出文件存临时目录，24h 后自动删除，下载链接带签名 token
- **账户删除**：
  - `DELETE /api/v1/users/me` — 软删除（`users.is_deleted=true, deleted_at`），立即吊销所有 token，用户无法登录
  - 30 天宽限期：软删除后 30 天内可恢复，30 天后硬删除
  - 硬删除：级联删除所有关联数据（watchlist/support_resistance/strategies/backtest/conversations/chat_messages/agent_runs/agent_steps/memory_chunks（迁移 pgvector（P1-12）后向量行随该表级联删除，无需再单独删 ChromaDB collection；迁移前则删除该用户 Chroma collection）/user_memory_files/user_sessions/user_usage），删除 `data/memory/{user_id}/` 目录
  - 删除前二次确认：前端弹窗需输入"确认删除我的账户和所有数据"才能提交
- **前端**：个人设置页增加"导出我的数据"按钮（显示任务进度+下载链接）和"删除账户"入口（红色危险区域，二次确认）

---

### P1-8 邮件/通知服务 + 系统公告
### 疑问？ 生产级代码系统用户管理员账号的设计
**说明**：当前系统无法主动联系用户，无邮件发送、无站内通知、无系统公告。密码找回（P0-4）依赖此模块，回测/Agent 长任务完成无推送。

**优化方案**：
- **邮件服务**：
  - SMTP 配置（`SMTP_HOST/PORT/USER/PASS/FROM_NAME/FROM_EMAIL`），支持 STARTTLS/SSL
  - 邮件模板：验证邮件、密码重置邮件、异常登录提醒、系统通知，HTML+纯文本双格式
  - `email_logs` 表记录每次发送（recipient, template, status, error, created_at）
- **站内通知**：
  - `notifications` 表（id, user_id, type, title, content, is_read, created_at, read_at）
  - 端点：`GET /api/v1/notifications`（列表，未读优先）、`PATCH /api/v1/notifications/{id}/read`、`PATCH /api/v1/notifications/read-all`、`GET /api/v1/notifications/unread-count`
  - 通知类型：system（系统公告）、backtest_complete、agent_complete、security（异常登录/密码修改）
- **WS 任务完成推送**：扩展 WS 消息类型，回测/Agent 任务完成时推送 `{"type":"notification","data":{...}}`
- **系统公告**：
  - `admin_announcements` 表（id, title, content, type, is_active, created_at, expires_at）
  - `POST /api/v1/admin/announcements`（管理员发布）、`GET /api/v1/announcements/active`（当前活跃公告）
- **前端**：顶部导航栏增加通知铃铛图标（未读红点+计数），点击展开通知列表下拉面板；回测/Agent 完成时 toast 提示；顶部 banner 展示活跃公告（可关闭）；I 区"系统公告"入口查看历史

---

### 登录页面前端改造（方案 B：免登录浏览 + 头像弹窗登录）
### 待修改
**说明**：当前根目录是独立登录注册组件，用户必须登录才能使用任何功能。改为免登录浏览行情数据，登录入口移到头像弹窗，降低体验门槛，让访客打开网站直接看到产品核心功能。

**优化方案**：
- **路由重构**：
  - `/` → 行情首页（原登录页路由改为 `/login`）
  - `/market/detail` → 个股详情（不变）
  - `/ai` → AI 策略页（未登录可浏览布局，发送时引导登录）
  - `/login` → 独立登录页（保留，用于 deep link 强制跳转）
  - `/terms`、`/privacy`、`/disclaimer` → 法律页面（配合 P0-8）
- **头像区域改造**：
  - 未登录：默认头像图标 + "登录"文字，点击弹出登录/注册 Tab 弹窗（Modal 形式，不跳转页面）
  - 已登录：用户头像 + 昵称，点击展开下拉菜单（个人设置、我的数据、通知中心、退出登录）
- **未登录态空态**：
  - D/E 区关注列表：显示"登录后同步您的关注股票"引导卡片
  - 支撑/压力位设置：点击时弹出登录引导弹窗
  - AI 页发送按钮：可点击但提交时弹出"登录后使用 AI 分析"
  - I 区用户信息：显示未登录状态 + 登录入口
- **版权/介绍区域**：
  - 所有页面底部固定版权条："© 2026 stock-invest-system | 免责声明 | 隐私政策"（链接）
  - I 区"关于"按钮 → 弹出软件介绍/技术栈/开发者信息
- **登录弹窗**：Modal 组件包含登录/注册 Tab 切换，登录成功后关闭弹窗并刷新当前页面用户态，不跳转
- **登录/注册视觉重设计**：现登录页仅为 380px 纯色卡片、字母"K"占位 logo、背景单一（`var(--bg)`），视觉完成度低；重做时补齐金融终端风格背景与品牌视觉、加载/错误态，并与登录弹窗保持统一样式。机制类需求（忘记密码/邮箱必填/协议勾选/登录锁定提示）分别见 P0-4、P0-8

---

### P1-11 回测结果可视化（资金曲线 + K 线买卖点）

**说明**：后端回测已返回 equity_curve（资金曲线）与 trades（买卖流水），但前端 `StrategyMetricsPanel.vue` 仅展示 7 个汇总数字，**无资金曲线图、K 线上无买卖点标记**，已有 `Sparkline.vue` 未被回测面板复用，用户无法直观看懂策略执行过程。

**优化方案**：
- **资金曲线**：回测结果卡片/详情内用 lightweight-charts 面积图渲染 equity_curve（复用 KLineChart 图表能力），可叠加初始资金线/标的涨幅基准对比
- **K 线买卖点标注**：在标的 K 线上按 trades 叠加买入/卖出标记（遵循本项目红涨绿跌配色），止损/止盈用不同样式区分，hover 显示成交价/数量/费用/触发原因
- **交易明细列表**：trades 流水表（时间/方向/价格/数量/费用/累计持仓/已实现盈亏），与图表联动高亮
- **状态联动**：指标数字与图表、明细同区展示；回测中显示进度，失败显示原因与重试（配合 P1-4 队列繁忙提示）
- **依赖**：展示数值口径以 P0-10 修复后的净盈亏/胜率为准，先修正确性再做可视化

---

### 1.2 前端基础设施改造（4 项）

> 以下 4 项用户不可见，但必须修改前端代码，属于安全/性能基础设施改造。

---

### P0-5 WS 鉴权 token 不在 URL

**说明**：当前 WS 连接 `ws://host/api/v1/ws/market?token={jwt}`，token 作为 query 参数会被 Nginx 日志、浏览器历史、代理日志记录，存在泄露风险。

**优化方案**：
- **移除 query token 鉴权**，WS 鉴权统一使用 HttpOnly Cookie（配合 P0-1/P0-7）
- 浏览器端 `new WebSocket(url)` 自动携带同域 Cookie，无需手动传 token
- 服务端 WS 握手时从 Cookie 读取 access token 并校验，校验失败返回 401 关闭连接
- **保留首条消息 auth 机制**作为非浏览器客户端（脚本/移动端）备选：连接后首条消息 `{"action":"auth","token":"..."}`，服务端校验后标记连接已认证
- **Nginx 日志脱敏**：access_log 中过滤 `ws/market` 路径的 query 参数，或全局脱敏 token 参数
- **前端 `wsClient.ts`**：移除 URL 中的 token 参数，依赖 Cookie 自动携带；连接建立后不需要发 auth 消息（Cookie 已在握手时校验）

---

### P0-6 用户信息隔离 / XSS 防护

**说明**：当前前端 markdown 渲染 AI 输出未见 sanitize 步骤，用户可设置 nickname/agent 名称/策略标题/system_prompt 等字段，存在存储型 XSS 风险；需确保用户间数据严格隔离（横向越权防护）。

**优化方案**：
- **前端 markdown 渲染消毒**：引入 DOMPurify，所有 markdown→HTML 转换后经过 `DOMPurify.sanitize()`，配置允许标签白名单（禁止 script/iframe/object/embed/form，禁止 on* 事件属性，禁止 javascript: 协议链接）
- **用户输入校验**：后端对 nickname/agent_name/strategy_title/system_prompt 等字段增加长度限制和字符校验（禁止控制字符），前端表单增加 maxlength
- **CSP 头**：配合 P0-7 设置 `Content-Security-Policy`，`script-src 'self'`（禁止 inline script），`connect-src 'self' wss:`
- **用户数据隔离审查**：全面审查所有带 user_id 的查询（watchlist/strategies/conversations/agent_runs/memory/backtest），确保 `WHERE user_id = current_user.id` 不可省略；添加自动化测试验证横向越权（用户 A 不能访问用户 B 的数据）
- **策略代码展示**：N 区策略代码使用 textarea 或 code 标签纯文本展示，不使用 v-html
- **输出编码**：所有用户生成内容在前端渲染时使用 Vue 文本插值 `{{ }}`（自动 HTML 转义），禁止对用户内容使用 v-html

---

### P0-7 HTTPS + 安全响应头 + Cookie 安全

**说明**：当前 Nginx TLS 可选，默认 HTTP；JWT 存 localStorage（可被 XSS 读取）；无 HSTS/CSP/X-Frame-Options 等安全响应头。

**优化方案**：
- **强制 HTTPS**：Nginx 80 端口 301 重定向到 443，443 启用 TLS 1.2/1.3，证书路径可配置（`/etc/nginx/certs/`）
- **HSTS**：响应头 `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- **Cookie 安全**：所有 Cookie 设置 `Secure; HttpOnly; SameSite=Lax`，access token 和 refresh token 均通过 Cookie 传输，移除前端 localStorage token 存储
- **前端 axios**：`withCredentials=true`，请求拦截器不再从 localStorage 读 token（Cookie 自动携带），401 响应时自动调 refresh 接口
- **安全响应头**：
  - `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' wss:; font-src 'self' data:`
  - `X-Frame-Options: DENY`（防止点击劫持）
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: strict-origin-when-cross-origin`
- **开发环境**：vite dev server 仍可 HTTP（本地开发），生产构建强制 HTTPS
- **CORS 白名单修正（必做前置）**：当前 `main.py` 同时设置 `allow_origins=["*"]` 与 `allow_credentials=True`，属浏览器规范禁止的无效组合（凭证模式下不允许通配源），改为 Cookie 鉴权（P0-1）后跨域带凭证会直接失败；需改为显式可信来源白名单（dev/prod 域名走环境变量配置），保留 `allow_credentials=True`

---

### P1-6 列表分页 + 虚拟滚动

**说明**：当前列表端点（会话/策略/Agent 运行/回测任务）无分页，对话消息全量返回，前端列表无虚拟滚动。重度用户使用后会导致响应体巨大（MB 级）、前端渲染卡顿/崩溃。

**优化方案**：
- **后端列表分页**：所有列表端点增加 `page`（默认1）、`size`（默认20，最大100）参数，返回格式统一 `{items: [...], total: N, page: 1, size: 20, total_pages: N}`
  - 涉及端点：`GET /conversations`、`GET /strategies`、`GET /agents`、`GET /agent/runs`、`GET /backtest/tasks`
  - 关注列表通常较少，可选分页
- **对话消息游标分页**：`GET /conversations/{id}/messages` 增加 `limit`（默认50）、`before`（message_id 游标）参数，返回 `{items: [...], has_more: bool, next_cursor: message_id|null}`；前端默认加载最新50条，滚动到顶部时加载更早消息
- **前端虚拟滚动**：引入 `vue-virtual-scroller`，J 区会话列表、M 区策略列表/Agent 运行列表使用虚拟滚动；对话消息区使用增量加载（消息高度不固定，非虚拟滚动）
- **性能监控**：列表渲染时间埋点，超过 500ms 告警

---

## 二、底层架构优化（9 项）

> 以下 4 项纯后端/运维，用户不可见，属于基础设施加固。

---

### P1-1 备份 + 灾难恢复

**说明**：当前无数据库自动备份、无 Redis 持久化确认、ChromaDB 向量库/记忆文件无备份（按 P1-12 迁移 pgvector 后向量随 PostgreSQL 统一备份，无需再单独备份），服务器故障或误操作可导致全部用户数据永久丢失。PostgreSQL 有约 680 个 K线分区子表，手动恢复极其困难。

**优化方案**：
- **PostgreSQL 备份**：
  - 每日全量备份：`pg_dump -Fc stock_invest > /backup/pg/full_$(date +%Y%m%d).dump`，保留最近30天
  - WAL 归档：`archive_mode=on, archive_command`，WAL 归档到 `/backup/pg/wal/`，支持 PITR（时间点恢复）
  - 备份脚本 `scripts/backup_pg.sh`，纳入 Celery beat 每日凌晨 2:00 执行
  - 每周自动恢复到临时库验证备份完整性（`scripts/verify_backup.sh`）
- **Redis 持久化**：启用 AOF（`appendonly yes, appendfsync everysec`）+ RDB 快照（`save 60 1000`），Redis 数据目录纳入文件备份
- **文件备份**：`data/memory/`、导出文件目录每日 rsync 到 `/backup/files/`，保留最近7天；`data/chroma/` 仅在 P1-12（pgvector 迁移）完成前需要一并备份，迁移后向量随 `pg_dump` 备份，停止该目录备份并删除；pgvector 扩展与向量表随 PostgreSQL 全量/WAL 备份自动覆盖
- **异地备份**：备份目录通过 rclone 同步到对象存储（S3/阿里云 OSS），每日一次，保留90天
- **恢复演练文档**：`docs/ops/disaster_recovery.md`，包含 PostgreSQL 全量恢复/PITR 恢复/Redis 恢复/文件恢复步骤，每季度执行一次演练
- **监控**：备份任务成功/失败告警、备份文件大小监控、备份目录磁盘空间监控（配合 P1-7）

---

### P1-2 水平扩展架构

**说明**：当前 WebSocket ConnectionManager 是进程内单例，多 API 实例间不共享 WS 连接；Celery worker 无冗余；Redis/PostgreSQL 单点。用户量增长后无法通过加机器扩容，单实例重启导致所有 WS 连接断开。

**优化方案**：
- **WS 连接共享**：扩展现有 Redis pub/sub 桥接——realtime_poll 发布到 Redis 频道后，所有 API 实例都订阅该频道，收到消息后推送给本实例上的 WS 客户端。ConnectionManager 保持进程内（每个实例管理自己的连接），消息通过 Redis 广播到所有实例（当前架构已有 Celery→Redis→API 桥接，需验证多实例订阅）
- **Nginx 负载均衡**：upstream api 多实例（least_conn），WS 升级头配置 `proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; proxy_read_timeout 3600s;`，无需 sticky session（消息通过 Redis 广播）
- **PostgreSQL 读写分离**：主库写 + 只读从库读（行情查询/K线/快照/指标走只读节点），SQLAlchemy 配置读写分离路由；用户数据（关注/策略/会话）读写都走主库（数据量小、一致性要求高）
- **Redis 高可用**：Redis Sentinel 一主两从，自动故障转移；应用层配置 Sentinel 地址自动发现主节点
- **Celery worker 多实例**：sync/backtest/ai 队列各至少 2 实例，任务自动分发；确认所有任务幂等（重复执行不产生脏数据）
- **无状态验证**：确认 API 进程无本地状态（所有状态走 Redis/PG），可随时增减实例

---

### P1-3 数据库时区统一（naive → timestamptz）

**说明**：K线 `ts`/快照 `updated_at` 列为 `timestamp without time zone`（naive），ORM 声明 `tz=True` 但实际表结构不对（迁移 0001 遗留），代码层用 `as_utc()` 归一规避。开发环境全东八区所以不明显，生产多时区环境会导致缓存失效时间错误、WS 增量推送丢数据或重复、`data_age_seconds` 计算错误、回测区间偏移等**静默数据错误**（不报错但结果全错）。

**优化方案**：
- **Alembic 迁移 0005_timezone_fix.py**：
  - 所有时间字段从 `TIMESTAMP` 改为 `TIMESTAMPTZ`：kline_*/ts、snapshot_realtime/updated_at、sync_tasks/*、backtest_tasks/*、agent_runs/*、agent_steps/created_at、memory_chunks/created_at、所有表的 created_at/updated_at
  - 存量数据转换：`ALTER TABLE ... ALTER COLUMN ... TYPE TIMESTAMPTZ USING column AT TIME ZONE 'UTC'`（假设存量数据均为 UTC，迁移前需先验证抽样数据）
  - 分区表：kline_* 按月分区约 680 个子表，使用 DO 块循环执行 ALTER
- **代码清理**：移除所有 `as_utc()` 归一调用（数据库已统一为 timestamptz，ORM 自动返回 aware datetime）；确认所有时间比较直接进行；数据库连接时区设置为 UTC（`timezone='UTC'` in SQLAlchemy create_engine）
- **验证**：迁移后抽样对比 K线 ts、快照 updated_at 的值；全量 190 pytest 通过；验证 WS 增量推送、缓存失效、data_age_seconds、回测区间在迁移后正确
- **回滚方案**：迁移前全量备份（配合 P1-1），如遇问题可回滚到 0004

---

### P1-4 策略代码沙箱加固 + 资源隔离

**说明**：当前策略代码在 RestrictedPython 沙箱执行，死循环由 Celery 硬超时杀 worker 进程兜底（`BACKTEST_HARD_TIME_LIMIT`，触发后 worker 进程被终止重启），无 CPU/内存限制，无 per-user 并发控制。恶意策略可导致 worker 崩溃、影响其他用户任务，或通过沙箱逃逸执行任意代码。

**优化方案**：
- **进程隔离**：策略执行从 Celery worker 主进程移到独立子进程（`multiprocessing.Process`），每个回测任务一个独立进程；子进程设置 CPU 时间限制（`resource.setrlimit RLIMIT_CPU`）和内存限制（`RLIMIT_AS`/`RLIMIT_DATA`）；子进程超时后强制 terminate，不影响 worker 主进程和其他任务
- **RestrictedPython 加固**：锁定版本并定期检查安全公告；扩展安全审计禁止 `__class__`/`__bases__`/`__subclasses__` 等属性访问（默认已禁，需验证）；禁止大量内存分配（内存限制兜底）
- **per-user 并发控制**：Redis 计数器 `backtest_running:{user_id}`，同一用户最多同时运行 3 个回测（可配置），超过返回 429；全局回测并发上限由 Celery worker 并发数控制，队列积压时返回"回测队列繁忙，请稍后重试"
- **策略校验增强**：提交回测前必须通过三级校验（ast.parse + 接口校验 + 沙箱 dry-run），dry-run 使用 1 根模拟 K 线，限制 CPU 1s、内存 64MB（配合 V0.2 阶段八）
- **监控**：回测任务执行时间分布、内存峰值、失败原因统计；异常策略告警（连续失败、超时、内存超限）
- **前端**：回测队列繁忙时显示"当前回测队列繁忙，预计等待 X 分钟"

---

### P0-9 Agent 工具按需回源取数（消除"数据孤岛"）

**说明**：当前 Agent 工具（`market_snapshot/get_kline/get_indicator`）只读 Redis→PostgreSQL，缓存或库中无数据时直接返回 `{"error":"暂无数据"}`，**不会回源 DataProvider 实时拉取，也不会触发 kline_init 同步**；外部回退能力（`search_ak_stock`）仅存在于搜索接口，Agent 工具链拿不到。导致未被 Celery 同步/预热的标的（新股、未关注标的、缓存过期标的）在 AI 对话中完全无法分析，形成"库里有才答得出"的数据孤岛，是 AI 功能的核心命门。

**优化方案**：
- **工具层回源**：market_snapshot/get_kline 缓存与库均未命中时，调用 DataProvider 实时拉取（fetch_realtime/fetch_kline），落库 + 回写缓存后再返回；仍失败才返回 error
- **按需触发同步**：标的仅有目录（is_catalog=true）而无 K 线时，工具内异步触发单标的 kline_init，先返回"数据同步中/以最近可得数据兜底"，避免同步阻塞对话
- **标的解析兜底**：resolve_symbol_id 解析不到时，复用搜索外部回退（代码/名称→目录→akshare）先解析再判定不存在
- **回源限流/熔断**：加短 TTL 回源锁（如 `agent_fetch:{symbol_id}`，60s）防止 LLM 反复工具调用打爆数据源，复用 DataProvider 既有优先级熔断链
- **返回状态语义化**：区分"数据陈旧（data_age）/同步中/确实不存在"，供 Agent 组织准确话术，禁止编造行情
- **异步隔离**：工具内同步外部请求统一用线程池（run_in_executor）包裹，避免阻塞 ReAct 异步事件循环（配合 P1-9）

---

### P0-10 回测引擎正确性修复（胜率口径 + 撮合现实性）

**说明**：当前回测绩效与撮合存在多处口径/现实性缺陷，导致回测结果不可信：
1. 胜率按**毛盈亏**判定：`_pair_trades` 的 `pnl=（卖价-买价）×股数`，未扣买入佣金与卖出佣金+印花税，毛赚净亏的交易被计为"赢"，胜率虚高；
2. 期末未平仓持仓不参与配对，浮盈浮亏不计入胜率/盈亏，只统计已平仓；
3. 一次卖单 FIFO 拆配多段买单，每段各算一个 win/loss，`total_trades` 为配对段数而非完整交易回合；
4. 平手（pnl==0）被计入亏损（`pnl<=0`）；
5. 成本口径双轨：止损止盈用加权平均成本 `entry_price`，胜率配对用 FIFO，两者不一致；
6. 撮合过于理想：滑点恒为 0、不校验当日成交量（涨跌停/无量也能成交）；同一根 bar 先自动止损卖出、随后 on_bar 又可买回，现实中无法实现。

**优化方案**：
- **净盈亏配对**：配对 pnl 扣除对应买卖费用（买入佣金按配对股数分摊、卖出佣金+印花税），win/loss 一律按净盈亏判定
- **期末持仓结算**：结束仍持仓部分按最后一根 bar 收盘价做浮动结算（标记"未平仓"），计入总收益并在 metrics_json 单列；胜率口径明确区分已实现/未实现
- **统一交易回合口径**：以"一次完整买入→卖出回合"为一笔统计胜率与盈亏比，FIFO 仅用于成本分摊；平手单列 draw，不并入亏损
- **统一成本法**：止损止盈触发价与配对成本统一为同一口径（FIFO 或加权平均二选一并文档化）
- **撮合现实性**：引入可配置滑点；单笔成交不超过当根 bar 成交量的可配置比例；触及涨停不买入、跌停不卖出；修复同 bar 逻辑（自动止损后禁止当根再开同向仓，或明确状态优先级并文档化）
- **回归测试**：构造确定性交易单（含费用、分批、期末持仓、平手、涨跌停）做指标单测锁定期望值；修复后用同一策略对比修复前后差异

---

### P1-9 启动预热与缓存链路性能优化

**说明**：首次启动/冷缓存时数据获取慢，且存在阻塞运行时的实现：
1. `main.py` lifespan 在 yield 前**同步**执行 `warmup_fixed_indices_cache`，串行遍历 49 个固定指数 ×（500 根日K+快照）写 Redis，阻塞 API 启动；
2. `run_fixed_indices_sync` 串行 49 标的 × 4 周期同步网络拉取，无并发，冷启动首次同步耗时长；
3. 缓存击穿锁内 `time.sleep(2)` 为同步阻塞，在 async 框架中阻塞事件循环；DataProvider 用 requests+time.sleep 同步实现，在 Agent 异步链路同样阻塞；
4. 预热只覆盖日 K（500 根），15m/周/月首访仍回源；
5. WS 监听用独立线程 + 自建 event loop（new_event_loop+threading），生命周期脆弱，多实例下难维护（配合 P1-2）。

**优化方案**：
- **预热非阻塞**：lifespan 将缓存预热改为后台 async task（或交由 Celery），不阻塞应用就绪，就绪探针不依赖预热完成
- **并发同步**：固定指数/多周期拉取用线程池或 asyncio.gather 并发（控制并发度与数据源限频），替代纯串行循环
- **消除同步阻塞**：缓存击穿等待改 asyncio.sleep/异步锁，请求链路禁止 time.sleep；同步 DataProvider 调用统一经 run_in_executor 线程池隔离
- **分级预热**：按访问热度预热（固定指数日K优先，其余周期/字段惰性加载并后台补齐）
- **WS 监听生命周期**：独立线程+自建 event loop 改为 lifespan 统一管理的 asyncio task，可追踪、可优雅退出（配合 P1-2 多实例订阅）
- **指标**：记录启动耗时、预热命中率、缓存回源耗时、冷启动首屏时间，用于优化前后对比

---

### P1-10 扩展基本面/资讯数据源与 Agent 工具（财报·新闻 MCP）

**说明**：当前 DataProvider 仅有 `fetch_kline/fetch_realtime/fetch_index_pe/fetch_catalog/search_ak_stock`，Agent 工具只有行情/指标/记忆，**无财报、新闻公告、资金流等基本面与资讯能力**，AI 分析只能依赖量价数据，无法回答公司财务、行业热点、消息面问题。

**优化方案**：
- **数据源抽象扩展**：BaseDataProvider 增加财报、新闻/公告、资金流等接口（先在东财 Provider 实现，沿用优先级链+熔断+重试），不可用源返回 available=False 降级
- **Agent 工具新增**：新增 get_financials（财报/估值）、get_news（新闻公告，带来源与时间）、get_money_flow（主力资金流，可选）等工具，description 写清何时调用，返回结构化数据
- **落库与缓存**：财报等低频数据入库 + Redis 长 TTL 缓存；新闻按标的/关键词短 TTL 缓存，避免重复抓取
- **可插拔 MCP 化**：工具按统一工具接口组织，便于后续接入更多外部能力；结果标注数据时间与来源，Agent 引用须带来源、缺失时明确说明而非编造
- **合规**：资讯/财报仅作研究信息聚合，配合 P0-8 免责声明，不生成确定性买卖建议
- **前端**：AI 回复中渲染新闻/财报引用来源（标题+链接+时间），展示位置随 AI 对话区设计

---

### P1-12 向量库 ChromaDB → pgvector 统一

**说明**：当前记忆向量用 ChromaDB 本地持久化（`data/chroma/`，`chromadb.PersistentClient`，按用户分 collection `user_memory_{id}_{kind}`），与 PostgreSQL 形成两套存储——`memory_chunks` 表存元数据、Chroma 存向量与文档、靠 `vector_id` 关联。由此带来：多一套存储进程/目录与备份、PG 与 Chroma 数据一致性难保证、跨存储无法原子事务、水平扩展（P1-2）时本地文件向量库无法被多实例共享、检索需先查 Chroma 再在内存重排。统一到 PostgreSQL 的 pgvector 扩展后，记忆元数据与向量同库，TopK 检索一条 SQL 完成，并天然随 P1-1 数据库备份、随主从/连接池扩展。

**优化方案**：
- **扩展与表结构**：PostgreSQL 安装并 `CREATE EXTENSION IF NOT EXISTS vector;`（部署/ Docker 镜像需内置 pgvector）；新增 Alembic 迁移，给 `memory_chunks` 增加 `embedding vector(384)` 列（维度对齐 `EMBEDDING_DIM`，hash/MiniLM 均为 384）与 `embedding_kind varchar(16)`（区分 hash/minilm，等价原 collection 名后缀的向量空间隔离，避免混用导致检索失真）；原 `vector_id` 迁移验证后废弃
- **向量索引**：`USING hnsw (embedding vector_cosine_ops)`（数据量小可先 ivfflat），并对 (user_id, embedding_kind) 建普通索引配合过滤
- **检索下推 SQL**：用余弦距离操作符完成 TopK（`ORDER BY embedding <=> :qvec LIMIT k`），原"相似度×0.7+重要性×0.3"加权重排、find_duplicate 的 0.85 去重阈值全部下推为 SQL；以 user_id + embedding_kind 行级过滤替代 per-user collection
- **存储层重写**：`agent/memory/store.py` 移除 PersistentClient/collection，改为 repository + SQLAlchemy；add/update/delete/清空改为对 memory_chunks 行的增删改（清空=按 user_id 删除）；embedding 计算仍复用现有 Hash/MiniLM，`embedding.py` 去掉对 `chromadb.api.types` 的依赖，EmbeddingFunction 改为本项目自有可调用协议
- **存量数据迁移**：一次性脚本遍历各 Chroma collection，按 vector_id 回填 memory_chunks.embedding/embedding_kind；校验行数与抽样 TopK 召回一致后再下线 Chroma，迁移期可双写灰度
- **依赖与清理**：依赖移除 chromadb、引入 pgvector；删除 `data/chroma/` 目录与 `CHROMA_DIR` 配置；更新本地/部署安装文档（数据库需装 vector 扩展）
- **与加密协同（P0-3）**：content 加密、embedding 保持明文向量（加密后无法计算相似度，沿用原"向量明文"策略），统一入库后改由数据库访问权限与磁盘加密保护
- **验证与回滚**：迁移前后对同一批 query 对比 TopK 召回与 score；记忆增删改/清空/去重合并/按用户隔离全链路回归；pytest 全绿；验证完成前保留 Chroma 与迁移脚本作为回滚路径

---

## 三、实施依赖与建议顺序

### 强依赖关系

```
P1-8(邮件服务) ──→ P0-4(密码找回/邮箱验证)
P0-7(Cookie安全) ──→ P0-1(双token) ──→ P0-5(WS鉴权)
P0-7(CSP头) ──→ P0-6(XSS防护)
P0-8(法律页面) ──→ 登录页改造(注册协议勾选)
P1-1(备份) ──→ P1-3(数据库时区迁移，迁移前需备份)
P0-10(回测正确性) ──→ P1-11(回测可视化，口径正确后再展示)
P1-9(异步线程池隔离) ──→ P0-9(Agent 按需回源，避免阻塞事件循环)
P1-12(pgvector 迁移) ──→ P0-3(记忆加密，向量统一入库后再定加密/权限策略)
```

### 建议实施批次

| 批次 | 包含项 | 说明 |
|---|---|---|
| 第零批（核心缺陷修复） | P0-9, P0-10 | 实测发现的功能命门：Agent 按需回源取数 + 回测胜率/撮合正确性，独立于安全改造，应最先做 |
| 第一批（安全地基） | P0-7, P0-1, P0-5, P0-6 | 鉴权安全一体化改造，共享 Cookie/CSP 基础设施（P0-7 内含 CORS 白名单修正） |
| 第二批（合规+账户） | P0-8, P1-8, P0-4, 登录页改造 | 法律页面+邮件服务+密码找回+登录页重构，互相依赖 |
| 第三批（数据+成本） | P1-12, P0-3, P0-2, P1-5 | 先做 pgvector 向量库统一再做记忆加密；AI 限流+数据导出删除 |
| 第四批（性能+运维） | P1-6, P1-1, P1-3, P1-4, P1-2, P1-9 | 分页+备份+时区+沙箱+水平扩展+启动预热/缓存性能 |
| 第五批（扩展+可视化） | P1-10, P1-11 | 财报/新闻数据源与 Agent 工具扩展、回测资金曲线与买卖点可视化（P1-11 依赖 P0-10） |

### 注意事项

1. 每批开发前必须重新阅读本文件对应条目，确保方案理解一致
2. P1-3（数据库时区迁移）执行前必须先完成 P1-1（备份），迁移风险高
3. P0-1/P0-5/P0-7 三者共享鉴权基础设施，必须同一批次连续开发，禁止拆分
4. 登录页改造（方案 B）涉及路由重构，需确保所有页面的未登录态都有处理，不能出现白屏
5. 所有新增端点必须写入 `docs/Agent_backend/api-docs.md`，所有前端组件变更写入 `docs/Agent_frontend/Agent_code.md`
6. P0-9/P0-10 为实测发现的核心缺陷（非新功能），修复时必须先补可复现的回归测试再改实现；P0-10 修复前后需用同一策略对比胜率/收益差异并记录
7. P0-9 回源取数与 P1-9 异步隔离强相关，禁止在 async 请求/Agent 链路新增 `time.sleep`、`requests` 等同步阻塞调用
8. P1-12（ChromaDB→pgvector）须先于 P0-3（记忆加密）实施；向量迁移需双写灰度 + TopK 召回对比验证通过后，才允许移除 chromadb 依赖与 `data/chroma/`，数据库镜像必须内置 pgvector 扩展

---

## 四、开发规划与多 Agent 并行任务分配（256K 上下文步长）

> 本节基于第三章「强依赖关系」与「建议实施批次」，将 22 项优化拆分为 **36 个可独立分配的开发步骤**。
> 三项目标：① 多 agent 并行开发时**不会因依赖未就绪而空转**；② 每个步骤的自包含上下文（规格 + 相关代码 + 实现 + 测试）**≤ 256K token**；③ **任一步骤可按任务量自由指派**给空闲 agent，步骤之间无 owner 绑定。

### 4.1 规划原则与步长定义

- **步长定义**：一个「开发步骤」＝一个 agent 在单次会话内能读入全部相关代码文件 + 对应条目规格 + 实现 + 测试，不超 256K token。下表「规模」列：**小**（改动 <8 文件）、**中**（8~20 文件）、**大**（20~40 文件）、**特大**（>40 文件或高风险 DB 迁移，落地时须按文件簇再内拆）。
- **并行安全规则**：只有「前置」全部满足的步骤才可被认领；前置未就绪的步骤处于「等待」态，**不占用 agent**。同一步骤禁止两个 agent 同时改同一文件簇（见 4.5）。
- **依赖修订（相较第三章，三处拆分以解除阻塞）**：
  1. `P1-9` 拆为 `P1-9a 线程池隔离`（作为 P0-9 的前置，先交付）与 `P1-9b 预热/缓存/WS 生命周期`（独立）。
  2. `P0-3` 拆为 `P0-3a 文件加密+审计`（独立可先做）与 `P0-3b 向量 content 加密`（依赖 P1-12）。
  3. `P0-2` 按已确认的**简化版（用户自填 key）**规划，不再含服务端统一限流/额度分层。

### 4.2 修订版依赖关系图

```
P1-9a(线程池隔离) ──→ P0-9(按需回源取数)
P1-8a(邮件服务) ──→ P0-4(邮箱验证/密码重置)
P0-7(HTTPS/Cookie) ──→ P0-1(双token) ──→ P0-5(WS鉴权)
P0-7 ──→ P0-6(XSS/CSP)
P0-8(法律页面) ──→ 登录页改造(协议勾选)
P1-1(备份) ──→ P1-3(时区迁移)
P0-10(回测正确性) ──→ P1-11(回测可视化)
P1-12(pgvector) ──→ P0-3b(向量content加密)
```

### 4.3 步骤分解总表（36 步）

> 类型：后端 / 前端 / 全栈 / DB·后端 / 运维 / 测试。「前置」为空（—）即波次 0，可立即认领。

| 编号 | 所属项 | 步骤内容 | 类型 | 前置 | 规模 |
|---|---|---|---|---|---|
| G01 | P0-7 | HTTPS 强制(TLS1.2/1.3)+安全响应头(HSTS/CSP/X-Frame-Options/nosniff/Referrer)+**CORS 白名单修正**+Cookie Secure/HttpOnly/SameSite+axios withCredentials | 全栈·运维 | — | 中 |
| G02 | P1-8a | SMTP 配置+邮件模板(验证/重置/异常登录/通知，HTML+纯文本双格式)+`email_logs` 表 | 后端 | — | 中 |
| G03 | P0-8 | `/terms` `/privacy` `/disclaimer` 三页+底部版权条+AI 回复免责声明追加+关于页定位声明 | 前端 | — | 中 |
| G04 | P1-12a | 装 `vector` 扩展(Docker 镜像内置)+迁移给 `memory_chunks` 加 `embedding(384)`/`embedding_kind`+HNSW 索引 | DB·后端 | — | 中 |
| G05 | P1-1 | pg_dump 全量+WAL 归档+Redis AOF/RDB+文件 rsync+rclone 异地+恢复演练文档+监控告警 | 运维 | — | 中 |
| G06 | P0-10a | 回测正确性：构造确定性交易单(费用/分批/期末持仓/平手/涨跌停)回归测试，锁定修复前口径与目标期望值 | 测试 | — | 中 |
| G07 | P1-9a | `run_in_executor` 线程池隔离通用封装+DataProvider 同步调用接入点改造（不阻塞 async/Agent 链路） | 后端 | — | 小 |
| G08 | P1-4a | 策略子进程隔离(multiprocessing)+`RLIMIT_CPU`/`RLIMIT_AS` 限制+强制 terminate+per-user 并发计数(429) | 后端 | — | 中 |
| G09 | P1-6a | 列表端点统一 `page/size` 分页(conversations/strategies/agents/agent_runs/backtest_tasks)+消息游标分页(before/limit) | 后端 | — | 中 |
| G10 | P1-2a | WS 多实例 Redis pub/sub 桥接+Nginx upstream 负载均衡+WS 升级头 | 后端·运维 | — | 中 |
| G11 | P1-2b | PG 读写分离路由(SQLAlchemy)+Redis Sentinel 一主两从自动故障转移 | 后端·运维 | — | 中 |
| G12 | P1-2c | Celery 多队列多实例+任务幂等审计+API 无状态验证 | 后端·运维 | — | 中 |
| G13 | P1-10a | `BaseDataProvider` 增加财报/新闻/资金流接口+东财实现+优先级链熔断降级(available=False) | 后端 | — | 中 |
| G14 | P0-2 | 用户自填 API key(个人设置栏)+后端加密存储+读取校验【简化版，限流/额度不做】 | 全栈 | — | 小 |
| G15 | P0-3a | `data/memory/{uid}/` 文件 AES-256-GCM 加解密(`MEMORY_ENCRYPTION_KEY`)+`audit_log` 审计+前端"存储说明"提示 | 全栈 | — | 中 |
| G16 | P1-8b | `notifications` 表+端点(列表/已读/未读数)+`admin_announcements` 表+公告端点+WS notification 推送+前端铃铛/banner | 全栈 | — | 中 |
| G17 | P1-5a | 数据导出异步任务(Celery 生成全量 ZIP)+状态查询+签名下载链接+24h 自动删除 | 后端 | — | 中 |
| G18 | P1-5b | 账户软删除(`is_deleted`)+30 天宽限+硬删除级联+二次确认前端 | 全栈 | — | 中 |
| G28 | P1-9b | 预热非阻塞(lifespan 后台任务)+固定指数并发拉取+缓存击穿异步锁+WS 监听 asyncio 生命周期 | 后端 | — | 中 |
| G19 | P0-1 | 双 token(access 15min JWT+refresh 7d HttpOnly Cookie)+轮换+复用检测吊销+黑名单+refresh/logout/sessions 端点 | 后端 | G01 | 大 |
| G20 | P0-10b | 回测引擎修复：净盈亏配对+期末持仓结算+统一交易回合口径+统一成本法+撮合现实性(滑点/量/涨跌停/同bar) | 后端 | G06 | 大 |
| G21 | P1-12b | `store.py` 去 Chroma→SQLAlchemy repository+检索 SQL 下推(TopK 余弦)+`embedding.py` 去 chromadb 依赖 | 后端 | G04 | 大 |
| G22 | P0-9 | market_snapshot/get_kline 回源取数+按需触发 kline_init+标的解析兜底+回源锁熔断+状态语义化 | 后端 | G07 | 大 |
| G23 | P0-4a | 邮箱验证端点+forgot/reset-password 流程+登录暴力保护(Redis 计数 5 次锁 15min) | 后端 | G02 | 中 |
| G24 | P1-3 | 迁移 0005 naive→timestamptz(含 680 分区表 DO 块循环)+清理 `as_utc()`+连接时区 UTC+验证回滚 | DB·后端 | G05 | 特大 |
| G25 | P1-4b | 策略三级校验(ast.parse+接口+dry-run 资源限制)+回测监控告警+前端"队列繁忙"提示 | 全栈 | G08 | 中 |
| G26 | P1-10b | Agent 工具 get_financials/get_news/get_money_flow+落库长 TTL 缓存+前端引用来源渲染 | 全栈 | G13 | 中 |
| G27 | P1-6b | vue-virtual-scroller 虚拟滚动+对话消息增量加载(before 游标)+列表渲染埋点 | 前端 | G09 | 中 |
| G29 | P0-5 | WS Cookie 鉴权(握手从 Cookie 读 access token)+首条 auth 兜底+Nginx query 脱敏+wsClient 去 token | 全栈 | G19 | 中 |
| G30 | P0-6 | DOMPurify 消毒+输入长度/字符校验+用户数据隔离审查(`WHERE user_id`)+横向越权自动化测试 | 全栈 | G01 | 中 |
| G31 | P1-12c | 存量 Chroma→pgvector 回填脚本+TopK 召回对比验证+双写灰度+下线 Chroma/删依赖 | DB·后端 | G21 | 大 |
| G32 | P1-11 | 回测资金曲线(lightweight-charts)+K线买卖点标注+交易明细联动+状态联动 | 前端 | G20 | 中 |
| G33 | P0-4b | 前端忘记密码/重置页+注册邮箱必填+个人设置改密/改邮箱入口 | 前端 | G23 | 中 |
| G34 | P0-3b | `memory_chunks.content` 加密(ENC)+检索解密+隐私政策文案对齐 | 后端 | G21 | 小 |
| G35 | 登录页改造 | 方案 B：路由重构(`/` `/login` `/ai`)+头像弹窗登录+未登录空态+登录/注册视觉重设计+协议勾选/忘记密码/用户态集成 | 前端 | G03,G19,G23,G33,G29 | 大 |
| G36 | 收尾 | 全量 pytest 回归+api-docs.md/Agent_code.md 更新+六要素审查收尾+上线检查单 | 全栈 | 全部 | 大 |

### 4.4 并行波次与关键路径

| 波次 | 步骤（可并行） | 说明 |
|---|---|---|
| 波次 0 | G01~G18、G28（19 步） | 全部无前置，可**同时开 N 路**；N = 可用 agent 数 |
| 波次 1 | G19~G27（9 步） | 各依赖波次 0 的单个步骤，前置一落地即可认领 |
| 波次 2 | G29~G34（6 步） | 二级依赖 |
| 波次 3 | G35、G36 | 集成与收尾 |

- **关键路径（最慢链，决定总工期）**：`G01→G19→G29→G35→G36`（5 跳）与 `G04→G21→G31→G34→G36`（5 跳）与 `G06→G20→G32→G36`（4 跳）。
- **不会空转的保证**：每步只依赖"前置编号"，agent 认领前检查前置是否全绿；波次 0 提供 19 个可立即开工的步骤，足以让任意规模的团队满负荷并行，无需等待串行解锁。

### 4.5 前端文件冲突协调（防串改）

多个前端步骤会写入同一文件簇，**必须单 owner 串行集成**，否则产生 merge 冲突：

1. **个人设置页（单组件）**：被 G14(APIKey)、G15(存储说明)、G19(设备管理)、G33(改密/邮箱)、G18(账户删除) 五项汇聚 → 建议指定一个"个人设置页 owner"统一实现，或按子区块拆分后由该 owner 最后合并。
2. **顶部导航栏**：G16(铃铛) 与 G35(头像弹窗) → 协调合并顺序。
3. **路由 `router/index`**：G03(法律页路由) 与 G35(登录路由重构) → G35 为后集大成者，应最后合入。
4. **登录/注册组件**：G33、G35、G03(协议勾选) → 同 G35 收口。

### 4.6 待确认项（开工前须定稿）

1. **P1-8b 系统公告的"管理员账号"设计未定** → 暂按「`users.is_admin` 标志 + 环境变量初始化管理员」假设，开工前定稿，否则 G16 的公告部分挂起。
2. **登录页改造(G35)的"视觉重设计"方向未定** → 需设计稿/参考图（可用图片阅读 skill 读图）定稿后再进入视觉实现；路由/空态/版权条可先行。
3. **P0-2 简化版是否保留"用量统计"展示**（即便不做限流）→ 默认不做，仅存 key；如要展示用量需回滚部分原方案。
4. **P0-7 CORS 白名单域名（dev/prod 环境变量值）** → 需确认具体域名后写入。

### 4.7 建议任务分配泳道（可自由调整）

> 以下为**建议泳道**，非硬绑定；任意空闲 agent 可认领任意"前置已满足"的步骤。

| 泳道 | 建议步骤序列 |
|---|---|
| A 安全鉴权 | G01 → G19 → G29 → G30 |
| B 合规账户邮件 | G02 → G23 → G33；穿插 G03 / G16 / G17 / G18 |
| C 数据·AI成本 | G04 → G21 → G31；穿插 G15 / G34 / G14 |
| D 回测引擎 | G06 → G20 → G32 |
| E Agent 取数 | G07 → G22；穿插 G13 → G26 |
| F 运维扩展 | G05 → G24；穿插 G08 → G25 与 G10 / G11 / G12 |
| G 前端集成 | G09 → G27；穿插 G35 |
| H 收尾审查 | G36 |

### 4.8 收尾与验收| 泳道 | 建议步骤序列 |
|---|---|
| A 安全鉴权 | G01 → G19 → G29 → G30 |
| B 合规账户邮件 | G02 → G23 → G33；穿插 G03 / G16 / G17 / G18 |
| C 数据·AI成本 | G04 → G21 → G31；穿插 G15 / G34 / G14 |
| D 回测引擎 | G06 → G20 → G32 |
| E Agent 取数 | G07 → G22；穿插 G13 → G26 |
| F 运维扩展 | G05 → G24；穿插 G08 → G25 与 G10 / G11 / G12 |
| G 前端集成 | G09 → G27；穿插 G35 |
| H 收尾审查 | G36 |

- 每步完成后：涉及后端跑 `pytest` 相关用例；涉及前端保证 `build` 通过；同步更新 `docs/Agent_backend/api-docs.md` 或 `docs/Agent_frontend/Agent_code.md`；做六要素自查（可维护/可扩展/可演进/稳定/可观测/可部署）。
- P0-10(G20) 修复前后用同一策略对比胜率/收益差异并记录到 `fixed.md`。
- P1-12(G31) 验证通过前**保留 Chroma 与迁移脚本作为回滚路径**，验证通过后才删 `data/chroma/` 与 chromadb 依赖。
- G36 上线前跑通全量回归 + 恢复演练(P1-1)确认可回滚。
