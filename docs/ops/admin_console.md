# 管理控制台

- 入口位于顶部股票搜索框左侧，沿用现有 root 管理员入口与路由限制；服务端接口继续执行管理员鉴权。
- `/admin?section=overview|sources|tasks|requests|display` 对应运行概览、行情与数据源、任务与队列、请求监控、显示设置。
- 本地行情日期是贵州茅台日 K 的连接采样日期，不作为全市场完整性证明。数据库与历史计算服务分别检测，单项失败不影响另一项结果。
- 本地手动同步负责项目导入；管理员仍需先完成 stockdb 数据文件更新。任务分类遵循实际投递队列，并统计 `local_market_sync` 的持久化失败状态。
- Worker 状态表示是否观测到在线消费者，未观测到可能是未部署、离线或检查超时，不直接判定服务故障。
- 数据源开关、请求保护、影线设置均显式保存，失败保留草稿。刷新不会覆盖未保存输入，保存前的旧读取响应不会回写旧配置。
- 请求监控每 3 秒轮询，队列每 10 秒轮询；概览和数据源页检查同步任务，运行时缩短到 3 秒。页面隐藏或卸载时停止定时器，进行中的请求不重复发起。同步结束后重新检查服务与队列。
- 源策略、调用预算和影线配置沿用原有接口；新增只读 `/api/v1/admin/local-services`，通过有超时限制的本地检查返回连接状态。

验证：

```powershell
cd stock_backend
.venv/Scripts/python.exe -m pytest tests/test_admin_console.py tests/test_admin_api.py -q
cd ../stock_frontend
node scripts/verify-admin-console.mjs
npm run build
```

视觉检查可使用 `node scripts/verify-admin-console.mjs --preview` 生成独立本地预览。预览使用受控测试数据，不连接实际管理接口。
