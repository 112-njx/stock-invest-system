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

# 用户鉴权 API（Auth）

## 1. 用户注册
接口名称：用户注册
请求 Method：POST
请求 Path：/api/v1/auth/register
接口作用：注册新用户（密码 bcrypt 哈希入库），成功后签发 JWT。
请求 Body：有（Body-JSON：username、password、email?、nickname?）
请求示例（curl）：`curl -X POST "http://127.0.0.1:8000/api/v1/auth/register" -H "Content-Type: application/json" -d '{"username":"alice","password":"pass123456","nickname":"Alice"}'`
成功返回示例：`{"code":0,"msg":"ok","data":{"token":"eyJhbGciOi...","user":{"id":1,"username":"alice","email":null,"nickname":"Alice","avatar_url":null,"created_at":"2026-08-09T05:00:00Z"}}}`

## 2. 用户登录
接口名称：用户登录
请求 Method：POST
请求 Path：/api/v1/auth/login
接口作用：用户名+密码校验，成功签发 JWT。
请求 Body：有（Body-JSON：username、password）
请求示例（curl）：`curl -X POST "http://127.0.0.1:8000/api/v1/auth/login" -H "Content-Type: application/json" -d '{"username":"alice","password":"pass123456"}'`
成功返回示例：`{"code":0,"msg":"ok","data":{"token":"eyJhbGciOi...","user":{"id":1,"username":"alice"}}}`

# 用户信息 API（Users）

## 1. 当前用户信息
接口名称：当前用户信息
请求 Method：GET
请求 Path：/api/v1/users/me
接口作用：获取当前登录用户信息。
请求 Body：无（Header：Authorization: Bearer <token>）
请求示例（curl）：`curl "http://127.0.0.1:8000/api/v1/users/me" -H "Authorization: Bearer eyJhbGciOi..."`
成功返回示例：`{"code":0,"msg":"ok","data":{"id":1,"username":"alice","email":null,"nickname":"Alice","avatar_url":null,"created_at":"2026-08-09T05:00:00Z"}}`

## 2. 更新当前用户
接口名称：更新当前用户
请求 Method：PUT
请求 Path：/api/v1/users/me
接口作用：更新昵称/头像。
请求 Body：有（Body-JSON：nickname?、avatar_url?）
请求示例（curl）：`curl -X PUT "http://127.0.0.1:8000/api/v1/users/me" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"nickname":"新昵称"}'`
成功返回示例：`{"code":0,"msg":"ok","data":{"id":1,"username":"alice","nickname":"新昵称","avatar_url":null}}`

# 重点关注股票 API（Watchlist）

## 1. 关注列表
接口名称：关注列表
请求 Method：GET
请求 Path：/api/v1/watchlist
接口作用：当前用户重点关注股票列表（合并实时快照：代码/名称/最新价/涨跌幅）。
请求 Body：无（Header：Authorization: Bearer <token>）
请求示例（curl）：`curl "http://127.0.0.1:8000/api/v1/watchlist" -H "Authorization: Bearer eyJhbGciOi..."`
成功返回示例：`{"code":0,"msg":"ok","data":[{"id":1,"symbol_id":125,"code":"600519","name":"贵州茅台","type":"stock","price":1309.22,"change":4.57,"change_pct":0.35,"updated_at":"2026-08-09T05:00:00Z","created_at":"2026-08-09T05:00:00Z"}]}`

## 2. 添加关注
接口名称：添加关注
请求 Method：POST
请求 Path：/api/v1/watchlist
接口作用：添加标的到关注列表（UNIQUE(user,symbol) 幂等，重复添加不报错）。
请求 Body：有（Body-JSON：symbol=标的代码或 symbol_id）
请求示例（curl）：`curl -X POST "http://127.0.0.1:8000/api/v1/watchlist" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"symbol":"600519"}'`
成功返回示例：`{"code":0,"msg":"添加成功","data":{"id":1,"symbol_id":125,"code":"600519","name":"贵州茅台","type":"stock","price":null,"change":null,"change_pct":null,"updated_at":null,"created_at":"2026-08-09T05:00:00Z"}}`

## 3. 删除关注
接口名称：删除关注
请求 Method：DELETE
请求 Path：/api/v1/watchlist/{watchlist_id}
接口作用：按关注记录 id 删除（仅本人可删）。
请求 Body：无（Path：watchlist_id）
请求示例（curl）：`curl -X DELETE "http://127.0.0.1:8000/api/v1/watchlist/1" -H "Authorization: Bearer eyJhbGciOi..."`
成功返回示例：`{"code":0,"msg":"删除成功","data":null}`

# 支撑/压力位 API（Support-Resistance）

## 1. 支撑压力位列表
接口名称：支撑压力位列表
请求 Method：GET
请求 Path：/api/v1/support-resistance
接口作用：当前用户支撑/压力位（可按标的过滤），K 线图叠加横线数据源。
请求 Body：无（Query：symbol_id?；Header：Authorization: Bearer <token>）
请求示例（curl）：`curl "http://127.0.0.1:8000/api/v1/support-resistance?symbol_id=125" -H "Authorization: Bearer eyJhbGciOi..."`
成功返回示例：`{"code":0,"msg":"ok","data":[{"id":1,"symbol_id":125,"type":"support","price":1200.0,"note":"强支撑","created_at":"2026-08-09T05:00:00Z"}]}`

## 2. 添加支撑压力位
接口名称：添加支撑压力位
请求 Method：POST
请求 Path：/api/v1/support-resistance
接口作用：添加支撑/压力位（type=support|pressure）。
请求 Body：有（Body-JSON：symbol=标的代码或 symbol_id、type、price、note?）
请求示例（curl）：`curl -X POST "http://127.0.0.1:8000/api/v1/support-resistance" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"symbol":"600519","type":"support","price":1200,"note":"强支撑"}'`
成功返回示例：`{"code":0,"msg":"添加成功","data":{"id":1,"symbol_id":125,"type":"support","price":1200.0,"note":"强支撑","created_at":"2026-08-09T05:00:00Z"}}`

## 3. 删除支撑压力位
接口名称：删除支撑压力位
请求 Method：DELETE
请求 Path：/api/v1/support-resistance/{sr_id}
接口作用：删除支撑/压力位记录（仅本人可删）。
请求 Body：无（Path：sr_id）
请求示例（curl）：`curl -X DELETE "http://127.0.0.1:8000/api/v1/support-resistance/1" -H "Authorization: Bearer eyJhbGciOi..."`
成功返回示例：`{"code":0,"msg":"删除成功","data":null}`

# 技术指标 API（Indicators）

## 1. 技术指标查询
接口名称：技术指标查询
请求 Method：GET
请求 Path：/api/v1/indicators
接口作用：服务端计算 MACD/KDJ/成交量/成交额（前端只渲染不计算），Redis 缓存（key 含 K 线最新 ts，新数据到达自动失效）。
请求 Body：无（Query：symbol=代码或 id、period=15m|1d|1w|1mon、names=逗号分隔指标名、start?、end?、limit?、params?=JSON 指标参数）
请求示例（curl）：`curl "http://127.0.0.1:8000/api/v1/indicators?symbol=600519&period=1d&names=macd,kdj&params=%7B%22kdj%22%3A%7B%22n%22%3A9%7D%7D"`
成功返回示例：`{"code":0,"msg":"ok","data":[{"ts":"2026-08-07T08:00:00","open":1308.66,"high":1315.28,"low":1301.0,"close":1309.22,"volume":24976,"amount":3266919421.0,"macd_dif":29.46,"macd_dea":33.11,"macd_hist":-7.30,"kdj_k":44.22,"kdj_d":59.02,"kdj_j":14.63},...]}`