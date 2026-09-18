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

> **泳道 F 范围变更（2026-09-17，已确认）**：**G24（P1-3 数据库时区统一）经决策跳过、不实施**，泳道 F 主序列实际为 `G05 →（结束）`；穿插步骤 `G08 → G25` 与 `G10 / G11 / G12` 照常执行。决策依据、已知代价与重做要点见第八节第 19 条。

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

1. **【泳道 C · G04】本地 PostgreSQL 缺少 pgvector 扩展，迁移 0009 无法执行 —— 已解决（改用容器库）**
   - 现象：`alembic upgrade head` 在 0009 报 `extension "vector" is not available`；本地 `memory_chunks.embedding` / `embedding_kind` 列缺失，导致 `test_memory.py` 5 个用例 + `test_agent_ops.py` 1 个用例失败（340 passed / 5 failed / 6 skipped）。
   - 原因：pgvector 需预装在 PG 实例中，本机原生 PostgreSQL 18.4 未安装，且本机无 MSVC（pgvector 的 `Makefile.win` 构建必需），无法就地编译。
   - **已采取的方案**：本地开发/测试改用容器库 `pgvector/pgvector:pg16`（两个 compose 的 db 镜像已替换；dev compose 的 db 端口默认映射 `127.0.0.1:5433`）。`stock_backend/.env` 的 `DATABASE_URL` 已指向 5433。迁移 0009~0012 已应用，G04 测试 11/11 全绿。
   - 需人工操作（新环境/换机时）：`docker compose --env-file .env.docker -f deploy/docker-compose.dev.yml up -d db` 启动容器库，再 `alembic upgrade head`。本机原生 PG 18（5432）保留作只读排查，不再作为开发库。
   - 遗留（低优先，可选）：若希望恢复原生 PG 工作流，需安装 VS Build Tools 后用 `nmake /F Makefile.win` 编译安装 pgvector；不建议从非官方源取预编译 DLL。

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

10. **【泳道 A · G19/G29】Cookie 回退鉴权导致 9 个「未登录应 401」用例失败 —— 已解决**
   - 现象：全库 `pytest` 9 failed / 353 passed。失败用例均为断言「不带 Authorization header 应返回 401」的接口（test_strategies::test_generate_api、test_sse::test_resume_endpoint_ownership、test_chat::test_chat_api_stream_and_requires_token、test_conversations::test_messages_order_and_symbol、test_research_graph::test_deep_chat_records_agent_steps、test_agent_ops::test_agent_runs_ownership_and_auth、test_catalog_search::test_search_fuzzy_prefers_synced_over_catalog、test_ws_market::test_ws_rejects_without_token/bad_token）。
   - 根因：G19（提交 d8e1abb）在 `app/api/deps.py::_extract_token` 增加 Cookie 回退（`request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)`），且登录/注册响应下发 access_token Cookie；FastAPI TestClient 在同一测试会话内持久化 Cookie，导致先 register 再「无 header」请求时被 Cookie 认证通过 → 期望 401 实得 200。WS 两项为 G29 进行中的 WS 鉴权改造（query token → Cookie）所致。
   - **解决**：泳道 A 后续提交已修正（全库 `pytest` 现为 **417 passed / 0 failed**）。
   - 需人工操作：无。

9. **【泳道 D · G32】`backtest_service.py` 被两条泳道并发编辑（提交时已如实披露）**
   - 现象：G32 编码期间，`stock_backend/app/services/backtest_service.py` 的工作区同时存在两套未提交改动——G32 的 `_serialize_curve/_serialize_trades/_realized_pnl_by_sell` + `execute_backtest` 落库调用，以及**泳道 B/G16（P1-8b）的 `_notify_backtest_done` 站内通知**（回测成功/失败写通知）。另 `app/schemas/backtest.py` 混入 G30（P0-6）给 `BacktestCreateIn.symbol` 加 `max_length=32` 的输入长度校验。
   - 影响：两套改动落在同一文件的不同区域，无 merge 冲突，功能共存（回测四文件 49 项全绿）。但 G32 的提交会把上述两条**尚未提交的跨泳道改动一并带入**。
   - 处理：G32 **未回退任何他人改动**（避免破坏在途工作），提交时在 commit message 中明确标注该文件含 G16/G30 的在途改动，并已在本条记录。相关泳道如需拆分提交，请以其自身 commit 为准。
   - 需人工确认：无（信息同步项）。

10. **【泳道 D · G32】K 线买卖点标注的 15m 周期覆盖范围受 `/kline` 默认 limit 限制**
   - 现状：前端 K 线图调 `/api/v1/kline` 使用默认 `limit=1000`，而回测取 K 线上限为 50000 根。日K 2 年约 500 根可完整覆盖；**15m 周期 2 年约 8k 根，超出 1000 的部分其买卖点会被前端裁剪掉不显示**（`KLineChart.drawMarkers` 按已加载 bar 时间范围过滤，不会报错、不会错位）。
   - 影响：15m 回测的买卖点只显示最近约 1000 根 bar 区间内的部分，属**展示不完整**而非错误。日K/周K/月K 不受影响。
   - 需人工确认：是否需要为「查看买卖点」场景把 `/kline` 的 limit 提高到覆盖回测区间（或让前端按回测 `start_ts/end_ts` 传参）。当前为有意取舍（避免一次性拉 8k 根影响图表性能），待确认后由泳道 D 在后续增量处理。
   - 附注：本轮已一并完成的增量项——止损/止盈异形标记、hover 显示成交价/数量/费用/触发原因、交易明细表（含后端产出的逐笔已实现净盈亏）。**仍留待后续的增量**：交易明细与图表的高亮联动（点击明细行定位到 K 线对应位置）。

11. **【泳道 B · G02】测试夹具用全量建表导致跨泳道 JSONB 编译失败 —— 已解决**
   - 现象：`test_email_service.py` 8 个用例 setup ERROR，`sqlalchemy.exc.CompileError: (in table 'backtest_results', column 'equity_curve'): SQLiteTypeCompiler can't render element of type JSONB`。
   - 根因：该测试的 `db_session` 夹具用 `Base.metadata.create_all(engine)` 在内存 SQLite 建**全部**表；泳道 D G32 给 `backtest_results` 新增了 JSONB 列，SQLite 无法渲染 → 编译期报错。非生产代码回归，属测试夹具作用域过宽。
   - **解决**：夹具改为只建本模块用到的表（`EmailLog.__table__.create(engine)`）。已恢复 16/16 全绿。
   - 需人工操作：无。**经验**：新增使用内存 SQLite 的测试时，禁止 `Base.metadata.create_all()` 全量建表，只建所需表。

11. **【本地开发环境】Redis 容器需手动启动，否则缓存/SSE/同步类用例大面积失败**
   - 现象：`stock-redis` 容器 Exited 时，`test_sse`/`test_market_cache`/`test_sync_service` 等 Redis 依赖用例失败，且 pytest 因连接重试耗时从 ~85s 膨胀到 ~20 分钟。
   - 需人工操作：跑后端测试前先 `docker start stock-redis`（或确保 Docker Desktop 已启动容器）。本地 DB 同理：dev 库现为容器 `pgvector/pgvector:pg16`（127.0.0.1:5433）。

13. **【泳道 B · G16/G18】`test_research_graph.py::test_deep_chat_records_agent_steps` 偶发失败（时序敏感，非回归）**
   - 现象：全库 `pytest` 偶现该用例失败（449 passed / 1 failed），单跑该文件或单跑该用例均通过；紧接重跑全库即 450 passed / 0 failed。
   - 根因：该用例直接调 `chat_service.stream_chat` 并断言 5 个节点各产 1 个 delta，链路内含基于**真实墙钟**的三级超时（首字 30s / 单 delta 15s / 总 120s）。全库高负载时偶发触及超时分支，delta 数不足。
   - 影响：仅测试稳定性，非功能回归（生产环境超时阈值同样宽松，且超时行为本身是设计目标）。
   - 建议（属该用例 owner）：断言放宽为「delta 数 ≥5 或含 done(truncated) 时跳过」，或为流式超时注入可控时钟。本轮未改他人测试文件。
   - 需人工操作：无。

14. **【泳道 C · G31】记忆模块 Chroma 下线在途，`CHROMA_DIR` 配置项已删但代码/测试仍引用 —— 已解决**
   - 现象：全库 `pytest` 20 failed / 465 passed，失败集中在 `test_memory.py` 与 `test_memory_dual_write.py`，报 `AttributeError: Settings(...) has no attribute 'CHROMA_DIR'`。
   - 根因：G31（Chroma→pgvector 下线）从 `config.py` 移除了 `CHROMA_DIR`，但 `app/agent/memory/store.py`、`scripts/rebuild_embeddings.py`、`tests/test_memory*.py` 中仍有引用。属该泳道**未完成的在途改动**（工作区未提交）。
   - **解决（2026-09-17 由泳道 B 复核确认）**：泳道 C 已自行完成清理——`store.py` / `scripts/rebuild_embeddings.py` 不再引用该配置，`chroma_legacy.py` 与 `tests/test_memory_dual_write.py` 已下线删除，`config.py` 与 `store.py` 仅保留两条说明性注释（记录迁移事实，属正确文档）。复核后 `tests/test_memory.py` 19/19 全绿。
   - 泳道 B 附带清理：删除仓库内残留的过期 `.pyc` 缓存（`tests/__pycache__/test_memory_dual_write.*.pyc`、`app/agent/memory/__pycache__/chroma_legacy.*.pyc` 及全仓 `__pycache__`）。
   - 需人工操作：无。

15. **【泳道 F · G05】备份目录与异地对象存储凭据未配置，异地备份处于模拟模式**
   - 现状：`BACKUP_DIR` 默认落 `backenddata` 卷内（`/app/data/backups`），与数据**同盘**——数据盘损坏会同时丢数据和备份；`RCLONE_REMOTE` 为空时异地同步进入模拟模式（日志 `[SIMULATED]`，只记清单不真同步，任务不算失败）。
   - 需人工操作（两步）：
     ① **备份盘独立**：在 `.env.docker` 设 `BACKUP_DIR=/backup`，并给 `deploy/docker-compose.yml` 的 `api`/`worker` 两个服务各加一条绑定挂载 `- /mnt/backup:/backup`（宿主机独立磁盘）。**改 `BACKUP_DIR` 必须同时挂载对应路径**，否则备份写进容器可写层，容器重建即丢。
     ② **异地备份**：`.env.docker` 设 `RCLONE_REMOTE=oss:<bucket>`（或 `s3:` 等），凭据用环境变量传（`RCLONE_CONFIG_<REMOTE>_ACCESS_KEY_ID` / `_SECRET_ACCESS_KEY` / `_ENDPOINT` 等，**勿写进 compose 或代码**）。配置后执行 `bash stock_backend/scripts/backup_pg.sh offsite` 验证一次。
   - 附：保留期 90 天由同步后自动执行的 `rclone delete <remote> --min-age 90d` 实现。

16. **【泳道 F · G05】WAL 归档需重建 db 容器才生效（存量环境）**
   - 现状：两个 compose 的 `db` 已配 `archive_mode=on` + `wal_level=replica` + `archive_timeout=300` + `archive_command` 写 `/wal-archive`，并配了一次性 sidecar `wal-init`（把归档卷属主改成 postgres:999 —— 该卷由 Docker 以 root 创建，不改属主 `archive_command` 会持续失败，已实测）。
   - 需人工操作：**已存在的 dev/生产 db 容器需重建才生效**：`docker compose --env-file .env.docker -f deploy/docker-compose.dev.yml up -d --force-recreate db`（数据在 `pgdata` 命名卷内，重建不丢）。重建后校验：
     `docker exec <db容器> psql -U postgres -tAc "select archived_count, failed_count from pg_stat_archiver"` —— `failed_count` 必须为 0。
   - 注意：**本步未对正在运行的 dev 库执行重建**（避免打断其它泳道并发的测试），归档配置已用一次性容器实测验证通过（`archived_count=2 / failed_count=0`）。

17. **【泳道 F · G05】本机无 PG 客户端，备份/恢复经 docker exec 借用 db 容器**
   - 现状：本机（Windows 开发机）`pg_dump`/`psql` 均不在 PATH，`C:\Program Files\PostgreSQL` 不存在；`BACKUP_PG_DUMP_MODE=auto` 会自动退回 `docker exec -i <容器> pg_dump`，`BACKUP_PG_CONTAINER` 默认 `stock-invest-dev-db-1`。生产容器内已装 `postgresql-client-16`（PGDG），走 local 模式。
   - 需人工操作：无（本地开箱可用）；若容器名不同，在 `.env` 设 `BACKUP_PG_CONTAINER=<实际名>`。
   - 附：**pg_dump 客户端主版本必须 ≥ 服务端主版本**（本项目服务端 PG16）；若镜像构建时 PGDG 源不可达会自动回退发行版 client-15，此时备份任务会在 `check_client_version()` 明确失败并提示，不会产出坏备份。

18. **【泳道 F · G05】行情新鲜度指标一直采集失败 —— 已修复（2026-09-18，G24 跳过后的兜底修复）**
   - 现象：`/metrics` 抓取时日志报 `market freshness collect failed: can't subtract offset-naive and offset-aware datetimes`，`market_data_freshness_seconds` 指标**从未真正上报**，`MarketDataStale` 告警规则因此永不触发（监控盲区）。
   - 根因：`app/core/metrics_ext.py::_refresh_market_freshness` 用 `datetime.now(UTC) - row`，而 `snapshot_realtime.updated_at` 是 naive（`timestamp without time zone`），aware 减 naive 抛 TypeError。属 P1-3（G24 时区统一）的典型症状，非 G05 引入。
   - **危险点（比报错更严重）**：异常被 `except` 吞掉只记 warning，Gauge 又保留初始值 **0.0** —— 指标对外显示"0 秒前"（最新），实际采集从未成功；前端"数据新鲜度"与 Grafana 面板同时被误导，且告警永不触发。
   - **修复**（G24 决策跳过后按用户指示做最小修复，不碰表结构/迁移）：① 用 `app/utils/market_cache.py::as_utc()` 先把 DB naive 时间戳按 UTC 补时区再相减（`data_age_seconds` 早已如此，全仓已确认仅此一处裸相减）；② 采集异常时置 `NaN`（Prometheus 的"未知"）而非保留旧值，使失败可辨别。
   - **实测**：修复前恒为 `0.0`；修复后 `1862853s`（≈21.6 天，即 dev 库快照的真实数据龄）。回归测试 `tests/test_metrics_ext.py` 新增 2 项，4/4 全绿。详见 `docs/Agent_backend/fixed.md`（2026-09-18 条）。
   - 需人工操作：无。
   - 附：第 19 条列出的另外两项代价（非 UTC+8 部署的静默错误、新代码仍需 `as_utc()` 归一）**不受本修复影响，仍然存在**。

19. **【泳道 F · G24 决策】P1-3 数据库时区统一（naive → timestamptz）经确认不做 —— 本轮跳过**
   - **决策**（2026-09-17，用户确认）：产品暂不解决数据库时区统一问题，**G24 整体跳过**——迁移脚本、`as_utc()` 清理、连接时区 UTC、抽样验证与回滚四簇均不实施。
   - **现状保持**：K线 `ts` / 快照 `updated_at` 等仍为 `timestamp without time zone`（naive），代码层继续用 `as_utc()` 归一规避；`sync_tasks` / `backtest_tasks` / `agent_runs` / `agent_steps` / `memory_chunks` 等表时间列不变。G05（备份）已落地，但其"迁移前全量备份"的角色在本轮不再被使用。
   - **已知代价（需知晓，非阻塞）**：
     ① **行情新鲜度指标失效**——`metrics_ext._refresh_market_freshness` 用 `datetime.now(UTC) - snapshot_realtime.updated_at`（aware 减 naive）抛 TypeError，`market_data_freshness_seconds` 从未真正上报，`MarketDataStale` 告警规则**永不触发**（监控盲区）。详见第 18 条。
     ② 开发环境全东八区（Asia/Shanghai），症状不明显；**若未来部署到非 UTC+8 时区，或改动容器/DB 的 timezone 设置**，Reference_guide P1-3 列出的静默数据错误会重新出现：缓存失效时间错误、WS 增量推送丢数据/重复、`data_age_seconds` 计算错误、回测区间偏移（均不报错但结果错）。
     ③ 第三方或后续开发者若按"DB 里是 timestamptz"的常规假设写新代码（如直接做 aware/naive 运算、或依赖 ORM 返回 aware datetime），会踩到同类 TypeError——**新代码处理这些时间列时仍需 `as_utc()` 归一**。
   - **触发重做的条件（建议）**：① 部署到非 UTC+8 时区；② 需要修复第 18 条的监控盲区；③ 实际出现上述静默数据错误。
   - **重做要点（供后续 agent，避免重复调研）**：
     - 迁移编号须用 **0016**——规划文档写的 `0005_timezone_fix.py` 已被 `0005_memory_importance` 占用，当前 alembic head 为 **0015**（泳道 B 的 export_tasks）。
     - 存量转换 `USING column AT TIME ZONE 'UTC'` 前**必须先抽样验证存量确为 UTC**（本机开发库未做该验证，是重做时的第一个卡点）。
     - K 线为**分区表**：父表 `kline_15m` / `kline_1d` / `kline_1w` / `kline_1mon`，实测 public schema 共 372 张表（规划文档"约 680 子表"为旧数），需 DO 块循环 ALTER 各子分区。
     - 迁移前须有 G05 的全量备份 + 恢复演练通过（本步已具备：`docs/ops/disaster_recovery.md` 第 3、4 节实测可执行）。
   - **需人工操作**：无。

20. **【泳道 F · 全泳道通用】`git push` 走 SSH 被拒（publickey）—— 已定位并解决：私钥带口令，非交互调用抑制了口令提示**
   - 现象：`git push origin main` 报 `git@ssh.github.com: Permission denied (publickey)`；`ssh -T git@github.com` 与显式 `-i ~/.ssh/id_ed25519` 均同样被拒。
   - **真实根因（已实测确认，与第 22 条的判断相反）**：`~/.ssh/id_ed25519` **已登记在 GitHub 账号上，且工作正常**——它是一把**带口令（passphrase）的私钥**。非交互式调用（agent 环境无 TTY、以及我最初用的 `ssh -o BatchMode=yes`）会**抑制口令提示**，ssh 找不到可用身份便统一报 `Permission denied (publickey)`，**这个报错具有误导性**：它既表示"key 未授权"，也表示"key 有口令但拿不到口令"。**以后遇到该报错不要直接断定公钥未登记**。
   - **验证与解决（实测通过）**：把私钥加载进 `ssh-agent` 后 SSH 立即恢复：
     ```
     eval "$(ssh-agent -s)"
     ssh-add ~/.ssh/id_ed25519        # 交互式输入口令；非交互场景可用 SSH_ASKPASS + SSH_ASKPASS_REQUIRE=force
     ssh -T git@github.com            # → Hi 112-njx! You've successfully authenticated
     ```
     本次由用户提供口令后加载成功，`git ls-remote origin` / `git fetch origin` 均正常，SSH remote 已可用。
   - **注意（本次会话的 agent 为一次性 daemon）**：ssh-agent 进程在会话结束后消失，下次仍需 `ssh-add` 重新加载（口令不落盘，这是 ssh-agent 的设计意图）。若希望免口令推送，见下方"可选人工操作"。
   - 本轮绕过方式（**已不再需要，仅作备用**）：显式 HTTPS URL 推送，凭据由 Windows 凭据管理器（`credential.helper=manager`）提供，已验证可用：
     `git push https://github.com/112-njx/stock-invest-system.git main`
     全程未修改 `origin` remote、未改 `~/.ssh/*`。
   - 可选人工操作（二选一，均非阻塞）：
     ① **免口令**：`ssh-keygen -p -f ~/.ssh/id_ed25519` 把口令改空（**降低安全性**，本机私钥泄露即可直接推代码，不建议）；
     ② **改走 HTTPS**：`git remote set-url origin https://github.com/112-njx/stock-invest-system.git`（凭据已在凭据管理器，免口令）。
   - ⚠️ **安全提醒**：口令已在对话中明文出现，建议尽快 `ssh-keygen -p -f ~/.ssh/id_ed25519` **更换口令**（保持非空），或轮换该密钥对。

20. **【泳道 C · G15/G34】MEMORY_ENCRYPTION_KEY 未配置 —— 生产必须配置（开发环境已临时配置）**
   - 现状：G15（记忆文件加密）/ G34（memory_chunks.content 加密）均使用 AES-256-GCM，密钥从环境变量 `MEMORY_ENCRYPTION_KEY` 读取（32 字节随机，64 位 hex）。按约束 5「未配置前用环境变量占位，禁止硬编码密钥」，`config.py` 中该字段默认空串，**代码内无任何硬编码兜底**；未配置时加密写入直接抛 `EncryptionKeyMissing`（不会静默降级为明文）。
   - **已为本机开发环境生成随机密钥写入 `stock_backend/.env`**（该文件被 `.gitignore` 忽略，不入库）；`.env.example` 仅留空占位 + 生成命令注释。
   - 需人工操作（**生产部署必须**）：生成并注入密钥 —— `python -c "import secrets; print(secrets.token_hex(32))"`，将输出写入生产环境变量 `MEMORY_ENCRYPTION_KEY`。
     ⚠️ **该密钥一旦用于加密便不可更换**：更换后既有记忆文件与 `memory_chunks.content` 密文将无法解密（存量数据不可读）。如需轮换，必须先解密全部存量再用新密钥重新加密。**请纳入密钥管理与备份范围**。
   - 附：测试侧已在 `tests/conftest.py` 用 `secrets.token_hex(32)` 注入一次性随机密钥，测试自包含、不依赖本机 `.env`。

21. **【泳道 C · G04/G21 遗留】后端容器镜像未安装 pgvector，api/worker/beat 容器启动即崩溃**
   - 现象：`docker logs stock-invest-dev-worker-1` 报 `ModuleNotFoundError: No module named 'pgvector'`，`worker` / `beat` 容器处于 `Restarting` 循环，`api` 亦受影响。宿主机 venv 已装 pgvector（G04 已加入 pyproject），**仅容器镜像未重建**。
   - 根因：G04 把 `pgvector` 加入 `pyproject.toml` / `requirements.lock` 后**未重建镜像**，容器内仍是旧依赖层。**与代码无关，宿主 venv 跑测试不受影响**（本泳道全部测试均在宿主 venv + 5433 容器库上执行并通过）。
   - 需人工操作：重建后端镜像后重启 —— `docker compose --env-file .env.docker -f deploy/docker-compose.dev.yml build api worker beat && docker compose --env-file .env.docker -f deploy/docker-compose.dev.yml up -d`。重建后容器内 `python -c "import pgvector"` 应无报错。
   - 附：本次会话期间 dev 全栈曾被停止（容器 `Exited (0)`），已由本泳道用上述 compose 命令恢复 db + redis。

22. **【泳道 G 复核发现 · 属泳道 F/G05】`test_backup.py` 恢复演练用例在活跃开发库上偶发失败（restored > source）**
   - 现象：`tests/test_backup.py::test_restore_into_temp_db_is_complete_and_cleans_up` 断言 `result["ok"] is True` 失败，报 `consistent: false`，且**漂移的表每次不同**——全库跑时是 `users`（source 13 / restored 15），单跑该模块时是 `symbols`（source 7258 / restored 7259）。
   - 根因：该用例校验口径为不变式 `restored <= source`（备份是 dump 那一刻的快照，源库是活的，写入只会让 source 变大）。**源库发生删除**时该不变式必然被打破：dump 之后若有人删行，source 会小于 restored。本仓库多泳道 agent 共用同一 dev 库（5433），其他泳道的测试清理（`_cleanup_users` / `_cleanup_symbol`）正好会删行。
   - **归因证据（已排除 G09 引入）**：① `pytest tests/test_backup.py -q` **单独跑整模块即复现**，此时 `tests/test_pagination.py` 根本未参与；② 单独跑该用例（`::test_restore_into_temp_db_is_complete_and_cleans_up`）连跑 3 次全绿，证明是环境竞态而非确定性缺陷；③ 泳道 G/G09 的改动全部落在列表**读**路径，不具备删行能力；④ 排除 `test_pagination.py` 跑全库（517 passed）与含它跑全库（528 passed）均通过，同一份代码两次结果不同。
   - 影响：仅测试稳定性，非功能回归（`verify_restore` 的其余四项不变式——归档可读、schema 表数一致、恢复库非空、无 pg_restore 错误——在失败样本中**全部为真**，备份链路本身健康）。生产每周演练若在业务低峰执行同样可能误报。
   - 建议（属该用例 owner 泳道 F）：把 `consistent` 的判定从「restored <= source」放宽为「restored 与 source 的差在容差内」或「dump 后源库无删除」（例如比对前先取源库行数快照、或对该用例使用独立库/停写窗口）。**泳道 G 未改动他人测试文件**，仅记录。
   - 需人工操作：无。

23. **【泳道 G · G09】列表端点分页契约变更 —— 前端已同步适配，但列表首屏上限 100 条待 G27 补齐**
   - 变更：`GET /conversations`、`/strategies`、`/agents`、`/backtest/tasks` 由**裸数组**改为分页信封 `{items,total,page,size,total_pages}`；`GET /conversations/{id}/messages` 由**全量数组**改为游标信封 `{items,has_more,next_cursor}`（默认最新 50 条）。
   - 影响：任何**外部/第三方**调用方（非本仓库前端）若按裸数组解析，需同步改造。仓库内前端已在同一步适配（`src/api/ai.ts` + `src/stores/ai.ts`），未破坏既有页面。
   - 待确认（G27 处理）：J 区会话列表、M 区策略/Agent 列表的首屏加载量由「全量」改为**一页 100 条**（后端单页上限）。当前无分页 UI，**拥有超过 100 条会话/策略的用户会看不到更早的记录**。G27 将引入 vue-virtual-scroller 虚拟滚动 + 按需续拉解决；若 G27 延后，需临时补「加载更多」入口。
   - 需人工操作：无。

22. **【全泳道 · 环境】git push 失败：SSH 公钥未被 GitHub 授权，本地已积压 6 个提交 —— 已解决（根因判断有误，见第 20 条）**
   - ⚠️ **本条的根因结论已被证伪，请以第 20 条为准**：该公钥**已登记在 GitHub 账号上且工作正常**，真正的失败原因是**私钥带口令**，而非交互式调用（无 TTY / `BatchMode=yes`）拿不到口令提示，ssh 便统一报 `Permission denied (publickey)`。**该报错同时表示"key 未授权"和"key 有口令但无法输入口令"，不能据此断定公钥未登记。**
   - **解决**：`eval "$(ssh-agent -s)" && ssh-add ~/.ssh/id_ed25519`（输入口令）后 `ssh -T git@github.com` 返回 `Hi 112-njx!`，`git push origin main` 恢复正常。已积压的 6 个提交（含泳道 C 的 G21/G31、G15/G34、G14，泳道 F 的 G05，泳道 D 的 G09）**均已推送，main 与远端同步**。
   - 保留原记录（供回溯，勿据此行动）：现象 `git@ssh.github.com: Permission denied (publickey)`；私钥文件存在（指纹 `SHA256:31twrZ6KzaM3nN7TJxg8y4HurmAhZbjqrbN4r0HuWEk`）；远端 `git@github.com:112-njx/stock-invest-system.git`；`~/.ssh/config` 把 github.com 指向 `ssh.github.com:443`。
   - 需人工操作：**无（已解决）**。可选免口令方案与安全提醒见第 20 条。

24. **【泳道 G · G27】新增前端依赖 vue-virtual-scroller，部署前需重新 npm install**
   - 现状：`stock_frontend/package.json` 新增 `vue-virtual-scroller@^3.0.5`（peer `vue ^3.3.0`，与本项目 Vue 3.5 兼容），`package-lock.json` 已同步；`src/main.ts` 引入其 CSS。
   - 需人工操作：**已存在的开发/部署环境需重新 `npm install`（或 `npm ci`）**，否则前端构建会因找不到模块失败。Docker 前端镜像若使用 `npm ci`，重建镜像即可自动带上。
   - 附：新增 `npm run verify:pagination` 验证脚本（esbuild + jsdom，25 项断言），与既有 `verify:xss` 并列，建议纳入 CI。

25. **【泳道 G · G27】Agent 运行记录弹窗由「上一页/下一页」分页器改为连续滚动（UX 变更，需确认）**
   - 现状：`AgentRunsDialog.vue`（M 区「运行记录」）原为每页 20 条的上一页/下一页分页器；G27 按要求改为 RecycleScroller 虚拟滚动 + 滚动到末尾自动续拉，**分页器已移除**，顶部保留「已加载 X / 共 Y 条」提示以免用户失去位置感。
   - 影响：交互方式变化（不能再按页跳转，只能连续滚动）。数据契约未变（仍走 `GET /agent/runs` 的 page/size）。
   - 需人工确认：是否接受该 UX 变更；若希望保留分页器，需回退为「分页器 + 虚拟滚动」并存（虚拟滚动收益在每页 20 条时很小，属冗余）。
   - 附：**虚拟滚动的 DOM 布局行为未做自动化验证** —— jsdom 不做布局计算（`clientHeight` 恒为 0），RecycleScroller 在无布局环境下无法真实渲染。已验证部分：typecheck / eslint / vite build 全绿 + `verify:pagination` 25 项断言覆盖游标累积·去重·终止条件·切换会话丢弃·埋点阈值。**待人工浏览器确认**：① J 区会话/策略列表滚动流畅、行不错位（`.j-item` 固定 34px 与 `ITEM_SIZE` 必须一致）；② Agent 运行记录滚动到底部自动续拉；③ 对话区滚动到顶部加载更早消息且视野不被顶走。

26. **【泳道 G · G35】登录页三张卡片图为未压缩大图，首屏额外约 5.2MB（需人工优化）**
   - 现状：按规格书 §7 把 `docs/Agent_v0.3/page1~3.png` 复制到 `src/assets/login/`，三图原始分辨率 2304×1594 / 2274×1364 / 2233×1575，合计 **5.2MB**，`vite build` 原样产出（dist 5.9MB），登录页首屏需下载全部三图。
   - 影响：弱网/移动端登录页加载慢。功能无影响（验收项全部满足）。
   - 需人工操作：用图片工具压到 ~200KB/张（如 `sharp`/`pngquant`/TinyPNG，宽度降到 ~1200px 即可，左侧卡片实际显示宽度不超过 600px）。本机无 PIL/sharp，未擅自压缩以免影响画质。**换图只需替换 `src/assets/login/` 下同名文件**，不必改代码。

27. **【泳道 G · G35】登录页卡片内容自定义入口 + QQ 邮箱登录未接入 OAuth**
   - 卡片自定义：改 `src/assets/login/page1~3.png` 或改 `src/config/loginCards.ts` 即可换图/换文案，**无需改组件**；`mode: 'data'` 为预留动态化模式（已实现三类卡片的结构化渲染骨架，字段见规格书 §2.2），未来接真实接口时切换 mode 即可。
   - QQ 邮箱登录：按规格书 §3.2「V0.3 阶段先弹提示『QQ 邮箱登录接入中』，不跳转；视觉先就位」实现，**无 OAuth 后端**。需人工确认：后续是否要接入真实 QQ 邮箱授权登录。
   - page1 图内英文（Chance Index / See Details）按用户确认**保留原样**，未中文化，属预期行为。

28. **【泳道 G · G35】方案 B 行为变更汇总 + 待人工浏览器确认清单**
   - **行为变更（需知晓）**：① 未登录可直接浏览行情页与 AI 页，不再强制跳登录页；② `/` 现在是行情首页，`/market` 变为重定向；③ 顶部导航栏新增头像区（未登录=「登录」入口，已登录=头像+下拉菜单），与 G16 铃铛并存，**I 区用户 Cell 保留不变**；④ 法律页 / 找回密码页 / 登录页**不显示顶部导航栏与公告条**（沿用 G03 现状，仅把语义从 `meta.public` 换成 `meta.bare`）；⑤ 未登录时 I 区隐藏账号安全、数据与隐私、AI 模型设置、危险操作四个区块（接口需鉴权）。
   - **关键坑（后续改动务必遵守）**：未登录状态下**任何鉴权请求都不能发出** —— `src/api/http.ts` 的 401 拦截器在 refresh 失败时会 `clearAuth()` 并跳登录页，会把免登录访客直接弹走。G35 已为 `/watchlist`、支撑压力位、通知未读数、API Key 状态、会话/策略/Agent 列表全部加了未登录短路；**新增鉴权调用时请同样先判 `user.token`**。
   - **待人工浏览器确认**（jsdom 不做布局计算，自动化脚本无法覆盖）：① `/` `/login` `/ai` `/terms` `/privacy` `/disclaimer` 六个路由打开正常、未登录**不白屏**；② 登录弹窗 Tab 切换、登录成功后弹窗关闭且当前页用户态刷新（头像变昵称、关注列表出现、AI 页列表加载）、**不跳转**；③ 头像下拉四项（个人设置/我的数据跳首页对应区块、通知中心打开铃铛面板、退出登录）可用；④ 登录页左右 56/44 分栏、三卡片 3D 倾斜（移入跟随、移出 0.4s 回正）、窄屏 <1024px 堆叠滚动；⑤ page3 底部「年化收益率」完整可见未被裁切。
   - 需人工操作：无（以上均为验收确认项）。

23. **【泳道 F · G08 发现】容器内整个应用无法导入（Python 3.12 急切注解）—— 已修复（跨泳道，泳道 C 的 G14 引入）**
   - 现象：Linux 容器内跑 pytest / 启动服务，`app/worker/tasks/ai_tasks.py` → `app.agent.memory` → `app.services.llm` 导入链在 `app/services/llm/llm_service.py:171` 报 `NameError: name 'LLMService' is not defined`，**api / worker / beat 三个容器全部起不来**。
   - 根因：`LLMService.with_api_key()` 的返回注解写成 `-> LLMService`（引用类自身），类体内注解在 **Python 3.12 是急切求值**，此刻 `LLMService` 尚未绑定到模块命名空间。本地 Python 3.14 走 PEP 649 惰性注解故不报错 —— 与 `deploy_fixed.md` 问题二（`chromadb.PersistentClient | None`）**完全同类**的"本地 3.14 / 容器 3.12"版本差异坑，**只在容器暴露**。
   - 影响范围：泳道 C 的 G14（提交 b624279）起，容器镜像导入即崩；本地开发不可见，属高危（部署后才炸）。
   - **已修复**（泳道 F 在 G08 期间发现并修）：`llm_service.py` 顶部加 `from __future__ import annotations`（与 `store.py` 同处置）。验证：容器内 `import app.main` 成功、celery 注册 15 个任务。
   - 需人工操作：无。**经验（全泳道）**：凡「类体内自引用注解」或「`X | None` 且 X 为函数」的写法，本地 3.14 不报错但容器 3.12 必炸 —— 新增此类注解一律加 `from __future__ import annotations`。建议 G36 收尾时全仓扫一遍类内自引用注解。
   - 附：同类问题已出现两次（`store.py` 的 chromadb、本次 llm_service），根因都是"本地解释器版本高于容器"，属结构性问题而非偶发。

24. **【泳道 F · G25】策略校验器要求 `initialize`，而回测引擎不要求 —— 口径不一致（待确认，当前保持现状）**
   - 现状：`strategy_validator._check_interface` 把「缺少 initialize 函数」判为**校验不通过**；但引擎侧 `app/backtest/sandbox.py::compile_strategy` 明确把 `initialize` 当作**可选**（`init = glb.get("initialize"); if callable(init): ...`，只强制 `on_bar`）。
   - 影响：G25 把三级校验**强制**在提交回测前执行后，理论上会拒掉「没有 initialize 但引擎完全能跑」的策略。对**手工编写**的策略尤其可能（AI 生成路径的提示词要求写 initialize，不受影响）。
   - **实测评估（2026-09-18）**：本机库中 5 条策略跑三级校验，仅 1 条不通过且原因是**代码为空**（本就跑不了），**0 条因缺 initialize 被拒** → 回归风险是理论上的，暂无实际影响。
   - 当前决策：**保持校验器现状**（不改其它泳道的契约），仅记录。校验失败信息会明确写出「缺少 initialize 函数」，用户可自行补上。
   - 需人工确认（二选一）：
     ① 保持现状（推荐，零风险且实测无影响）；
     ② 若希望两边口径一致，把校验器的 initialize 检查改为可选（仅保留 `on_bar` 强制）—— 属 `strategy_validator` owner 的改动，一行删改 + 更新 `tests/test_strategy_validator.py` 对应用例。

25. **【泳道 F · G08】Windows 本地开发：CPU 无硬上限（内存已由跨平台看门狗覆盖）**
   - 现状：策略子进程的 CPU 上限靠 POSIX 的 `RLIMIT_CPU`（内核级）实现，**Windows 没有 `resource` 模块**，本地开发机上 CPU 上限**不生效**；内存上限已由跨平台 RSS 看门狗补齐（见第 20~22 条之外的 fixed.md 2026-09-18 条），但 CPU 仍只有**墙钟兜底**（`BACKTEST_TIME_BUDGET + GRACE` = 默认 45s）。
   - 影响面：**仅本地开发机**，且危害有限 —— CPU 失控只占单核、且被墙钟硬封顶 45s（对比内存失控曾达 ~600MB/s 无上限，故内存优先补齐）。生产容器（Linux）`RLIMIT_CPU` 正常生效。
   - 残余风险：**dev/prod 行为仍有一处分叉** —— 一个 CPU 耗时超过 45s 的策略在本地表现为"墙钟超时"，在生产会先撞 `RLIMIT_CPU`；两者的失败语义一致（都判失败、都不可重试），仅错误原因文案不同，故影响很小。
   - 需人工操作：无。若确需在 Windows 也精确限制 CPU，可选方案是 Windows Job Object（需 `pywin32` 或一段 ctypes），评估后认为**收益不抵成本**（仅开发机、且已有墙钟兜底），未实施。

26. **【泳道 F · G11】Redis Sentinel 自动故障转移「未经验证」—— 上线前必须按真实拓扑实测**
   - 现状：应用侧 Sentinel 支持已实现并验证（主节点发现 + 经其读写，真实容器端到端通过），但「一主两从**自动故障转移**」在本地最小化拓扑下**未能跑通**：1 sentinel + 1 master + 2 replica，down-after-milliseconds 设为 3000，kill 掉主节点后 Sentinel **未把主标记为 s_down**（sentinel master 查询的 flags 仍为 master），35s 内未发生提升，客户端连接旧主超时。
   - 已排除：Sentinel 能看到 2 个 replica（num-slaves=2）、resolve-hostnames 已开启、replica 侧 master_link_status 正确转为 down。
   - 根因：**未定位**（本轮未继续深挖，超出合理成本，且见下方判断）。
   - 判断依据：单 Sentinel 本身是**单点**，其切换行为不代表生产拓扑（quorum/多数派语义不同）—— 在本机强行调通并宣称"故障转移可用"反而会给出**错误信心**，故未这么做。
   - 需人工操作（上线前必做，清单见 docs/ops/read_write_splitting.md 第 2.3 节）：
     ① 按手册搭 **≥3 个 Sentinel** 的真实拓扑；
     ② kill 主节点后，sentinel get-master-addr-by-name 应返回新节点，应用**不重启**直接读写应成功；
     ③ 把切换耗时与结论回填手册。
   - 关联：**PG 读写分离已验证通过**（未配从库即降级为单实例），可独立上线；本项仅影响 Redis 高可用的故障转移能力，不影响主从切换以外的功能。
