FROM rust:1.89-bookworm AS market-indicators-build
WORKDIR /build
ENV PYO3_NO_PYTHON=1
COPY native/market_indicators/Cargo.toml native/market_indicators/Cargo.lock ./
COPY native/market_indicators/src ./src
RUN cargo build --release --locked

FROM python:3.12-slim-bookworm AS legacy
ARG STOCKDB_URL=https://github.com/hello245m/free-stockdb/releases/download/%E6%B5%8B%E8%AF%95%E7%89%88%E6%9C%AC0.3.5/free-stockdb-manylinux-x64-v0.3.5-more-power.tar
ARG STOCKDB_SHA256=9ec47250f60cd35462446dfcf34db99ef33e6b73b3f02f0970ef329722c265cf
WORKDIR /opt/stockdb
RUN STOCKDB_URL="$STOCKDB_URL" STOCKDB_SHA256="$STOCKDB_SHA256" python -c "import urllib.request,hashlib,os; p='/tmp/stockdb.tar'; urllib.request.urlretrieve(os.environ['STOCKDB_URL'],p); assert hashlib.sha256(open(p,'rb').read()).hexdigest()==os.environ['STOCKDB_SHA256']" \
    && tar -xf /tmp/stockdb.tar -C /opt && rm /tmp/stockdb.tar \
    && chmod +x /opt/stockdb/stockdb /opt/stockdb/数据更新
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=Asia/Shanghai
COPY deploy/stockdb/LICENSE.stockdb /opt/stockdb/LICENSE
COPY deploy/stockdb/stockdb.conf /opt/stockdb/stockdb.conf
COPY deploy/stockdb/supervise.py deploy/stockdb/healthcheck.py deploy/stockdb/update_control.py /opt/
COPY stock_backend/app/services/stockdb_files.py /opt/stockdb_files.py
COPY stock_backend/app/services/indicator_registry.py stock_backend/app/services/indicator_catalog.json /opt/
COPY scripts/stockdb_sdk_bridge.py scripts/market_indicator_library.py /opt/
COPY --from=market-indicators-build /build/target/release/libmarket_indicators.so /opt/market_indicators.abi3.so
RUN PYTHONPATH=/opt python -c "import market_indicators; assert market_indicators.FEATURE_VERSION >= 1"
EXPOSE 7899 7900
ENTRYPOINT ["python", "/opt/supervise.py"]

FROM debian:bookworm-slim AS leveldb-build
ARG LEVELDB_REV=bb74ef739973a70ca9f0d90788a1da89b788c0ad
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl cmake g++ make libzstd-dev libsnappy-dev
RUN mkdir /src && curl -fsSL "https://codeload.github.com/google/leveldb/tar.gz/${LEVELDB_REV}" | tar xz --strip-components=1 -C /src \
    && grep -q '^void DBImpl::MaybeScheduleCompaction() {' /src/db/db_impl.cc \
    && sed -i '/^void DBImpl::MaybeScheduleCompaction() {/a\  return;  // Read-only snapshot reader: never compact linked source tables.' /src/db/db_impl.cc \
    && sed -i 's/check_library_exists(zstd zstd_compress /check_library_exists(zstd ZSTD_compress /' /src/CMakeLists.txt \
    && cmake -S /src -B /build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DLEVELDB_BUILD_TESTS=OFF -DLEVELDB_BUILD_BENCHMARKS=OFF \
    && grep -q '^HAVE_ZSTD:INTERNAL=1' /build/CMakeCache.txt \
    && cmake --build /build -j2 && cmake --install /build --prefix /out

FROM legacy AS market-data-local
RUN apt-get update && apt-get install -y --no-install-recommends libsnappy1v5 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir msgpack==1.1.2
COPY --from=leveldb-build /out/lib/libleveldb.so* /usr/local/lib/
COPY --from=leveldb-build /src/LICENSE /opt/stockdb/LICENSE.leveldb
COPY deploy/stockdb/market_data_reader.py deploy/stockdb/market_data_sdk.py /opt/
ENV STOCKDB_READER=managed

FROM legacy AS stockdb-local
