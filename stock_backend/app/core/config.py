"""应用配置：pydantic-settings 从环境变量 / .env 读取，禁止硬编码。

生产修改方式：复制 .env.example 为 .env 后按需调整。
"""

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

_BASE_DIR = Path(__file__).resolve().parents[2]  # stock_backend/（相对路径基于工程根）


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---- 基础 ----
    APP_NAME: str = "stock-backend"
    APP_ENV: str = "dev"  # dev / test / prod
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # ---- 数据库（PostgreSQL）----
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/stock_invest"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600  # 秒

    # ---- Redis（缓存 + Celery 队列）----
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    SNAPSHOT_CACHE_TTL: int = 300  # 实时快照缓存秒数（V0.2 从 5s 延长至 300s，交易时段由 realtime_poll 覆盖刷新）
    KLINE_CACHE_TTL: int = 300  # K线缓存秒数
    SEARCH_CACHE_TTL: int = 3600  # 搜索联想缓存秒数（catalog_sync 完成后批量删除）
    WATCHLIST_CACHE_TTL: int = 300  # 关注列表缓存秒数

    CELERY_BROKER_URL: str = "redis://127.0.0.1:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://127.0.0.1:6379/2"

    # ---- 行情同步 ----
    DATA_PROVIDER_PRIORITY: str = "eastmoney,sina,ths"  # Provider 优先级链（逗号分隔，可调整顺序/禁用）
    PROVIDER_CIRCUIT_FAILURE_THRESHOLD: int = 3  # Provider 连续失败 N 次熔断
    PROVIDER_CIRCUIT_COOLDOWN: int = 60  # Provider 熔断冷却（秒），冷却后半开探测
    PROVIDER_PROBE_INTERVAL: int = 60  # 熔断中 Provider 后台探测间隔（秒）
    KLINE_INIT_DAYS: int = 730  # 首次全量拉取天数（约2年）
    REALTIME_POLL_INTERVAL: int = 15  # 实时轮询间隔（秒），降频规避东财风控（原 5s 触发限流）
    SYNC_INCREMENTAL_HOUR: int = 16  # 每日增量同步时刻（本地时区小时）
    SYNC_INCREMENTAL_MINUTE: int = 30
    SYNC_TIMEOUT: int = 30  # 数据源请求超时（秒）
    SYNC_RETRY_TIMES: int = 3  # 外部源重试次数
    SYNC_RETRY_BACKOFF: float = 2.0  # 退避基数（秒）
    SYNC_DAILY_LIST_TIMES: str = "16,17"  # 增量同步 beat cron 小时，逗号分隔

    # ---- JWT 鉴权 ----
    JWT_SECRET_KEY: str = "dev-secret-change-in-production-0123456789abcdef"  # ≥32字节，生产必须覆盖为强随机值
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 旧 token 有效期 7 天（向后兼容，G19 后由 ACCESS_TOKEN_EXPIRE_MINUTES 接管）
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # G19: access token 有效期 15 分钟
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # G19: refresh token 有效期 7 天
    REFRESH_TOKEN_COOKIE_NAME: str = "refresh_token"  # G19: refresh token Cookie 名称
    ADMIN_USERNAMES: str = "root"  # 管理员用户名（逗号分隔），启动时自动置 is_admin=true

    # ---- SMTP 邮件服务（G02：邮箱验证/密码重置/异常登录/系统通知）----
    SMTP_HOST: str = ""  # SMTP 服务器地址（为空时启用模拟模式）
    SMTP_PORT: int = 587  # SMTP 端口（587=STARTTLS, 465=SSL）
    SMTP_USER: str = ""  # SMTP 用户名
    SMTP_PASS: str = ""  # SMTP 密码
    SMTP_FROM_NAME: str = "量化回测助手"  # 发件人显示名称
    SMTP_FROM_EMAIL: str = ""  # 发件人邮箱（为空时用 SMTP_USER）
    SMTP_USE_TLS: bool = True  # True=STARTTLS(587), False=SSL(465)
    SMTP_TIMEOUT: int = 30  # SMTP 连接/发送超时（秒）

    # ---- CORS / Cookie 安全（G01：白名单 + Secure 属性）----
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:8081,http://127.0.0.1:5173,http://127.0.0.1:8081"  # 逗号分隔可信来源；生产覆盖为实际域名
    COOKIE_SECURE: bool = False  # Cookie Secure 属性；生产 HTTPS 环境设 True
    COOKIE_SAMESITE: str = "lax"  # Cookie SameSite（lax / strict / none）
    ACCESS_TOKEN_COOKIE_NAME: str = "access_token"  # access token Cookie 名称（G19 启用 Cookie 鉴权后使用）

    # ---- 技术指标 ----
    INDICATOR_CACHE_TTL: int = 300  # 指标缓存秒数（key 含 K 线最新 ts，新数据到达自动失效）

    # ---- DeepSeek（阶段三 LangChain 启用）----
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # ---- LLM 调用防护（超时/重试/熔断/限流，借鉴 TradingAgents-CN llm_adapters）----
    LLM_TIMEOUT: float = 60.0  # 单次 LLM 调用超时（秒）
    LLM_MAX_RETRIES: int = 2  # 失败指数退避重试次数
    LLM_RETRY_BACKOFF: float = 1.5  # 退避基数（秒，2^attempt 递增）
    LLM_CIRCUIT_FAILURE_THRESHOLD: int = 5  # 连续失败 N 次熔断
    LLM_CIRCUIT_COOLDOWN: int = 60  # 熔断冷却（秒），冷却后半开探测
    LLM_RATE_LIMIT_RPM: int = 30  # 每分钟限流请求数
    LLM_TEMPERATURE: float = 0.7  # 默认采样温度

    # ---- Token 预算控制（阶段八 8.2：发送前估算 token，超预算自动减轮）----
    LLM_MAX_TOKENS: int = 65536  # 模型上下文上限（DeepSeek-chat 64K）
    TOKEN_BUDGET_RATIO: float = 0.8  # 发送前 token 预算占比上限（80%）

    # ---- 策略生成（阶段八 8.4：校验失败自动重试）----
    STRATEGY_GEN_MAX_RETRIES: int = 2  # 策略校验失败最多重试次数

    # ---- 会话标题自动生成（阶段八 8.7）----
    TITLE_WAIT_TIMEOUT: float = 3.0  # done 后等待标题生成的最长时间（秒，best-effort）

    # ---- SSE 流式稳定性（阶段五：心跳/三级超时/delta 断点续传缓存）----
    SSE_KEEPALIVE_INTERVAL: int = 15  # SSE 空闲时每 N 秒发注释行 :keepalive，防 Nginx proxy_read_timeout
    SSE_FIRST_TOKEN_TIMEOUT: float = 30.0  # 首字超时（LLM 未返回首个输出即超时，秒）
    SSE_INTER_DELTA_TIMEOUT: float = 15.0  # 单 delta 间隔超时（相邻输出间隔，秒）
    SSE_TOTAL_TIMEOUT: float = 120.0  # 总流式超时（秒），超时返回已生成内容
    SSE_DELTA_CACHE_TTL: int = 600  # delta 断点续传缓存 TTL（秒）
    SSE_DELTA_CACHE_MAX: int = 100  # 每会话缓存最近 delta 条数上限

    # ---- 用户数据导出（G17：P1-5a 数据复制权）----
    EXPORT_DIR: str = str(_BASE_DIR / "data" / "exports")  # 导出 ZIP 临时目录
    EXPORT_TTL_HOURS: int = 24  # 导出文件保留时长（超过后由 beat 清理任务删除）
    EXPORT_DOWNLOAD_TOKEN_MINUTES: int = 30  # 下载链接签名 token 有效期（分钟）

    # ---- 本地记忆（memory_chunks + pgvector 持久化 + 人类可读记忆文件）----
    # G31 起 PG 为向量存储唯一真源；Chroma 依赖 / data/chroma/ / CHROMA_DIR / 双写开关均已下线。
    MEMORY_DIR: str = str(_BASE_DIR / "data" / "memory")  # 记忆文件根目录（M 区可打开）
    MEMORY_TOP_K: int = 5  # 记忆检索注入条数
    MEMORY_IMPORTANCE_MIN: int = 5  # 抽取时重要性低于该值不入库（噪音过滤）

    # ---- 记忆加密（G15 P0-3a / G34 P0-3b）----
    # 32 字节随机密钥（64 位 hex），AES-256-GCM。**禁止硬编码**，未配置时加密写入会明确报错。
    # 生成：python -c "import secrets; print(secrets.token_hex(32))"
    MEMORY_ENCRYPTION_KEY: str = ""  # 空 = 未配置（需人工配置，见 project_constraints_v0.3.md）

    # ---- Embedding（阶段六：ONNX MiniLM 语义向量，int8 量化，本地 CPU 推理）----
    EMBEDDING_MODEL: str = "minilm"  # minilm | hash（hash 为回退选项）
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # HF 模型仓库
    EMBEDDING_MODEL_PATH: str = str(_BASE_DIR / "data" / "models")  # 模型文件本地目录（首次启动自动下载）
    EMBEDDING_QUANTIZATION: str = "int8"  # int8 | fp32（机器性能够时可切 fp32 完整版）
    EMBEDDING_DIM: int = 384  # 向量维度
    EMBEDDING_MAX_LENGTH: int = 128  # 输入截断长度（token）

    # ---- 回测引擎（阶段四：异步 Celery，不阻塞主线程）----
    BACKTEST_INITIAL_CASH: float = 1_000_000  # 初始资金（元）
    BACKTEST_COMMISSION_RATE: float = 0.0003  # 佣金（双边，万分之三）
    BACKTEST_STAMP_DUTY_RATE: float = 0.0005  # 印花税（卖出单边，万分之五）
    BACKTEST_FILL_ON: str = "close"  # 撮合价：close（收盘价）/ open（开盘价）
    BACKTEST_TIME_BUDGET: float = 30.0  # 单次回测执行时间预算（秒，超预算中止）
    BACKTEST_DEFAULT_DAYS: int = 730  # 默认回测区间天数（约2年）
    BACKTEST_MAX_RETRIES: int = 2  # 回测任务失败自动重试次数
    BACKTEST_SOFT_TIME_LIMIT: int = 120  # Celery 任务软超时（秒）
    BACKTEST_HARD_TIME_LIMIT: int = 180  # Celery 任务硬超时（秒，触发后 worker 被终止重启）

    # ---- 回测沙箱子进程隔离（G08 · P1-4a）----
    # 策略执行从 worker 主进程移到独立子进程：死循环由父进程 terminate 兜底（不影响 worker 与其它任务），
    # CPU/内存硬上限由 rlimit 施加（**仅 POSIX 生效**，Windows 无 resource 模块，见 app/backtest/runner.py）。
    BACKTEST_SUBPROCESS_ENABLED: bool = True  # 置 false 退回进程内执行（仅本地排查用，无隔离保护）
    # 子进程启动方式：auto（POSIX=forkserver / Windows=spawn）/ fork / forkserver / spawn。
    # auto 刻意不用 fork —— Celery worker 是多线程进程，fork 子进程可能继承其它线程持有的锁而死锁
    # （Python 3.12 起发 DeprecationWarning，3.14 在 Linux 已默认改 forkserver）。
    # fork 更快（COW 共享 K 线、免 pickle），确需时可显式设 fork 自担风险。
    BACKTEST_SUBPROCESS_START_METHOD: str = "auto"
    BACKTEST_SUBPROCESS_GRACE: float = 15.0  # 子进程墙钟超时 = BACKTEST_TIME_BUDGET + 本值（秒）
    BACKTEST_CPU_LIMIT_SECONDS: int = 45  # 子进程 CPU 时间上限（秒，POSIX）；应 ≤ 墙钟超时
    BACKTEST_MEMORY_LIMIT_MB: int = 512  # 子进程内存**增长**上限（MB，POSIX）：限额 = 基线 VSZ + 本值
    BACKTEST_MAX_CONCURRENT_PER_USER: int = 3  # 同一用户同时运行的回测数上限，超出返回 429
    BACKTEST_QUEUE_BUSY_THRESHOLD: int = 20  # 回测队列积压超过该值即拒绝新任务（返回"队列繁忙"）
    BACKTEST_QUEUE_WAIT_PER_TASK_SECONDS: int = 30  # 队列繁忙时单任务平均耗时估算（秒），用于"预计等待 X 分钟"
    BACKTEST_QUOTA_STALE_SECONDS: int = 300  # 并发配额残留自愈阈值（秒）：worker 崩溃后超此值的槽位自动回收
    BACKTEST_ABNORMAL_FAIL_STREAK: int = 3  # G25：同一策略连续失败达该次数判为「异常策略」并计数告警

    # ---- 备份与灾难恢复（G05 · P1-1）----
    # 备份根目录：容器内挂独立卷 /backup，本地默认 data/backups。
    # 生产建议挂宿主机独立磁盘（与数据盘分离，避免同盘故障同时丢数据+备份）。
    BACKUP_DIR: str = str(_BASE_DIR / "data" / "backups")
    BACKUP_ENABLED: bool = True  # 备份任务总开关（本地不需要时置 false，beat 仍注册但任务直接返回）
    BACKUP_PG_RETAIN_DAYS: int = 30  # 逻辑全量备份（pg_dump）保留天数
    BACKUP_BASE_RETAIN_DAYS: int = 14  # 物理基础备份（pg_basebackup）保留天数：每周一次 → 留 2 代
    BACKUP_WAL_RETAIN_DAYS: int = 7  # WAL 归档保留天数（=PITR 可回溯窗口，与基础备份配合）
    BACKUP_FILES_RETAIN_DAYS: int = 7  # 文件镜像（记忆/导出）保留天数
    BACKUP_OFFSITE_RETAIN_DAYS: int = 90  # 异地保留天数（由对象存储生命周期策略执行，本地仅记录）
    BACKUP_PG_DUMP_MODE: str = "auto"  # pg_dump 取用方式：auto（先本地后 docker）/ local / docker
    BACKUP_PG_DUMP_BIN: str = "pg_dump"  # local 模式下的 pg_dump 可执行文件（可写绝对路径）
    BACKUP_PG_CONTAINER: str = "stock-invest-dev-db-1"  # docker 模式借用的 PG 容器名（宿主开发环境无 PG 客户端）
    BACKUP_DISK_MIN_FREE_PCT: float = 15.0  # 备份盘剩余空间告警阈值（百分比）
    BACKUP_MAX_AGE_HOURS: int = 26  # 最近一次成功备份超过该时长视为过期（监控告警用）
    BACKUP_VERIFY_DB: str = "stock_invest_verify"  # 恢复演练临时库名（验证后即删）
    PG_ARCHIVE_DIR: str = ""  # WAL 归档目录（与 db 容器 archive_command 一致，供归档状态检查；空=不检查）
    RCLONE_BIN: str = "rclone"  # rclone 可执行文件
    RCLONE_REMOTE: str = ""  # 对象存储远端，如 oss:stock-invest-backup；空=模拟模式（不真同步，仅记清单）
    RCLONE_CONFIG: str = ""  # rclone 配置文件路径；空则用 RCLONE_CONFIG_* / AWS_* 环境变量凭据

    # ---- 时区 ----
    TIMEZONE: str = "Asia/Shanghai"  # 展示用；DB 内一律存 UTC

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.TIMEZONE)


@lru_cache
def get_settings() -> Settings:
    return Settings()
