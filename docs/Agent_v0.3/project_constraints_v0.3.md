# V0.3 开发拓扑关系与并行约束

> 本文件记录 V0.3 多 agent 并行开发的拓扑关系（依赖图、波次、关键路径）、泳道分配与文件冲突协调规则。
> 任何 agent 开工前必须阅读本文件：确认自己负责步骤的前置已满足、不与其它步骤串改同一文件簇。

---

## 一、修订版依赖关系图（Reference_guide_v0.3.md 4.2）

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

## 二、并行波次与关键路径（4.4）

| 波次 | 步骤（可并行） | 说明 |
|---|---|---|
| 波次 0 | G01~G18、G28（19 步） | 全部无前置，可同时开 N 路 |
| 波次 1 | G19~G27（9 步） | 各依赖波次 0 的单个步骤 |
| 波次 2 | G29~G34（6 步） | 二级依赖 |
| 波次 3 | G35、G36 | 集成与收尾 |

- **关键路径**：`G01→G19→G29→G35→G36`（5 跳）、`G04→G21→G31→G34→G36`（5 跳）、`G06→G20→G32→G36`（4 跳）。
- **不会空转保证**：每步只依赖"前置编号"，agent 认领前检查前置是否全绿；波次 0 提供 19 个可立即开工步骤。

## 三、建议任务分配泳道（4.7，可自由调整）

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

同一泳道内**必须按序列顺序开发**（后一步依赖前一步产出）；不同泳道之间只有"前置编号"约束，可并行。

## 四、前端文件冲突协调（4.5，防串改）

多个前端步骤写入同一文件簇，**必须单 owner 串行集成**，否则 merge 冲突：

1. **个人设置页（单组件）**：被 G14(APIKey)、G15(存储说明)、G19(设备管理)、G33(改密/邮箱)、G18(账户删除) 汇聚 → 按子区块拆分，由最后合入者统一合并。
2. **顶部导航栏**：G16(铃铛) 与 G35(头像弹窗) → 协调合并顺序。
3. **路由 `router/index`**：G03(法律页路由) 与 G35(登录路由重构) → G35 后集大成者，最后合入。
4. **登录/注册组件**：G33、G35、G03(协议勾选) → 同 G35 收口。

## 五、已定稿决策（原 4.6 待确认项）

1. **P1-8b 系统公告"管理员账号"** → 已定稿：沿用 `ADMIN_USERNAMES` 环境变量 + 正常注册。部署时环境变量配置管理员用户名列表（逗号分隔），这些用户注册后自动获得 `is_admin`；G16 管理员发布端点正常实现，不再挂起。
2. **登录页改造(G35)"视觉重设计"** → 已定稿：规格书 `docs/Agent_v0.3/login_page_design_v0.3.md`（参考图 login_pic.png），G35 视觉严格按此实现。
3. **P0-2 简化版"用量统计"** → 已定稿：保留 token 用量显示（按 usage 字段估算，非精确计费），不做服务端限流/额度分层。
4. **P0-7 CORS 白名单域名** → 已定稿：域名暂未购买，一律用环境变量 `CORS_ORIGINS` 占位，禁止硬编码通配/具体域名，后续购买后填写。

## 六、泳道 A（安全鉴权）工作范围

- 步骤序列：**G01 → G19 → G29 → G30**（严格按此顺序，每步完成并验证后再开始下一步）
- 所属项：P0-7(HTTPS/Cookie/CORS) → P0-1(双token) → P0-5(WS鉴权) → P0-6(XSS/隔离)
- 类型：G01 全栈·运维 / G19 后端 / G29 全栈 / G30 全栈
- 前置：G01 无前置（波次 0）；G19 依赖 G01；G29 依赖 G19；G30 依赖 G01
- 涉及的共享文件簇（注意与其它泳道协调）：
  - `app/core/security.py`、`app/api/v1/auth.py`（G19 独占主改）
  - `app/main.py`（CORS 白名单，G01；注意与 G03/G16 等不冲突）
  - `nginx` 配置（HTTPS/响应头/WS 脱敏，G01+G29）
  - 前端 `src/api/http.ts` / axios 实例（G01 改 withCredentials，G19 改 401 自动 refresh）
  - 前端 `src/utils/wsClient.ts`（G29 去 token）
  - 前端个人设置页（G19 设备管理入口，与 G14/G15/G33/G18 汇聚，按子区块拆分）

## 七、通用收尾要求（4.8）

- 每步完成后：涉及后端跑 `pytest` 相关用例；涉及前端保证 `build` 通过；同步更新 `docs/Agent_backend/api-docs.md` 或 `docs/Agent_frontend/Agent_code.md`；做六要素自查（可维护/可扩展/可演进/稳定/可观测/可部署）。
- 所有新增端点必须写入 `docs/Agent_backend/api-docs.md`，所有前端组件变更写入 `docs/Agent_frontend/Agent_code.md`。
- P0-9/P0-10 修复须先补可复现回归测试再改实现；P0-10 修复前后用同一策略对比胜率/收益差异并记录到 fixed.md。
- 禁止在 async/Agent 链路新增 `time.sleep`、`requests` 等同步阻塞调用（P1-9 约束）。

---

## 八、需人类操作配置事项（各泳道发现即追加，标清序号+泳道）

1. **【泳道 C · G04】本地 PostgreSQL 缺少 pgvector 扩展，迁移 0009 无法执行**
   - 现象：`alembic upgrade head` 在 0009 报 `extension "vector" is not available`；本地 `memory_chunks.embedding` / `embedding_kind` 列缺失，导致 `test_memory.py` 5 个用例 + `test_agent_ops.py` 1 个用例失败（340 passed / 5 failed / 6 skipped）。
   - 原因：pgvector 需预装在 PG 实例中，本机原生 PostgreSQL 未安装。
   - 需人工操作：本机 PostgreSQL 安装 pgvector（Windows 可下载预编译包或改用 `pgvector/pgvector:pg16` 容器库），然后执行 `alembic upgrade head` 补 0009~0012。
   - 临时绕过（仅供本地开发验证）：手工 `ALTER TABLE` 补列，不作为正式方案。

2. **【泳道 B · G23】注册接口 `email` 已改为必填，所有测试注册夹具已同步更新**
   - 影响：任何外部调用 `/api/v1/auth/register` 的地方必须带 `email`，否则 422。
   - 需人工操作：无（代码内已同步），但前端注册页需在 G33 补邮箱必填校验。

3. **【泳道 B · G02/G23】SMTP 凭据未配置，邮件走模拟模式**
   - 现象：`SMTP_HOST` 为空时邮件不真发，落盘到 `stock_backend/data/email_outbox/*.eml`，日志标注 `[SIMULATED]`。
   - 需人工操作：部署时配置 `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `SMTP_FROM_EMAIL`（`SMTP_USE_TLS=true` 走 587 STARTTLS，`false` 走 465 SSL），否则邮箱验证/密码重置链接无法真实送达。

4. **【泳道 D · G20】回测撮合现实性参数为代码默认值，尚未接入环境变量配置**
   - 现状：`BacktestConfig.slippage_pct` 默认 `0.0`（无滑点）、`max_volume_pct` 默认 `1.0`（不限制成交量占比），二者仅在引擎内可配，未暴露为 `.env` 配置项，也未接入回测 API 请求参数。
   - 影响：生产环境若需要更贴近真实的撮合（如 0.1% 滑点、单笔不超过成交量 10%），当前只能改代码。
   - 需人工确认：是否需要新增 `BACKTEST_SLIPPAGE_PCT` / `BACKTEST_MAX_VOLUME_PCT` 环境变量（默认值保持与现在一致以保证向后兼容），并允许 `POST /api/v1/backtest` 按次覆盖。确认后由泳道 D 在后续步骤补配置与端点参数。

5. **【泳道 D · G20】涨跌停判定依赖 K 线形态，建议数据源补显式标记**
   - 现状：引擎按「一字板」形态（`open == high == low == close`）判定涨跌停并拒绝买入/卖出；若 bar 数据带 `limit_up` / `limit_down` 显式布尔字段则优先采用。
   - 影响：盘中打开涨停后回落（非一字板）不会被判定为涨停，仍可买入——属当前口径的有意取舍（避免误拦正常收盘价等于最高价的交易日）。
   - 需人工确认：行情同步层（`kline` 表）是否需要新增涨跌停标记字段。注意本项目禁止直接改表结构，若需新增须走 Alembic 迁移；当前不改表，保持一字板判定。

6. **【泳道 A · G01】CORS 白名单域名未配置（生产）**
   - 现状：`CORS_ORIGINS` 开发默认 `http://localhost:5173,http://localhost:8081`（含 127.0.0.1 同端口），已按 4.6 定稿要求改为环境变量白名单，代码内无任何硬编码通配或具体域名。
   - 影响：生产部署若不配置该变量，`allow_credentials` 会因白名单为空而自动关闭（安全降级），前端跨域带 Cookie 的请求将失败。
   - 需人工操作：域名购买后在 `.env.docker` 设置 `CORS_ORIGINS=https://<实际域名>`（多个用逗号分隔）。

7. **【泳道 A · G01】Nginx TLS 证书路径未提供，HTTPS 尚未启用**
   - 现状：`deploy/nginx/nginx.conf` 已写好完整 443 server 块（TLS 1.2/1.3 + 五项安全响应头），但处于注释状态；80 端口已预留 `SSL_REDIRECT` 环境变量控制的 301 重定向分支。五项安全响应头（HSTS/CSP/X-Frame-Options DENY/nosniff/Referrer-Policy）在 HTTP 下已生效。
   - 需人工操作（证书就位后四步）：① 将 `fullchain.pem` / `privkey.pem` 挂载到容器 `/etc/nginx/certs/`（取消 `deploy/docker-compose.yml` 中 nginx volumes 的证书注释）；② 取消 `nginx.conf` 中 443 server 块全部注释；③ `.env.docker` 设 `SSL_REDIRECT=true`；④ `.env.docker` 设 `COOKIE_SECURE=true`（否则 HTTPS 下 refresh Cookie 不会被浏览器接受）。之后重建 nginx 容器。
   - 注意：开发环境（vite dev / docker-compose.dev.yml）保持 HTTP，不受影响。

8. **【泳道 A · G19】user_sessions 表需执行 Alembic 0010（依赖 G04 的 0009 先完成）**
   - 现状：新增迁移 `stock_backend/alembic/versions/0010_user_sessions.py`（revision 0010 / down_revision 0009）。本地因第 1 条 pgvector 阻塞，0009 未执行，0010 也随之未执行；已临时手工建表供本地测试。
   - 需人工操作：解决第 1 条 pgvector 后执行 `alembic upgrade head`，一次性补齐 0009~0012（含 user_sessions 表与两个索引）。回滚方案：`alembic downgrade 0009`（脚本内含 drop index + drop table）。
   - 附注：G19 新增环境变量均有默认值，无需配置——`ACCESS_TOKEN_EXPIRE_MINUTES`(15) / `REFRESH_TOKEN_EXPIRE_DAYS`(7) / `REFRESH_TOKEN_COOKIE_NAME`(refresh_token)。
