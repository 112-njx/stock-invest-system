# V0.3 开发参考指南 — 16 项生产级优化

> V0.3 核心目标：将 V0.1+V0.2 的功能从"个人 Demo 可用"升级为"可交付真实用户的生产级作品"。
> 共 16 项优化，分两大类：前端修改/功能增加（12 项）、底层架构优化（4 项）。
> 每项包含「说明」（优化什么）和「优化方案」（具体怎么做），开发前必须阅读对应条目。

---

## 一、前端修改 / 功能增加（12 项）

### 1.1 用户可见的新功能（8 项）

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
- **per-user 日 token 配额**：Redis 计数器 `ai_usage:{user_id}:{date}`，每次 AI 调用累加 prompt+completion token，超过日配额返回 429
- **配额配置**：默认免费用户日配额 50K tokens（环境变量 `AI_DAILY_TOKEN_LIMIT`），预留 `user_ai_quota` 表支持付费配额
- **用量统计**：`user_usage` 表日维度汇总（user_id, date, ai_calls, ai_tokens, ai_cost_estimate, backtest_count），Celery 每日凌晨聚合
- **新增端点**：
  - `GET /api/v1/ai/usage` — 返回今日已用/总额度/剩余
  - `GET /api/v1/admin/usage` — 全用户用量排行、总成本统计（管理员）
- **响应头**：`x-ai-usage` 返回实时用量（prompt/completion/total）
- **前端**：AI 页底部显示今日用量进度条（已用/总额），超额时输入框禁用并提示"今日额度已用完，明日重置"

---

### P0-3 记忆数据隐私
### 待修改
**说明**：需求文档承诺"记忆文件保存在用户本地"，实际存储在服务端 `data/memory/` 和 `data/chroma/`，明文无加密。属于虚假承诺且存在数据泄露风险（服务器被入侵=所有用户交易体系泄露）。V0.3 采用方案 B（改承诺+加密），方案 A（浏览器本地化）列为未来增强。

**优化方案**：
- **明确产品定位**：用户协议和隐私政策中说明"记忆数据存储在服务端并加密存储"，移除所有"本地存储"表述
- **记忆文件加密**：AES-256-GCM 加密 `data/memory/{user_id}/` 下所有文件，加密密钥从环境变量 `MEMORY_ENCRYPTION_KEY`（32 字节随机）读取，写入时加密、读取时解密
- **ChromaDB 加密**：记忆文本 content 字段在写入 ChromaDB 前加密存储；向量保持明文（相似度计算需要）；ChromaDB 持久化目录权限设为 `0700`
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
### 待修改
**说明**：当前 AI 输出包含具体买卖建议，无用户协议/隐私政策/免责声明页面，无注册强制同意流程，无底部版权信息。存在法律合规风险（无牌照提供投资建议、无隐私政策违反个保法）。

**优化方案**：
- **法律页面**：新增 `/terms`（用户协议）、`/privacy`（隐私政策）、`/disclaimer`（免责声明）三个静态页面
  - 用户协议：服务条款、用户行为规范、知识产权、免责条款、争议解决
  - 隐私政策：收集信息类型、使用方式、存储方式、用户权利（访问/更正/删除）、数据安全措施
  - 免责声明：明确"本产品为研究辅助工具，不构成投资建议，AI 输出仅供参考，投资决策风险自负"
- **注册强制同意**：注册页增加"我已阅读并同意《用户协议》《隐私政策》《免责声明》"勾选框（默认不勾选），未勾选不能注册
- **AI 输出免责声明**：每次 AI 回复末尾自动追加固定文本"以上分析由 AI 生成，仅供研究参考，不构成投资建议。投资有风险，决策需谨慎。"
- **产品定位声明**：关于页明确标注"本产品为量化研究辅助工具，非证券投资咨询服务"
- **底部版权信息**：所有页面底部固定显示"© 2026 stock-invest-system | 免责声明 | 隐私政策"链接
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
  - 硬删除：级联删除所有关联数据（watchlist/support_resistance/strategies/backtest/conversations/chat_messages/agent_runs/agent_steps/memory_chunks/user_memory_files/user_sessions/user_usage），删除 ChromaDB 中该用户 collection，删除 `data/memory/{user_id}/` 目录
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

## 二、底层架构优化（4 项）

> 以下 4 项纯后端/运维，用户不可见，属于基础设施加固。

---

### P1-1 备份 + 灾难恢复

**说明**：当前无数据库自动备份、无 Redis 持久化确认、ChromaDB/记忆文件无备份，服务器故障或误操作可导致全部用户数据永久丢失。PostgreSQL 有约 680 个 K线分区子表，手动恢复极其困难。

**优化方案**：
- **PostgreSQL 备份**：
  - 每日全量备份：`pg_dump -Fc stock_invest > /backup/pg/full_$(date +%Y%m%d).dump`，保留最近30天
  - WAL 归档：`archive_mode=on, archive_command`，WAL 归档到 `/backup/pg/wal/`，支持 PITR（时间点恢复）
  - 备份脚本 `scripts/backup_pg.sh`，纳入 Celery beat 每日凌晨 2:00 执行
  - 每周自动恢复到临时库验证备份完整性（`scripts/verify_backup.sh`）
- **Redis 持久化**：启用 AOF（`appendonly yes, appendfsync everysec`）+ RDB 快照（`save 60 1000`），Redis 数据目录纳入文件备份
- **文件备份**：`data/memory/`、`data/chroma/`、导出文件目录每日 rsync 到 `/backup/files/`，保留最近7天
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

## 三、实施依赖与建议顺序

### 强依赖关系

```
P1-8(邮件服务) ──→ P0-4(密码找回/邮箱验证)
P0-7(Cookie安全) ──→ P0-1(双token) ──→ P0-5(WS鉴权)
P0-7(CSP头) ──→ P0-6(XSS防护)
P0-8(法律页面) ──→ 登录页改造(注册协议勾选)
P1-1(备份) ──→ P1-3(数据库时区迁移，迁移前需备份)
```

### 建议实施批次

| 批次 | 包含项 | 说明 |
|---|---|---|
| 第一批（安全地基） | P0-7, P0-1, P0-5, P0-6 | 鉴权安全一体化改造，共享 Cookie/CSP 基础设施 |
| 第二批（合规+账户） | P0-8, P1-8, P0-4, 登录页改造 | 法律页面+邮件服务+密码找回+登录页重构，互相依赖 |
| 第三批（数据+成本） | P0-3, P0-2, P1-5 | 记忆加密+AI限流+数据导出删除 |
| 第四批（性能+运维） | P1-6, P1-1, P1-3, P1-4, P1-2 | 分页+备份+时区+沙箱+水平扩展 |

### 注意事项

1. 每批开发前必须重新阅读本文件对应条目，确保方案理解一致
2. P1-3（数据库时区迁移）执行前必须先完成 P1-1（备份），迁移风险高
3. P0-1/P0-5/P0-7 三者共享鉴权基础设施，必须同一批次连续开发，禁止拆分
4. 登录页改造（方案 B）涉及路由重构，需确保所有页面的未登录态都有处理，不能出现白屏
5. 所有新增端点必须写入 `docs/Agent_backend/api-docs.md`，所有前端组件变更写入 `docs/Agent_frontend/Agent_code.md`
