该文档中你将记录对整个系统修复的bug，
我在指出bug后,你的格式按照：
时间：
修复bug内容（描述）：
需要我手动配置（如果有的话）：
的格式对该文档进行编写，要求编码内容简练而说明主要内容，
一次编写的编码内容描述在200字以内
另外不准更改或删除我对问题的描述。
在文件最后方写出工作完成后需要人配置的地方或日志文件说明，要求遵循简洁的原则，一条一句话总结即可并且每一条都必须是需要开发者手动配置或观看系统运行的。

## 问题一：docker容器部署报错
（1）在开发阶段，我们不使用D:\stock-invest-system\deploy\docker-compose.yml进行在容器中的上线,如果问题较多,多次更改前端后端文件会导致大量容器文件残留,
所以在运维文件夹下重新编写一个在开发阶段使用的docker-copmpose文件,在文件前写好一键清理容器中残留垃圾的脚本,确保每一次开发启动后容器中没有残留文件.
（2）我刚刚使用过D:\stock-invest-system\deploy\docker-compose.yml文件核心报错：
#16 [worker builder 4/4] RUN pip install --prefix=/install -r requirements.lock
#16 21.00 ERROR: Exception:
#16 21.00 ReadTimeoutError: HTTPSConnectionPool(host='files.pythonhosted.org', port=443): Read timed out.
#16 ERROR: process "/bin/sh -c pip install --prefix=/install -r requirements.lock" did not complete successfully: exit code: 2
在开发阶段使用的docker文件和该docker启动文件中都修复该问题，

时间：2026-08-11
修复bug内容（描述）：Dockerfile 依赖安装改用国内 PyPI 镜像（默认清华 TUNA）并加长超时/重试，修复 pip 连国外源 ReadTimeout；新增开发阶段编排 deploy/docker-compose.dev.yml（后端 bind mount + uvicorn --reload、前端 nginx 托管宿主 dist）+ cleanup_dev.sh / start_dev.sh 一键清理容器残留。生产/开发 compose 共用 Dockerfile，均修复。
需要我手动配置（如果有的话）：1) 根目录 .env.docker 配置 JWT_SECRET_KEY 与 DEEPSEEK_API_KEY；2) 如需换 PyPI 源，构建传 --build-arg PIP_INDEX_URL=<镜像>；3) 开发栈端口冲突可在 .env.docker 设 DEV_API_PORT / DEV_NGINX_PORT。

---

## 工作完成后需手动配置 / 日志文件说明
- 手动配置：.env.docker 需配置 JWT_SECRET_KEY（生产改强随机值）与 DEEPSEEK_API_KEY（容器内用 AI 才需要）。
- 手动配置：开发栈端口默认 API 8000 / 前端 8081，冲突时在 .env.docker 设 DEV_API_PORT / DEV_NGINX_PORT。

## 问题二：Docker 开发栈 worker / beat 容器启动即崩溃、反复重启

现象：docker compose up 后 api、frontend 正常，但 worker、beat 在 Docker Desktop 里转圈、时开时关（崩溃重启循环）。

问题出现原因（本地 Python 3.14 与容器 Python 3.12 的版本差异，共两处）：
1. worker：app/agent/memory/store.py 中 `chromadb.PersistentClient | None`，而 chromadb 1.5.x 的 PersistentClient 顶层导出是工厂函数（function）并非类；本地 Python 3.14 默认 PEP649 惰性注解不报错，容器 Python 3.12 急切求值 `function | None` 抛 TypeError，worker 导入即崩。
2. beat：Python 3.13+ 的 dbm 默认改用 SQLite 后端，本地 3.14 跑 beat 生成 SQLite 格式的 celerybeat-schedule（带 -shm/-wal）；容器 3.12 的 dbm 无 SQLite 后端，经 bind mount 读到该文件报 `db type could not be determined`。

时间：2026-09-03
修复bug内容（描述）：1) store.py 顶部加 from __future__ import annotations 使注解惰性求值，兼容 Python 3.10-3.14，worker 正常注册 ai/backtest/sync 队列；2) docker-compose.dev.yml 的 beat 命令加 --schedule=/tmp/celerybeat-schedule，把调度状态文件隔离到容器内非挂载目录，并删除宿主 stock_backend 下残留的 celerybeat-schedule/-shm/-wal，beat 不再报 dbm 损坏。
需要我手动配置（如果有的话）：无；若此前在本地直接跑过 celery beat，手动删除 stock_backend 目录下的 celerybeat-schedule* 残留文件即可。

---

## 工作完成后需手动配置 / 日志文件说明（问题二补充）
- 观看运行：`docker compose -f deploy/docker-compose.dev.yml ps` 确认 worker、beat 为 Up 且 RestartCount=0；`docker compose -f deploy/docker-compose.dev.yml logs -f worker beat` 应无 TypeError / dbm 报错，worker 打印 ai、backtest、sync 三个队列即正常。

---

## 问题三：Docker 全新空库行情数据拉取长时间未完成

现象：docker compose up 后打开前端，行情同步长时间停在"拉取中"，页面无数据可展示。

问题出现原因（按日志逐条分析，区分系统性 bug 与外部/环境因素）：

系统性 bug（代码/编排层，可修复）：
1. 多源 Provider 与 akshare 接口不匹配：eastmoney `stock_board_industry_hist_min_em()` 传了当前 akshare 不支持的 `start_date` 参数（参数漂移）；sina `stock_zh_index_daily` 返回缺 `date` 列、ths `stock_board_industry_index_ths` 返回缺板块名列（KeyError）——与"akshare 返回英文列名、代码硬编码中文列名"同源，硬编码与数据源返回格式脱耦，导致东财→新浪→同花顺三级降级链全部打穿。
2. 启动编排缺陷：api/worker/beat 三容器 entrypoint 各自执行 `alembic upgrade head` 并发建表撞 `pg_type_typname_nsp_index` 唯一约束；presync 在 worker/api 重复触发 fixed indices/catalog（生成两个 task_id）。

外部/环境因素（非代码 bug）：
3. 东财限流/反爬：`Connection aborted / RemoteDisconnected`，容器出口 IP 更易触发风控，每个接口重试 3 次（2s+4s+8s）后 give up。
4. 全新空库无兜底：db 全新初始化仅种 49 个 symbol 元数据，无 K 线/快照/账号，数据源失败即空白。

时间：2026-09-04
修复bug内容（描述）——种子数据引导方案（已确认可行，待落地）：
在容器首次启动时预置必要数据，页面打开即有内容，不依赖实时拉取。start-dev.bat 在 up -d 且 db ready 后检测空库：① 优先从本地原生库 pg_dump（--data-only）导入容器库（账号/K线/快照/重点关注，需两端 alembic 版本一致）；② 或执行轻量种子 SQL（默认账号+49 指数+常用标的最近 K 线/快照），幂等用 ON CONFLICT DO NOTHING + 卷内 .seeded 标记避免重复导入。同时修复 akshare 参数/列名适配与迁移单点化，增量拉取方可恢复。
需要我手动配置（如果有的话）：1) 选"从本地库引导"时，本机 Postgres（5432/stock_invest）需运行且 schema 与容器库 alembic 版本一致；2) 首次引导耗时取决于数据量，期间勿重复启动；3) 东财限流需降低同步并发/频次或依赖多源降级。

---

## 工作完成后需手动配置 / 日志文件说明（问题三补充）
- 观看运行：`docker compose -f deploy/docker-compose.dev.yml logs -f worker` 持续出现 `[provider:eastmoney] ... give up` 说明数据源仍不可用，需等待或调整同步策略。
- 手动配置：若选择"从本地库引导"，先确保本机 Postgres（5432/stock_invest）运行且数据完整。

---

## 问题三修复落地报告（2026-09-04，两个系统性 bug + 种子引导均已落地并实测）

时间：2026-09-04
修复bug内容（描述）：
1) 系统性 bug①多源适配：eastmoney 行业分钟接口 stock_board_industry_hist_min_em 仅收 (symbol,period)，按 asset_type 移除误传的 start_date/end_date（取近期全量后按时间窗过滤）；sina 日K日期列改用 _pick_col 兼容 date/日期、缺列优雅返回空，不再 KeyError 打穿；ths 日K调用前用 _industry_score 把种子行业名归一化到同花顺内置板块（半导体设备→半导体），无匹配返回空，规避 akshare 内部 code_map KeyError。
2) 系统性 bug②迁移单点化：compose 抽 x-backend-env 公共锚点，仅 api 置 RUN_MIGRATIONS=1 执行 alembic+seed+presync；新增 scripts/wait_for_migrations.py，worker/beat entrypoint 轮询等待 alembic_version=head 再启动，消除并发建表撞 pg_type 唯一约束与 presync 重复触发。
3) 种子引导：新增 deploy/seed_from_local.py，由 start-dev.bat [4/4] 自动执行——宿主 psycopg2 读本机 PG18、经 docker exec psql 写容器 PG16（绕开 pg_dump 18→16 版本差）；自动等迁移、空库才导（幂等）、导入前停 worker/beat 防并发写、导完 setval 对齐全部自增序列到 max(id) 再恢复。实测导入 362 张表（users=13/symbols=52/快照44/K线齐全），root 登录与行情页打开即有数据，6 容器 RestartCount=0。
需要我手动配置（如果有的话）：
1) 种子引导依赖本机原生 PostgreSQL（127.0.0.1:5432/stock_invest，postgres/123456）运行、且两端 alembic 版本一致（当前均 0008）；本机库未运行时脚本自动跳过、不阻断启动（全新机器无本地库则无种子，需另备轻量种子 SQL）。
2) 需以本机库覆盖容器库时手动执行：stock_backend\.venv\Scripts\python.exe deploy\seed_from_local.py --force。
3) 东财 RemoteDisconnected 属外部限流/反爬，非改代码可根治，仍靠多源降级与降频缓解。

---

## 工作完成后需手动配置 / 日志文件说明（问题三落地补充）
- 观看运行：双击 start-dev.bat 看到 [4/4] Seed initial data，出现“共引导 N 张表”或“种子数据已存在，跳过”即正常。
- 观看运行：docker compose -f deploy/docker-compose.dev.yml logs worker beat 应先打印 migrations ready (current=0008, head=0008) 再启动 celery，且无 pg_type 冲突、无 duplicate key。
- 手动配置：种子源库账号/密码/端口写在 deploy/seed_from_local.py 顶部 LOCAL_DSN，本机库信息变更时同步修改。

---

## 问题四：start-dev.bat 启动后同步阻塞（前端死等 + presync 全量重拉 + 数据源全挂卡 running）

现象：行情同步中页面一直骨架屏死等不展示数据；已有 K 线数据的库每次重启仍对全部固定指数全量重拉、启动慢；数据源全挂时 fixed_indices 一直 running 不置 failed，前端无从降级。

问题出现原因：
1. 前端 MarketView.vue checkSyncStatus 把 running 当硬阻塞，无超时兜底，同步失败/极慢即死等。
2. 后端 run_fixed_indices_sync 对所有 49 个固定指数全周期全量重拉（start=now-730天），与"谁过期"脱耦。
3. run_fixed_indices_sync 无 except 收尾：fetch_kline raise_on_giveup=True 抛 ProviderError 后 sync_status 永久停留 running。

时间：2026-09-04
修复bug内容（描述）：
1) 前端 MarketView.vue：checkSyncStatus 加 SYNC_TIMEOUT_MS=30000 常量，running 持续超阈值即降级 loadFixedIndices+ensureDefaultSymbol+start() 展示库中已有快照，同步完成后自动刷新（syncDegraded 标记保证 done 分支仍刷新）；阈值集中定义便于调整。
2) 后端 sync_service.run_fixed_indices_sync(skip_existing=True)：已有日K（latest_ts 非空）标的跳过全量重拉并标记已同步，仅无数据标的全量拉；过期数据由每日 16:30 增量任务 run_kline_incremental 兜底。/fetch-all 运维接口传 skip_existing=False 保持全量刷新。
3) 后端失败收尾：except 中置 sync_status=failed 并 re-raise（失败原因由 Celery 任务层写 task_logs）；全部被拉取标的 0 写入（数据源通但返回空）也收尾 failed 而非假 done，前端据此降级展示已有数据。
需要我手动配置（如果有的话）：无。

---

## 工作完成后需手动配置 / 日志文件说明（问题四补充）
- 观看运行：前端打开即展示已有数据，顶部同步进度条超过 30s 不再阻塞页面（降级后完成自动刷新）。
- 观看运行：`docker compose -f deploy/docker-compose.dev.yml logs -f worker` 出现 fixed indices presync done 即正常；若打印 give up 则 sync_status=failed、前端降级展示旧数据。
- 手动配置：本机跑后端测试时需先启动本地 Redis（127.0.0.1:6379），否则 test_realtime_poll_writes_snapshot_and_redis_cache 环境性失败。

---

## 问题五：nginx 启动竞态（frontend 先于 api 就绪 502）+ 东财容器出口 IP 持续风控

现象：docker compose up 后打开前端，启动初期大量接口 502 Connection refused；worker 日志东财全接口 RemoteDisconnected 持续 give up，多源降级链新浪/同花顺亦部分打穿。

问题出现原因：
1. frontend（nginx）与 api 容器无 healthcheck / depends_on 编排，frontend 先起、api 未就绪时 nginx 反代全部 502（日志 09:07:39-55 连续 connect() failed，users/me、watchlist、sync-status、symbols 全失败），浏览器重试期首屏白屏。
2. 东财接口（index_zh_a_hist_min_em / index_zh_a_hist / stock_board_industry_name_em / stock_board_industry_hist_min_em）容器出口 IP 被风控，重试 3 次（2s+4s+8s）后 give up，属外部限流/反爬，非改代码可根治。

时间：2026-09-04
修复bug内容（描述）：（待定）① compose 为 frontend 配 depends_on: api（condition: service_healthy）+ api 健康检查，或 nginx proxy_next_upstream 对上游 502 重试；② 东财风控靠多源降级+降频缓解，暂无法根治。
需要我手动配置（如果有的话）：无。

---

## 工作完成后需手动配置 / 日志文件说明（问题五补充）
- 观看运行：启动后 api 容器日志出现 uvicorn running 后再打开前端，即可避免启动期 502 刷屏。
- 观看运行：docker compose logs worker 持续打印 [provider:eastmoney] ... give up 说明东财仍被风控，等待冷却或依赖多源降级。
