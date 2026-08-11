# ---------- 阶段一：builder（安装依赖，requirements.lock 层缓存） ----------
FROM python:3.12-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
# 国内网络加速：默认清华 PyPI 镜像 + 加长超时/重试，避免 pip 连国外 PyPI 源 ReadTimeout 构建失败。
# 需要自定义镜像源时构建传参覆盖：docker compose build --build-arg PIP_INDEX_URL=<镜像地址>
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_DEFAULT_TIMEOUT=300
ARG PIP_RETRIES=10
WORKDIR /build
COPY stock_backend/requirements.lock ./requirements.lock
RUN pip install --prefix=/install --index-url "${PIP_INDEX_URL}" --timeout "${PIP_DEFAULT_TIMEOUT}" --retries "${PIP_RETRIES}" -r requirements.lock

# ---------- 阶段二：runner（仅运行时产物，非 root 用户） ----------
FROM python:3.12-slim AS runner
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 TZ=Asia/Shanghai
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata curl \
    && rm -rf /var/lib/apt/lists/*
# 仅拷贝 builder 安装的 site-packages，镜像不含源码/编译缓存
COPY --from=builder /install /usr/local
RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY --chown=app:app stock_backend/ ./
# 固定指数种子 SQL（seed 脚本按 parents[2]/docs/sql 定位）
COPY --chown=app:app docs/sql/02_seed_fixed_indices.sql /docs/sql/02_seed_fixed_indices.sql
COPY --chown=app:app stock_backend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh \
    && mkdir -p /app/data/memory /app/data/chroma \
    && chown -R app:app /app/data
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1
ENTRYPOINT ["/docker-entrypoint.sh"]
# API 服务默认命令；worker/beat 由 docker-compose command 覆盖
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
