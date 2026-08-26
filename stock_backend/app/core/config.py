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
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # token 有效期 7 天
    ADMIN_USERNAMES: str = "root"  # 管理员用户名（逗号分隔），启动时自动置 is_admin=true

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

    # ---- 本地记忆（ChromaDB 持久化 + 人类可读记忆文件，本地存储约束）----
    MEMORY_DIR: str = str(_BASE_DIR / "data" / "memory")  # 记忆文件根目录（M 区可打开）
    CHROMA_DIR: str = str(_BASE_DIR / "data" / "chroma")  # 向量库持久化目录
    MEMORY_TOP_K: int = 5  # 记忆检索注入条数
    MEMORY_IMPORTANCE_MIN: int = 5  # 抽取时重要性低于该值不入库（噪音过滤）

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

    # ---- 时区 ----
    TIMEZONE: str = "Asia/Shanghai"  # 展示用；DB 内一律存 UTC

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.TIMEZONE)


@lru_cache
def get_settings() -> Settings:
    return Settings()
