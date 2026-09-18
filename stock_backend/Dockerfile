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
# 运维工具（G05 · P1-1 备份与灾难恢复）：
#   - postgresql-client-16：备份/恢复所需的 pg_dump / pg_restore / psql。
#     **客户端主版本必须 ≥ 服务端主版本**，否则 pg_dump 直接拒绝执行（本项目服务端为 PG16，
#     Debian bookworm 自带的 client-15 不可用），故从 PGDG 装 16；PGDG 不可达时回退发行版包
#     （回退后版本可能不匹配，备份任务会在 check_client_version() 处明确失败，而非产出坏备份）。
#   - rsync：文件备份镜像；rclone：异地同步到对象存储（未安装时 sync_offsite 返回明确失败）。
RUN set -eux; \
    # 国内网络加速：替换 Debian 官方源为清华镜像（deb.debian.org 国内直连超时导致 apt 构建失败，
    # 与上方 PyPI 清华源策略一致；PGDG 源不可达时下方已有 fallback 到发行版 postgresql-client）
    sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn/debian-security|g' \
        /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
    sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn/debian-security|g' \
        /etc/apt/sources.list 2>/dev/null || true; \
    apt-get update; \
    apt-get install -y --no-install-recommends tzdata curl ca-certificates gnupg rsync rclone; \
    if ( \
        install -d /usr/share/postgresql-common/pgdg; \
        curl -fsSL --connect-timeout 20 -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
            https://www.postgresql.org/media/keys/ACCC4CF8.asc; \
        echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
            > /etc/apt/sources.list.d/pgdg.list; \
        apt-get update; \
        apt-get install -y --no-install-recommends postgresql-client-16; \
    ); then \
        echo "installed postgresql-client-16 from PGDG"; \
    else \
        echo "PGDG unreachable, falling back to distro postgresql-client (may mismatch server major)"; \
        rm -f /etc/apt/sources.list.d/pgdg.list; \
        apt-get update; \
        apt-get install -y --no-install-recommends postgresql-client; \
    fi; \
    pg_dump --version; \
    rm -rf /var/lib/apt/lists/*
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
