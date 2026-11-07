FROM python:3.12-slim-bookworm
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
COPY scripts/stockdb_online.py scripts/stockdb_online_catalog.py scripts/stockdb_online_requests.py scripts/stockdb_online_tables.json /opt/
COPY scripts/stockdb_sdk_bridge.py /opt/stockdb_sdk_bridge.py
EXPOSE 7899 7900
ENTRYPOINT ["python", "/opt/supervise.py"]
