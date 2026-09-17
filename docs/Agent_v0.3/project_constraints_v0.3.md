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

18. **【泳道 F · G05】发现现存 bug：行情新鲜度指标一直采集失败（留待 G24 修复）**
   - 现象：`/metrics` 抓取时日志报 `market freshness collect failed: can't subtract offset-naive and offset-aware datetimes`，`market_data_freshness_seconds` 指标**从未真正上报**，`MarketDataStale` 告警规则因此永不触发（监控盲区）。
   - 根因：`app/core/metrics_ext.py::_refresh_market_freshness` 用 `datetime.now(UTC) - row`，而 `snapshot_realtime.updated_at` 是 naive（`timestamp without time zone`），aware 减 naive 抛 TypeError。属 P1-3（G24 时区统一）的典型症状，非 G05 引入。
   - 需人工操作：无。已记录，G24 完成 timestamptz 迁移后该指标自动恢复（迁移后 ORM 返回 aware datetime）；G24 需补回归断言。
