# Python Research Service

数据采集与策略回测 Worker 服务。

## 环境准备

```bash
cd python-research-service
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
```

## 配置

复制 `.env.example` 为 `.env`，按需修改数据库连接信息。

## 使用

### 单股补数

```bash
python scripts/ingest_single.py --symbol sh600519 --months 3
```

参数说明：
- `--symbol`: 股票代码，格式 `sh600519` / `sz000001`
- `--months`: 回溯月数（默认 3）
- `--start` / `--end`: 指定日期范围（YYYY-MM-DD）
- `--adjust`: 复权类型 `qfq` / `hfq` / `` (默认 qfq)
- `--no-write`: 仅拉取打印，不写库

### 批量补数

```bash
python scripts/ingest_batch.py --symbols sh600519,sz000001,sz000002 --months 6
```

### 运行测试

```bash
pip install pytest
pytest tests/ -v
```
