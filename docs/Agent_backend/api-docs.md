api文档，你需要按照：
大标题api分类，分类下的序号
接口名称：
请求 Method：
请求 Path：
接口作用：
请求 Body：有无（参数位置：Query/Path/Body-JSON） --->上面到这些,需要符合简洁的特征,均一句话或一个单词概括
请求示例（curl）
成功返回示例
进行编写所有的软件api.

---

# 行情查询 API（Market）

## 1. 标的列表
接口名称：标的列表
请求 Method：GET
请求 Path：/api/v1/symbols
接口作用：标的列表（type/search/is_fixed 过滤），供下拉选择与 G/H 区固定指数列表。
请求 Body：无（Query：type=stock|etf|index、search、is_fixed=0|1）
请求示例（curl）：`curl "http://127.0.0.1:8000/api/v1/symbols?type=index&is_fixed=1"`
成功返回示例：`{"code":0,"msg":"ok","data":[{"id":70,"code":"000001","name":"上证指数","type":"index","market":"SSE","etf_linked":"","is_fixed_index":true,"sort_order":1},...]}`

## 2. 标的搜索联想
接口名称：标的搜索联想
请求 Method：GET
请求 Path：/api/v1/symbols/search
接口作用：6位代码/名称联想（已入库优先，精确代码优先）。
请求 Body：无（Query：q=代码或名称）
请求示例（curl）：`curl "http://127.0.0.1:8000/api/v1/symbols/search?q=600519"`
成功返回示例：`{"code":0,"msg":"ok","data":[{"id":125,"code":"600519","name":"贵州茅台","type":"stock","market":"SSE"}]}`

## 3. K线查询
接口名称：K线查询
请求 Method：GET
请求 Path：/api/v1/kline
接口作用：多周期K线（15m/1d/1w/1mon，区间/分页），时间 UTC。
请求 Body：无（Query：symbol=代码、period、start、end、limit、offset）
请求示例（curl）：`curl "http://127.0.0.1:8000/api/v1/kline?symbol=600519&period=1d"`
成功返回示例：`{"code":0,"msg":"ok","data":[{"ts":"2026-08-07T08:00:00","open":1308.66,"high":1315.28,"low":1301.0,"close":1309.22,"volume":24976,"amount":3266919421.0},...]}`

## 4. 批量实时快照
接口名称：批量实时快照
请求 Method：GET
请求 Path：/api/v1/snapshot
接口作用：批量实时快照（合并特殊字段：个股 market_cap/pe、ETF nav/premium、指数 pe）。
请求 Body：无（Query：symbols=逗号分隔的 symbol_id）
请求示例（curl）：`curl "http://127.0.0.1:8000/api/v1/snapshot?symbols=70,125"`
成功返回示例：`{"code":0,"msg":"ok","data":[{"symbol_id":70,"code":"000001","name":"上证指数","type":"index","price":null,"extra":{}},...]}`