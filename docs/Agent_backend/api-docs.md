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

- **接口名称**：标的列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/symbols
- **接口作用**：标的列表（type/search/is_fixed 过滤），供下拉选择与 G/H 区固定指数列表。
- **请求 Body**：无（Query：type=stock|etf|index、search、is_fixed=0|1）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/symbols?type=index&is_fixed=1"
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":70,"code":"000001","name":"上证指数","type":"index","market":"SSE","etf_linked":"","is_fixed_index":true,"sort_order":1},...]}
```

## 2. 标的搜索联想

- **接口名称**：标的搜索联想
- **请求 Method**：GET
- **请求 Path**：/api/v1/symbols/search
- **接口作用**：6位代码/名称联想（已入库优先，精确代码优先）。
- **请求 Body**：无（Query：q=代码或名称）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/symbols/search?q=600519"
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":125,"code":"600519","name":"贵州茅台","type":"stock","market":"SSE"}]}
```

## 3. K线查询

- **接口名称**：K线查询
- **请求 Method**：GET
- **请求 Path**：/api/v1/kline
- **接口作用**：多周期K线（15m/1d/1w/1mon，区间/分页），时间 UTC。
- **请求 Body**：无（Query：symbol=代码、period、start、end、limit、offset）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/kline?symbol=600519&period=1d"
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"ts":"2026-08-07T08:00:00","open":1308.66,"high":1315.28,"low":1301.0,"close":1309.22,"volume":24976,"amount":3266919421.0},...]}
```

## 4. 批量实时快照

- **接口名称**：批量实时快照
- **请求 Method**：GET
- **请求 Path**：/api/v1/snapshot
- **接口作用**：批量实时快照（合并特殊字段：个股 market_cap/pe、ETF nav/premium、指数 pe）。
- **请求 Body**：无（Query：symbols=逗号分隔的 symbol_id）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/snapshot?symbols=70,125"
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"symbol_id":70,"code":"000001","name":"上证指数","type":"index","price":null,"extra":{}},...]}
```

## 5. 同步状态查询

- **接口名称**：同步状态查询
- **请求 Method**：GET
- **请求 Path**：/api/v1/sync-status
- **接口作用**：查询某同步范围（fixed_indices/catalog/watchlist）的最新同步进度，行情页加载时轮询展示"数据同步中（X/49）"。
- **请求 Body**：无（Query：scope=fixed_indices|watchlist|catalog）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/sync-status?scope=fixed_indices"
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"status":"running","progress":35,"total":49,"message":"已同步 35/49"}}
```

（无进行中同步时返回 `{"status":"done","progress":100,"total":0,"message":"无进行中的同步"}`）

## 6. 一次性全量同步

- **接口名称**：一次性全量同步
- **请求 Method**：POST
- **请求 Path**：/api/v1/fetch-all
- **接口作用**：免鉴权，同步执行固定指数K线+快照 + 全量实时快照（本地测试无 Celery/beat 时一次性补齐数据）。
- **请求 Body**：无

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/fetch-all"
```

**成功返回示例**

```json
{"code":0,"msg":"全量同步完成","data":{"fixed_indices":{"000001":{"1d":1,"1w":1,"1mon":1}},"realtime":{"synced":49}}}
```

# 用户鉴权 API（Auth）

## 1. 用户注册

- **接口名称**：用户注册
- **请求 Method**：POST
- **请求 Path**：/api/v1/auth/register
- **接口作用**：注册新用户（密码 bcrypt 哈希入库），成功后签发 JWT 并发送邮箱验证邮件。
- **请求 Body**：有（Body-JSON：username、password、**email（必填）**、nickname?）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/register" -H "Content-Type: application/json" -d '{"username":"alice","password":"pass123456","email":"alice@example.com","nickname":"Alice"}'
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"token":"eyJhbGciOi...","user":{"id":1,"username":"alice","email":"alice@example.com","email_verified":false,"nickname":"Alice","avatar_url":null,"created_at":"2026-08-09T05:00:00Z"}}}
```

> 邮箱必填（缺失 422）；邮箱已注册返回 `{"code":40002,"msg":"该邮箱已被注册"}`。

## 2. 用户登录

- **接口名称**：用户登录
- **请求 Method**：POST
- **请求 Path**：/api/v1/auth/login
- **接口作用**：用户名+密码校验，成功签发 JWT。
- **请求 Body**：有（Body-JSON：username、password）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/login" -H "Content-Type: application/json" -d '{"username":"alice","password":"pass123456"}'
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"token":"eyJhbGciOi...","user":{"id":1,"username":"alice"}}}
```

> **G19 双 token 变更**：登录/注册成功后在响应体返回 access token（15min），同时通过 `Set-Cookie` 种下 `refresh_token`（HttpOnly / Secure / SameSite=Lax / Path=/api/v1/auth，7d）。

## 3. 刷新令牌

- **接口名称**：刷新令牌
- **请求 Method**：POST
- **请求 Path**：/api/v1/auth/refresh
- **接口作用**：从 Cookie 读 refresh token → 校验 → 轮换签发新 access + 新 refresh；旧 refresh 入 Redis 黑名单。复用检测：旧 refresh 被用两次则吊销该用户全部会话。
- **请求 Body**：无（Cookie：refresh_token）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/refresh" -b "refresh_token=xxx"
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"token":"eyJhbGciOi..."}}
```

> 响应不返回 refresh 明文（仅通过 Set-Cookie 下发）。

## 4. 登出

- **接口名称**：登出
- **请求 Method**：POST
- **请求 Path**：/api/v1/auth/logout
- **接口作用**：access token 的 jti 入 Redis 黑名单 + refresh session 标记吊销 + 清 Cookie。
- **请求 Body**：无（Header：Authorization: Bearer <token>；Cookie：refresh_token）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/logout" -H "Authorization: Bearer eyJhbGciOi..." -b "refresh_token=xxx"
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":null}
```

## 5. 活跃设备列表

- **接口名称**：活跃设备列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/auth/sessions
- **接口作用**：返回当前用户所有活跃会话（未过期未吊销），标记当前设备。
- **请求 Body**：无（Header：Authorization: Bearer <token>；Cookie：refresh_token）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/auth/sessions" -H "Authorization: Bearer eyJhbGciOi..." -b "refresh_token=xxx"
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":1,"user_agent":"Mozilla/5.0 ...","ip_address":"127.0.0.1","created_at":"2026-09-17T05:00:00Z","expires_at":"2026-09-24T05:00:00Z","is_current":true}]}
```

## 6. 踢出设备

- **接口名称**：踢出设备
- **请求 Method**：DELETE
- **请求 Path**：/api/v1/auth/sessions/{id}
- **接口作用**：吊销指定会话（refresh 失效，已签发 access 通过黑名单失效）；仅限本人会话，越权返回 404。
- **请求 Body**：无（Path：id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/auth/sessions/2" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":null}
```

> **G01 安全加固备注（2026-09-17）**：
> - CORS 已从通配符 `*` 改为环境变量 `CORS_ORIGINS` 白名单，仅白名单内来源可携带凭证。
> - 后端新增 Cookie 安全工具（`set_access_token_cookie` / `clear_access_token_cookie`），属性：HttpOnly / Secure / SameSite=Lax / Path=/。G19 双 token 启用后，登录/刷新响应将额外设置 HttpOnly Cookie。
> - Nginx 补充 HSTS / CSP / X-Frame-Options DENY / X-Content-Type-Options / Referrer-Policy 五项安全响应头。
> - 生产 HTTPS：设置 `SSL_REDIRECT=true` + `COOKIE_SECURE=true` + 挂载 TLS 证书到 `/etc/nginx/certs/` 后取消 nginx.conf 443 块注释即可启用。
> - G19 已新增端点见上方 3~6 节：`POST /auth/refresh`、`POST /auth/logout`、`GET /auth/sessions`、`DELETE /auth/sessions/{id}`。

> **G23 邮箱验证/密码重置备注（2026-09-17）**：
> - **注册 `email` 改为必填**，注册后自动发送验证邮件（10 分钟有效链接），并校验邮箱唯一性（重复邮箱返回 `40002`）。
> - **登录暴力保护**：同一用户名连续失败 5 次后锁定 15 分钟，锁定期间登录返回 `423`（业务码 `42301`）；登录成功后失败计数清零。计数器存 Redis `login_fail:{username}`（Redis 不可用时降级放行，不影响可用性）。
> - 邮箱验证/密码重置 token 与 access token 独立签名（派生密钥 + `type` 字段），验证 token 不能用于重置、反之亦然。
> - `UserOut` 新增 `email_verified` 字段。

## 7. 邮箱验证

- **接口名称**：邮箱验证
- **请求 Method**：GET
- **请求 Path**：/api/v1/auth/verify-email
- **接口作用**：校验验证邮件中的 token（10min 有效），标记用户邮箱已验证；重复验证返回成功提示。
- **请求 Body**：无（Query：token）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/auth/verify-email?token=eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"message":"邮箱验证成功"}}
```

（token 无效/过期返回 `{"code":40010,"msg":"验证链接无效或已过期"}`）

## 8. 忘记密码

- **接口名称**：忘记密码（发送重置邮件）
- **请求 Method**：POST
- **请求 Path**：/api/v1/auth/forgot-password
- **接口作用**：按邮箱发送密码重置邮件（1h 有效链接）。**无论邮箱是否已注册均返回相同成功响应**（防邮箱枚举）。
- **请求 Body**：有（Body-JSON：email）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/forgot-password" -H "Content-Type: application/json" -d '{"email":"alice@example.com"}'
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"message":"如果该邮箱已注册，重置密码邮件已发送，请查收邮箱"}}
```

## 9. 重置密码

- **接口名称**：重置密码
- **请求 Method**：POST
- **请求 Path**：/api/v1/auth/reset-password
- **接口作用**：校验重置 token（1h 有效）→ 更新密码 → **吊销该用户全部 refresh token**（所有设备强制重新登录）。
- **请求 Body**：有（Body-JSON：token、new_password）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/reset-password" -H "Content-Type: application/json" -d '{"token":"eyJhbGciOi...","new_password":"newpass789"}'
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"message":"密码重置成功，请使用新密码登录"}}
```

（token 无效/过期返回 `{"code":40012,"msg":"重置链接无效或已过期"}`）

## 10. 恢复账户（G18）

- **接口名称**：恢复已注销账户
- **请求 Method**：POST
- **请求 Path**：/api/v1/auth/restore-account
- **接口作用**：**30 天宽限期内**用原用户名+密码恢复已注销账户，成功后签发新双 token（access + refresh Cookie）。超过宽限期返回 `410/41001`。
- **请求 Body**：有（Body-JSON：username、password）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/auth/restore-account" -H "Content-Type: application/json" -d '{"username":"alice","password":"pass123456"}'
```

**成功返回示例**

```json
{"code":0,"msg":"账户已恢复","data":{"token":"eyJhbGciOi...","user":{"id":1,"username":"alice","is_deleted":false}}}
```

（用户名/密码错误返回 401/40101；账户未注销返回 `400/40041`；超宽限期返回 `410/41001`）

# 用户信息 API（Users）

## 1. 当前用户信息


- **接口名称**：当前用户信息
- **请求 Method**：GET
- **请求 Path**：/api/v1/users/me
- **接口作用**：获取当前登录用户信息。
- **请求 Body**：无（Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/users/me" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"id":1,"username":"alice","email":null,"nickname":"Alice","avatar_url":null,"created_at":"2026-08-09T05:00:00Z"}}
```

## 2. 更新当前用户

- **接口名称**：更新当前用户
- **请求 Method**：PUT
- **请求 Path**：/api/v1/users/me
- **接口作用**：更新昵称/头像。
- **请求 Body**：有（Body-JSON：nickname?、avatar_url?）

**请求示例（curl）**

```bash
curl -X PUT "http://127.0.0.1:8000/api/v1/users/me" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"nickname":"新昵称"}'
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"id":1,"username":"alice","nickname":"新昵称","avatar_url":null}}
```

## 3. 修改密码（G33）

- **接口名称**：修改密码
- **请求 Method**：PUT
- **请求 Path**：/api/v1/users/me/password
- **接口作用**：已登录用户改密（需旧密码校验），成功后**吊销该用户全部 refresh token**，所有设备需重新登录。
- **请求 Body**：有（Body-JSON：old_password、new_password；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X PUT "http://127.0.0.1:8000/api/v1/users/me/password" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"old_password":"pass123456","new_password":"newpass789"}'
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"message":"密码修改成功，请重新登录"}}
```

（旧密码错误返回 `40003`；新旧密码相同返回 `40004`；新密码 <6 位返回 422）

## 4. 修改邮箱（G33）

- **接口名称**：修改邮箱
- **请求 Method**：PUT
- **请求 Path**：/api/v1/users/me/email
- **接口作用**：已登录用户改邮箱（需密码校验），新邮箱置 `email_verified=false` 并向新邮箱发送验证邮件。
- **请求 Body**：有（Body-JSON：password、new_email；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X PUT "http://127.0.0.1:8000/api/v1/users/me/email" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"password":"pass123456","new_email":"new@example.com"}'
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"message":"邮箱已更新，请查收验证邮件完成验证"}}
```

（密码错误返回 `40003`；新邮箱与当前相同返回 `40005`；新邮箱已被他人注册返回 `40002`）

## 5. 查询自填 API Key 状态（G14）

- **接口名称**：查询自填 API Key 状态
- **请求 Method**：GET
- **请求 Path**：/api/v1/users/me/api-key
- **接口作用**：返回当前用户是否已配置自填 DeepSeek API Key，以及掩码形式（如 `sk-abcd****wxyz`）。**服务端只回掩码，任何响应都不回显明文**。个人设置页「AI 模型设置」数据源。
- **请求 Body**：无（Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/users/me/api-key" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"has_api_key":true,"masked":"sk-abcd****wxyz"}}
```

## 6. 设置 / 清除自填 API Key（G14）

- **接口名称**：设置自填 API Key
- **请求 Method**：PUT
- **请求 Path**：/api/v1/users/me/api-key
- **接口作用**：保存用户自填的 DeepSeek API Key（AES-256-GCM 密文存储）。保存后 AI 调用**优先使用用户 Key**；传空串表示清除，回退服务端默认 Key。格式要求 `sk-` 前缀 + 32 位以上字符。
- **请求 Body**：有（Body-JSON：api_key；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X PUT "http://127.0.0.1:8000/api/v1/users/me/api-key" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"api_key":"sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}'
```

**成功返回示例**

```json
{"code":0,"msg":"已保存","data":{"has_api_key":true,"masked":"sk-xxxx****xxxx"}}
```

（格式不合法返回 `40030`；清除时 `api_key` 传空串，返回 `has_api_key=false`）

> 累计 token 用量（估算值，非精确计费）随 `GET /api/v1/users/me` 返回：`llm_tokens_prompt` / `llm_tokens_completion` / `llm_tokens_total`。

## 7. 创建数据导出任务（G17）

- **接口名称**：创建数据导出任务
- **请求 Method**：POST
- **请求 Path**：/api/v1/users/me/export
- **接口作用**：异步创建全量个人数据导出任务（Celery），生成 ZIP：账号信息、关注列表、支撑压力位、交易策略（JSON+代码 .py）、回测任务与结果、会话与消息、Agent 配置与运行记录、记忆事实与原始 md 文件。文件存临时目录，**24h 后自动删除**。
- **请求 Body**：无（Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/users/me/export" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"导出任务已提交","data":{"task_id":1,"status":"pending","progress":0,"file_size":null,"error":null,"created_at":"2026-09-17T08:00:00Z","finished_at":null,"expires_at":"2026-09-18T08:00:00Z","download_url":null}}
```

## 8. 查询导出任务状态（G17）

- **接口名称**：导出任务状态
- **请求 Method**：GET
- **请求 Path**：/api/v1/users/me/export/{task_id}
- **接口作用**：查询导出进度（pending/running/success/failed/expired）；成功后返回**带签名 token 的下载链接**（30 分钟有效）。
- **请求 Body**：无（Path：task_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/users/me/export/1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"task_id":1,"status":"success","progress":100,"file_size":20480,"error":null,"created_at":"...","finished_at":"...","expires_at":"2026-09-18T08:00:00Z","download_url":"/api/v1/users/me/export/1/download?token=eyJhbGciOi..."}}
```

（任务不存在/越权查询他人任务返回 404/40420）

## 9. 下载导出文件（G17）

- **接口名称**：下载导出 ZIP
- **请求 Method**：GET
- **请求 Path**：/api/v1/users/me/export/{task_id}/download
- **接口作用**：按**签名 token** 下载导出 ZIP（token 含 user_id + task_id，防越权；30 分钟有效）。
- **请求 Body**：无（Path：task_id；Query：token）

**请求示例（curl）**

```bash
curl -OJ "http://127.0.0.1:8000/api/v1/users/me/export/1/download?token=eyJhbGciOi..."
```

**成功返回**：`application/zip` 二进制流（`Content-Disposition: attachment; filename=export_user1_1_20260917_080000.zip`）

（token 无效/过期/不匹配返回 403/40301；任务未完成返回 400/40030；文件已过期被清理返回 404/40421）

# 重点关注股票 API（Watchlist）

## 1. 关注列表

- **接口名称**：关注列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/watchlist
- **接口作用**：当前用户重点关注股票列表（合并实时快照：代码/名称/最新价/涨跌幅）。
- **请求 Body**：无（Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/watchlist" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":1,"symbol_id":125,"code":"600519","name":"贵州茅台","type":"stock","price":1309.22,"change":4.57,"change_pct":0.35,"updated_at":"2026-08-09T05:00:00Z","created_at":"2026-08-09T05:00:00Z"}]}
```

## 2. 添加关注

- **接口名称**：添加关注
- **请求 Method**：POST
- **请求 Path**：/api/v1/watchlist
- **接口作用**：添加标的到关注列表（UNIQUE(user,symbol) 幂等，重复添加不报错）。
- **请求 Body**：有（Body-JSON：symbol=标的代码或 symbol_id）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/watchlist" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"symbol":"600519"}'
```

**成功返回示例**

```json
{"code":0,"msg":"添加成功","data":{"id":1,"symbol_id":125,"code":"600519","name":"贵州茅台","type":"stock","price":null,"change":null,"change_pct":null,"updated_at":null,"created_at":"2026-08-09T05:00:00Z"}}
```

## 3. 删除关注

- **接口名称**：删除关注
- **请求 Method**：DELETE
- **请求 Path**：/api/v1/watchlist/{watchlist_id}
- **接口作用**：按关注记录 id 删除（仅本人可删）。
- **请求 Body**：无（Path：watchlist_id）

**请求示例（curl）**

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/watchlist/1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"删除成功","data":null}
```

# 支撑/压力位 API（Support-Resistance）

## 1. 支撑压力位列表

- **接口名称**：支撑压力位列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/support-resistance
- **接口作用**：当前用户支撑/压力位（可按标的过滤），K 线图叠加横线数据源。
- **请求 Body**：无（Query：symbol_id?；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/support-resistance?symbol_id=125" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":1,"symbol_id":125,"type":"support","price":1200.0,"note":"强支撑","created_at":"2026-08-09T05:00:00Z"}]}
```

## 2. 添加支撑压力位

- **接口名称**：添加支撑压力位
- **请求 Method**：POST
- **请求 Path**：/api/v1/support-resistance
- **接口作用**：添加支撑/压力位（type=support|pressure）。
- **请求 Body**：有（Body-JSON：symbol=标的代码或 symbol_id、type、price、note?）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/support-resistance" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"symbol":"600519","type":"support","price":1200,"note":"强支撑"}'
```

**成功返回示例**

```json
{"code":0,"msg":"添加成功","data":{"id":1,"symbol_id":125,"type":"support","price":1200.0,"note":"强支撑","created_at":"2026-08-09T05:00:00Z"}}
```

## 3. 删除支撑压力位

- **接口名称**：删除支撑压力位
- **请求 Method**：DELETE
- **请求 Path**：/api/v1/support-resistance/{sr_id}
- **接口作用**：删除支撑/压力位记录（仅本人可删）。
- **请求 Body**：无（Path：sr_id）

**请求示例（curl）**

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/support-resistance/1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"删除成功","data":null}
```

# 技术指标 API（Indicators）

## 1. 技术指标查询

- **接口名称**：技术指标查询
- **请求 Method**：GET
- **请求 Path**：/api/v1/indicators
- **接口作用**：服务端计算 MACD/KDJ/成交量/成交额（前端只渲染不计算），Redis 缓存（key 含 K 线最新 ts，新数据到达自动失效）。
- **请求 Body**：无（Query：symbol=代码或 id、period=15m|1d|1w|1mon、names=逗号分隔指标名、start?、end?、limit?、params?=JSON 指标参数）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/indicators?symbol=600519&period=1d&names=macd,kdj&params=%7B%22kdj%22%3A%7B%22n%22%3A9%7D%7D"
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"ts":"2026-08-07T08:00:00","open":1308.66,"high":1315.28,"low":1301.0,"close":1309.22,"volume":24976,"amount":3266919421.0,"macd_dif":29.46,"macd_dea":33.11,"macd_hist":-7.30,"kdj_k":44.22,"kdj_d":59.02,"kdj_j":14.63},...]}
```

# 会话与消息 API（Conversations）

## 1. 创建会话

- **接口名称**：创建会话
- **请求 Method**：POST
- **请求 Path**：/api/v1/conversations
- **接口作用**：创建新会话（默认标题「新会话」），J区历史会话数据源。
- **请求 Body**：有（Body-JSON：title?；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/conversations" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{}'
```

**成功返回示例**

```json
{"code":0,"msg":"创建成功","data":{"id":1,"title":"新会话","created_at":"2026-08-09T05:00:00Z","updated_at":"2026-08-09T05:00:00Z"}}
```

## 2. 会话列表

- **接口名称**：会话列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/conversations
- **接口作用**：当前用户会话列表（按更新时间倒序，分页）。
- **请求 Body**：无（Query：page?=1、size?=20（最大 100）；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/conversations?page=1&size=20" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"items":[{"id":1,"title":"新会话","created_at":"...","updated_at":"..."}],"total":1,"page":1,"size":20,"total_pages":1}}
```

> P1-6a（G09）：列表端点统一分页信封 `{items,total,page,size,total_pages}`；`total_pages` 为空列表时为 0。

## 3. 重命名会话

- **接口名称**：重命名会话
- **请求 Method**：PATCH
- **请求 Path**：/api/v1/conversations/{conversation_id}
- **接口作用**：重命名会话（仅本人）。
- **请求 Body**：有（Body-JSON：title；Path：conversation_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X PATCH "http://127.0.0.1:8000/api/v1/conversations/1" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"title":"贵州茅台研究"}'
```

**成功返回示例**

```json
{"code":0,"msg":"重命名成功","data":{"id":1,"title":"贵州茅台研究","created_at":"...","updated_at":"..."}}
```

## 4. 删除会话

- **接口名称**：删除会话
- **请求 Method**：DELETE
- **请求 Path**：/api/v1/conversations/{conversation_id}
- **接口作用**：删除会话及其全部消息（仅本人）。
- **请求 Body**：无（Path：conversation_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/conversations/1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"删除成功","data":null}
```

## 5. 追加消息

- **接口名称**：追加消息
- **请求 Method**：POST
- **请求 Path**：/api/v1/conversations/{conversation_id}/messages
- **接口作用**：向会话追加消息（user/assistant/system），可绑定标的 symbol_id。
- **请求 Body**：有（Body-JSON：role、content、symbol?=代码或symbol_id、tokens?；Path：conversation_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/conversations/1/messages" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"role":"user","content":"分析贵州茅台","symbol":"600519"}'
```

**成功返回示例**

```json
{"code":0,"msg":"发送成功","data":{"id":1,"conversation_id":1,"role":"user","symbol_id":125,"content":"分析贵州茅台","tokens":null,"created_at":"2026-08-09T05:00:00Z"}}
```

## 6. 拉取消息

- **接口名称**：拉取消息
- **请求 Method**：GET
- **请求 Path**：/api/v1/conversations/{conversation_id}/messages
- **接口作用**：按会话拉取消息（**游标分页**，items 时间升序），前端渲染历史对话。
- **请求 Body**：无（Query：limit?=50（最大 200）、before?=message_id 游标；Path：conversation_id；Header：Authorization: Bearer <token>）

**分页语义（P1-6a / G09）**

- 不传 `before`：返回该会话**最新** `limit` 条（前端默认加载 50 条）。
- 传 `before`：以该 message_id 为游标，返回**更早**的一页（滚动到顶部加载更早记录）。
- `has_more`：是否还有更早的消息；`next_cursor`：本页最旧一条的 id（下一页的 `before`），无更早消息时为 `null`。
- 游标 message_id 不属于该会话或不存在 → `400 / 40005`。

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/conversations/1/messages?limit=50" -H "Authorization: Bearer eyJhbGciOi..."
curl "http://127.0.0.1:8000/api/v1/conversations/1/messages?limit=50&before=100" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"items":[{"id":1,"conversation_id":1,"role":"user","symbol_id":125,"content":"分析贵州茅台","tokens":null,"created_at":"..."}],"has_more":true,"next_cursor":1}}
```

# AI 聊天 API（Chat）

## 1. 流式对话

- **接口名称**：流式对话（SSE）
- **请求 Method**：POST
- **请求 Path**：/api/v1/chat
- **接口作用**：AI 流式对话（SSE 透传前端）。保存消息→组装上下文（系统提示+历史+工具）→ReAct Agent 取数→流式输出；落库 chat_messages + agent_runs/agent_steps。LLM 不可用/失败返回降级文案。
- **请求 Body**：有（Body-JSON：content、conversation_id?、symbol?=代码或symbol_id、agent_id?、run_type?=diagnostic|plan|radar|strategy|custom；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -N -X POST "http://127.0.0.1:8000/api/v1/chat" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"content":"分析贵州茅台趋势","symbol":"600519","run_type":"diagnose"}'
```

**成功返回示例（SSE data 行）**

```
data: {"type":"start"}
data: {"type":"tool_call","tool":"market_snapshot","input":{"symbol":"600519"}}
data: {"type":"delta","seq":1,"content":"..."}
data: {"type":"delta","seq":2,"content":"..."}
data: {"type":"done","message_id":9,"conversation_id":2,"run_id":3}
```

**SSE 事件协议（V0.2 阶段五增强）**

| 事件 | 字段 | 说明 |
|---|---|---|
| `start` | — | 流开始 |
| `delta` | `seq`(递增序号)、`content`、`node`?(深度模式) | 文本增量；seq 用于断点续传 |
| `tool_call` | `tool`、`input` | Agent 调用工具 |
| `tool_result` | `tool`、`preview` | 工具返回预览 |
| `agent_step` | `node`、`status`、`summary`?、`duration_ms`?、`error`? | 深度模式多智能体节点状态：`running`（开始）/`done`（完成，带 summary+耗时）/`failed`（失败，带 error） |
| `usage` | `prompt`、`completion`、`total` | token 用量（阶段八 8.2，估算值，done 前推送） |
| `strategy_ready` | `strategy_id`、`auto_backtest` | 策略生成校验通过并已保存（阶段八 8.6，前端可自动发起回测） |
| `title` | `title`、`conversation_id` | 会话标题自动生成完成（阶段八 8.7，done 后异步推送） |
| `done` | `message_id`、`conversation_id`、`run_id`、`truncated`?、`reason`?、`partial`? | 正常结束；超时截断时带 `truncated:true,reason:"timeout"`；部分节点异常时带 `partial:true` |
| `error` | `code`、`message`、`retryable`、`retry_after`? | 错误帧（见下错误码） |
| `resync` | `conversation_id` | 断点续传缓存已过期，提示前端重新加载完整消息 |

- **心跳**：空闲每 15s 发送注释行 `:keepalive\n\n`（防 Nginx proxy_read_timeout）。
- **三级超时**：首字 30s / 单 delta 间隔 15s / 总流式 120s，超时返回已生成内容 + `done(truncated=true,reason="timeout")`。
- **错误码**：`NETWORK_ERROR`(可重试)、`RATE_LIMITED`(可重试,带retry_after)、`TOKEN_INVALID`(不可重试)、`TOKEN_QUOTA`(不可重试)、`CONTENT_FILTERED`(不可重试)、`PROVIDER_UNAVAILABLE`(可重试)、`TIMEOUT`(可重试)。
- **错误分级降级**：LLM 熔断/未配置 Key → 返回「AI服务暂时不可用，已切换基础分析模式」+ 规则指标文案；token 无效/余额不足 → 「您的DeepSeek API Key无效或余额不足，请检查配置」；工具失败 → 输出标注「行情数据暂时不可用，以下分析基于历史数据」。

**错误帧示例**

```
data: {"type":"error","code":"RATE_LIMITED","message":"请求过于频繁，请30秒后重试","retryable":true,"retry_after":30}
```

## 2. 断点续传（Resume）

- **接口名称**：流式断点续传（SSE）
- **请求 Method**：GET
- **请求 Path**：/api/v1/chat/resume
- **接口作用**：流式中断后前端带 `last_seq` 重连，后端从 Redis 缓存补发 `seq>last_seq` 的 delta（不重复不丢失），补发完成后若流已结束再发 `done`；缓存已过期（TTL 600s）返回 `{"type":"resync"}` 提示重新加载完整消息。
- **请求 Body**：无（Query：`conversation_id`(必填)、`last_seq`(默认0)；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -N "http://127.0.0.1:8000/api/v1/chat/resume?conversation_id=2&last_seq=42" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例（SSE data 行）**

```
data: {"type":"delta","seq":43,"content":"..."}
data: {"type":"done","message_id":9,"conversation_id":2,"run_id":3}
```

# 交易策略 API（Strategies）

## 1. AI 生成策略

- **接口名称**：AI 生成策略（结构化输出）
- **请求 Method**：POST
- **请求 Path**：/api/v1/strategies/generate
- **接口作用**：LangChain with_structured_output 按用户描述生成策略代码+JSON参数（schema 校验 + ast.parse 语法检查）。
- **请求 Body**：有（Body-JSON：description、symbol?=代码或symbol_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/strategies/generate" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"description":"金叉买入死叉卖出的双均线策略"}'
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"strategy_name":"双均线策略","description":"...","code":"def initialize(context):...","params":{"entry":{"fast":5,"slow":20},"stop_loss":{},"take_profit":{},"position":{}},"risk_warning":"震荡市可能反复止损"}}
```

## 2. 策略列表

- **接口名称**：策略列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/strategies
- **接口作用**：当前用户交易策略列表（按创建倒序，分页），M 区策略栏数据源。
- **请求 Body**：无（Query：page?=1、size?=20（最大 100）；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/strategies?page=1&size=20" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"items":[{"id":1,"title":"双均线","description":"...","code":"...","params":{...},"status":"active","created_at":"...","updated_at":"..."}],"total":1,"page":1,"size":20,"total_pages":1}}
```

## 3. 保存策略

- **接口名称**：保存策略
- **请求 Method**：POST
- **请求 Path**：/api/v1/strategies
- **接口作用**：保存交易策略（title/description/code/params/status），与 M 区联动、回测数据源。
- **请求 Body**：有（Body-JSON：title、description?、code?、params?、status?；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/strategies" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"title":"双均线","code":"def on_bar(bar,context): pass"}'
```

**成功返回示例**

```json
{"code":0,"msg":"保存成功","data":{"id":1,"title":"双均线","status":"draft",...}}
```

## 4. 策略详情

- **接口名称**：策略详情
- **请求 Method**：GET
- **请求 Path**：/api/v1/strategies/{strategy_id}
- **接口作用**：单条策略详情（N 区展示代码/参数）。
- **请求 Body**：无（Path：strategy_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/strategies/1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"id":1,"title":"双均线",...}}
```

## 5. 更新策略

- **接口名称**：更新策略
- **请求 Method**：PUT
- **请求 Path**：/api/v1/strategies/{strategy_id}
- **接口作用**：更新策略字段（title/description/code/params/status）。
- **请求 Body**：有（Body-JSON：title?、description?、code?、params?、status?；Path：strategy_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X PUT "http://127.0.0.1:8000/api/v1/strategies/1" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"status":"active"}'
```

**成功返回示例**

```json
{"code":0,"msg":"更新成功","data":{"id":1,"title":"双均线","status":"active",...}}
```

## 6. 删除策略

- **接口名称**：删除策略
- **请求 Method**：DELETE
- **请求 Path**：/api/v1/strategies/{strategy_id}
- **接口作用**：删除策略（仅本人）。
- **请求 Body**：无（Path：strategy_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/strategies/1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"删除成功","data":null}
```

# 策略模板 API（Strategy-Templates）

## 1. 模板列表

- **接口名称**：策略模板列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/strategy-templates
- **接口作用**：内置策略模板列表（id/name/description/params_schema，不含完整 code，按需获取），「基于模板创建」数据源。
- **请求 Body**：无（Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/strategy-templates" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":1,"name":"双均线交叉","description":"短期均线上穿长期均线买入，下穿卖出...","params_schema":{"entry":{"fast":5,"slow":20}}}]}
```

## 2. 模板详情

- **接口名称**：策略模板详情
- **请求 Method**：GET
- **请求 Path**：/api/v1/strategy-templates/{template_id}
- **接口作用**：单个模板详情（含完整 code），前端加载到编辑器供用户修改保存。
- **请求 Body**：无（Path：template_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/strategy-templates/1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"id":1,"name":"双均线交叉","description":"...","params_schema":{...},"code":"def initialize(context):\n    ...\n\ndef on_bar(bar, context):\n    ..."}}
```

# 用户定制 Agent API（Agents）

## 1. 创建定制 Agent

- **接口名称**：创建定制 Agent
- **请求 Method**：POST
- **请求 Path**：/api/v1/agents
- **接口作用**：创建用户定制 Agent（system_prompt/tools/llm_config/memory_config JSONB），支持从预设模板（technical/fundamental/risk_control）创建。
- **请求 Body**：有（Body-JSON：name、agent_type?、system_prompt?、tools?、llm_config?、memory_config?、status?、template?；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/agents" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"name":"我的风控","template":"risk_control"}'
```

**成功返回示例**

```json
{"code":0,"msg":"创建成功","data":{"id":1,"name":"我的风控","agent_type":"custom","system_prompt":"你是风控专员...","tools":{...},"llm_config":{"temperature":0.2},"memory_config":{...},"status":"draft","created_at":"...","updated_at":"..."}}
```

## 2. Agent 列表

- **接口名称**：Agent 列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/agents
- **接口作用**：当前用户定制 Agent 列表（分页）。
- **请求 Body**：无（Query：page?=1、size?=20（最大 100）；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/agents?page=1&size=20" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"items":[{"id":1,"name":"我的风控"}],"total":1,"page":1,"size":20,"total_pages":1}}
```

## 3. Agent 详情

- **接口名称**：Agent 详情
- **请求 Method**：GET
- **请求 Path**：/api/v1/agents/{agent_id}
- **接口作用**：单条定制 Agent 配置详情。
- **请求 Body**：无（Path：agent_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/agents/1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"id":1,"name":"我的风控",...}}
```

## 4. 更新 Agent

- **接口名称**：更新 Agent（启停）
- **请求 Method**：PATCH
- **请求 Path**：/api/v1/agents/{agent_id}
- **接口作用**：更新 Agent 配置或启停（status=active|draft）。
- **请求 Body**：有（Body-JSON：name?、agent_type?、system_prompt?、tools?、llm_config?、memory_config?、status?；Path：agent_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X PATCH "http://127.0.0.1:8000/api/v1/agents/1" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"status":"active"}'
```

**成功返回示例**

```json
{"code":0,"msg":"更新成功","data":{"id":1,"name":"我的风控","status":"active",...}}
```

## 5. 删除 Agent

- **接口名称**：删除 Agent
- **请求 Method**：DELETE
- **请求 Path**：/api/v1/agents/{agent_id}
- **接口作用**：删除定制 Agent（仅本人）。
- **请求 Body**：无（Path：agent_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/agents/1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"删除成功","data":null}
```

# 回测 API（Backtest）

## 1. 发起回测

- **接口名称**：发起回测（异步）
- **请求 Method**：POST
- **请求 Path**：/api/v1/backtest
- **接口作用**：创建回测任务（queued）→ Celery backtest 队列异步执行，返回任务 ID 供前端轮询；回测结束结果写 backtest_results。
- **请求 Body**：有（Body-JSON：strategy_id、symbol=标的代码或symbol_id、period?=15m|1d|1w|1mon、start?、end?、fill_on?=close|open；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/backtest" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"strategy_id":1,"symbol":"600519","period":"1d"}'
```

**成功返回示例**

```json
{"code":0,"msg":"回测已提交","data":{"id":17,"strategy_id":1,"symbol_id":125,"period":"1d","status":"queued","progress":0,"error":null,"created_at":"...","updated_at":"..."}}
```

## 2. 任务状态轮询

- **接口名称**：回测任务状态
- **请求 Method**：GET
- **请求 Path**：/api/v1/backtest/tasks/{task_id}
- **接口作用**：查询回测任务状态（queued/running/success/failed）与进度（0-100），前端轮询。
- **请求 Body**：无（Path：task_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/backtest/tasks/17" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"id":17,"strategy_id":1,"symbol_id":125,"period":"1d","status":"success","progress":100,"error":null,"created_at":"...","updated_at":"..."}}
```

## 3. 回测任务列表

- **接口名称**：回测任务列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/backtest/tasks
- **接口作用**：当前用户回测任务列表（可按 strategy_id 过滤，分页，N 区历史任务）。
- **请求 Body**：无（Query：strategy_id?、page?=1、size?=20（最大 100）；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/backtest/tasks?strategy_id=1&page=1&size=20" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"items":[{"id":17,"strategy_id":1,"symbol_id":125,"status":"success","progress":100}],"total":1,"page":1,"size":20,"total_pages":1}}
```

## 4. 结果查询（按策略）

- **接口名称**：回测结果列表（按策略）
- **请求 Method**：GET
- **请求 Path**：/api/v1/backtest/results
- **接口作用**：按策略查询回测结果列表（N 区与全景K线策略指标数据源：胜率/盈亏比/夏普/年化/最大回撤等）。
- **请求 Body**：无（Query：strategy_id；Header：Authorization: Bearer <token>）
- **G32 字段裁剪**：本端点用 `BacktestResultBriefOut` 序列化，**不返回** `equity_curve` / `trades`（两字段单条约 60KB，列表返回会显著放大响应体）。仓储层同时用 SQLAlchemy `defer()` 让 DB 不取这两列。需要曲线/流水请调「5. 结果详情」。

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/backtest/results?strategy_id=1" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":5,"task_id":17,"strategy_id":1,"symbol_id":125,"win_rate":0.25,"profit_loss_ratio":1.8273,"sharpe":-0.8449,"total_buys":8,"total_sells":8,"annual_return":-0.1472,"max_drawdown":0.1124,"metrics_json":{"total_return":-0.0493,"total_trades":8,"commission_total":7750.04,...},"start_ts":"...","end_ts":"..."}]}
```

## 5. 结果详情

- **接口名称**：回测结果详情
- **请求 Method**：GET
- **请求 Path**：/api/v1/backtest/results/{result_id}
- **接口作用**：单条回测结果详情（含 metrics_json 扩展指标与交易统计；G32 起另含资金曲线与买卖流水）。
- **请求 Body**：无（Path：result_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/backtest/results/5" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"id":5,"task_id":17,"strategy_id":1,"win_rate":0.25,"metrics_json":{...},"equity_curve":[{"ts":"2024-08-12T08:00:00+00:00","equity":1000000.0,"cash":1000000.0,"pos":0,"price":5520.454}],"trades":[{"ts":"2024-08-19T08:00:00+00:00","side":"buy","price":5778.676,"shares":164,"amount":947702.86,"fee":284.31,"reason":"signal","realized_pnl":null}]}}
```

**G32 新增响应字段说明（P1-11 回测结果可视化）**

| 字段 | 类型 | 说明 |
|---|---|---|
| equity_curve | array \| null | **资金曲线**，逐 bar 一点；与 `/api/v1/kline` 的 bar `ts` 一一对应（同一回测周期的每根 K 线） |
| trades | array \| null | **买卖流水**，按时间升序 |

`equity_curve` 元素：

| 字段 | 说明 |
|---|---|
| ts | 该 bar 时间（ISO8601，带 `+00:00` 时区；与 `/kline` 的 naive `ts` 表示同一时刻） |
| equity | 该 bar 收盘时的总权益（现金 + 持仓市值，含期末未平仓浮动市值） |
| cash | 可用现金 |
| pos | 持仓股数 |
| price | 该 bar 收盘价（前端「买入持有基准」用此序列归一化） |

`trades` 元素：

| 字段 | 说明 |
|---|---|
| ts | 成交时间（ISO8601，同上） |
| side | `buy` / `sell` |
| price | 成交价（含滑点；止损/止盈为触发价） |
| shares | 成交股数 |
| amount | 成交金额（price × shares） |
| fee | 该笔费用（买入=佣金；卖出=佣金+印花税） |
| reason | 触发原因：`signal`（策略信号）/ `stop_loss`（止损）/ `take_profit`（止盈） |
| realized_pnl | **已实现净盈亏**（仅 `sell` 有值，`buy` 为 `null`）。与胜率同一口径：复用 `metrics._pair_trades` 的 FIFO 成本 + 买卖费用按股数分摊，前端**不得自行重算** |

> **兼容性**：两字段为 0013 迁移新增，**存量结果行（迁移前生成）为 `null`**，前端按空态降级展示，不报错。
> **体积**：单条结果两字段合计约 60KB（2 年日K ≈ 500 点 + 上百笔流水），故列表端点裁剪（见 4）。

**metrics_json 字段说明（P0-10b/G20 修复后口径）**

| 字段 | 说明 |
|---|---|
| total_return | 总收益率（末值净值/初始资金-1，含期末未平仓浮动盈亏） |
| total_trades | **完整交易回合数**（一次买→卖为一笔；FIFO 仅用于成本分摊） |
| total_buys / total_sells | 累计买入/卖出笔数（流水笔数，非回合数） |
| commission_total | 累计费用（佣金+印花税） |
| bars_used | 回测使用 K 线根数 |
| avg_holding_bars | 平均持仓 bar 数 |
| annual_volatility | 年化波动率 |
| best_trade / worst_trade | 最好/最差单笔盈亏（**净盈亏**，已扣费用） |
| draws | **平手交易数**（毛盈亏为 0，单列，不计入胜率分母、不并入亏损） |
| unrealized_pnl | **期末未平仓浮动盈亏**（按最后一根 bar 收盘价结算，未扣买入佣金） |
| unrealized_count | 期末未平仓标的数（0 或 1） |

> 胜率 `win_rate` 口径：仅统计**已实现**交易回合，分母 = 回合数 - draws；无已实现回合时为 null。
> 盈亏比 `profit_loss_ratio` 按净盈亏均值计算，全胜无亏损时为 null。

# Agent 运行记录与记忆文件 API（Agent-Ops）

## 1. Agent 运行历史

- **接口名称**：Agent 运行历史
- **请求 Method**：GET
- **请求 Path**：/api/v1/agent/runs
- **接口作用**：当前用户 Agent 运行记录列表（按时间倒序，支持按会话筛选 + 分页，前端 AgentRunsDialog 数据源）。
- **请求 Body**：无（Query：conversation_id?、page?=1、size?=20（最大 100）；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/agent/runs?conversation_id=2&page=1&size=20" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"items":[{"id":3,"agent_id":null,"conversation_id":2,"symbol_id":125,"run_type":"diagnostic","status":"success","input":"分析贵州茅台趋势","output":"结论：持有","final_decision":"结论：持有","total_duration":3500,"tokens":null,"error":null,"created_at":"...","updated_at":"..."}],"total":1,"page":1,"size":20,"total_pages":1}}
```

> P1-6a（G09）：本端点原已分页，本轮补齐 `total_pages` 字段，与其余列表端点信封一致。

## 2. Agent 运行节点步骤

- **接口名称**：Agent 运行节点步骤
- **请求 Method**：GET
- **请求 Path**：/api/v1/agent/runs/{run_id}/steps
- **接口作用**：某次运行的完整多智能体节点步骤（node/status/summary/content/duration_ms，按节点执行顺序）。
- **请求 Body**：无（Path：run_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/agent/runs/3/steps" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":1,"run_id":3,"step_name":"technical_analyst","node":"technical_analyst","agent_role":"analyst","status":"done","content":"趋势向上...","summary":"趋势向上，支撑1200","duration_ms":2100,"meta":null,"created_at":"..."}]}
```

## 3. Agent 运行详情

- **接口名称**：Agent 运行详情
- **请求 Method**：GET
- **请求 Path**：/api/v1/agent/runs/{run_id}
- **接口作用**：单条运行记录详情（内嵌 agent_steps 多智能体步骤输出，可观测/复盘）。
- **请求 Body**：无（Path：run_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/agent/runs/3" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"id":3,"run_type":"diagnostic","status":"success","output":"结论：持有","final_decision":"结论：持有","total_duration":3500,"steps":[{"id":1,"run_id":3,"step_name":"technical_analyst","node":"technical_analyst","agent_role":"analyst","status":"done","content":"技术面看多","summary":"技术面看多","duration_ms":2100,"meta":null,"created_at":"..."}],"created_at":"..."}}
```

## 4. 本地记忆文件

- **接口名称**：本地记忆文件列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/memory/files
- **接口作用**：当前用户本地记忆文件列表（M 区「记忆文件」数据源；记忆本体存本地路径，接口返回索引元数据）。
- **请求 Body**：无（Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/memory/files" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"path":"D:/stock-invest-system/stock_backend/data/memory/1/rule.md","content_type":"rule","updated_at":"2026-08-11T05:00:00Z"}]}
```

## 5. 记忆事实列表（V0.2 阶段六 6.4）

- **接口名称**：记忆事实列表（分页）
- **请求 Method**：GET
- **请求 Path**：/api/v1/memory/facts
- **接口作用**：分页返回当前用户记忆列表（内容、重要性、来源类型/对话ID、创建时间），支持按重要性下限筛选。M 区「记忆文件」数据源。
- **请求 Body**：无（Query：`page`(默认1)、`size`(默认20，≤100)、`importance_min`(可选 1-10)；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/memory/facts?page=1&size=20&importance_min=7" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"items":[{"id":12,"content":"止损不超过2%","importance":8,"source_type":"rule","source_id":3,"created_at":"2026-08-11T05:00:00Z"}],"total":1,"page":1,"size":20}}
```

## 6. 删除单条记忆（V0.2 阶段六 6.4）

- **接口名称**：删除单条记忆
- **请求 Method**：DELETE
- **请求 Path**：/api/v1/memory/facts/{fact_id}
- **接口作用**：删除单条记忆（删 memory_chunks 行，向量同列同删），删除后 AI 不再召回；同时写入记忆访问审计。
- **请求 Body**：无（Path：fact_id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/memory/facts/12" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"已删除","data":null}
```

## 7. 清空全部记忆（V0.2 阶段六 6.4）

- **接口名称**：清空全部记忆
- **请求 Method**：DELETE
- **请求 Path**：/api/v1/memory/facts
- **接口作用**：清空当前用户全部记忆（按 user_id 删 memory_chunks 行 + 删加密记忆文件）；同时写入记忆访问审计。
- **请求 Body**：无（Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/memory/facts" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"已清空","data":{"deleted":5}}
```

## 8. 记忆访问审计（G15 · P0-3a）

- **接口名称**：记忆访问审计日志（分页）
- **请求 Method**：GET
- **请求 Path**：/api/v1/memory/audit
- **接口作用**：分页返回当前用户的记忆访问审计日志（读取/写入/删除的时间、动作、关联记忆 ID、来源 IP），按时间倒序。用于隐私合规与用户自查。
- **请求 Body**：无（Query：`page`(默认1)、`size`(默认20，≤100)、`action`(可选：memory_read / memory_write / memory_delete)；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/memory/audit?page=1&size=20&action=memory_read" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"items":[{"id":31,"action":"memory_read","memory_id":null,"ip":"127.0.0.1","created_at":"2026-09-17T05:00:00Z"}],"total":1,"page":1,"size":20}}
```

## 9. 注销账户（G18）

- **接口名称**：注销账户（软删除）
- **请求 Method**：DELETE
- **请求 Path**：/api/v1/users/me
- **接口作用**：注销当前账户。置 `is_deleted/deleted_at` + **立即吊销全部 refresh session**；access token 因 `get_current_user` 的 is_deleted 检查**即刻失效**。**30 天宽限期内**可经 `POST /api/v1/auth/restore-account` 恢复，逾期由 beat 每日 4:45 硬删级联清理全部数据（含记忆目录与导出文件）。
- **请求 Body**：无（Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X DELETE "http://127.0.0.1:8000/api/v1/users/me" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"账户已注销","data":{"message":"账户已注销，30 天内可登录后申请恢复，逾期将永久删除全部数据","grace_days":30}}
```

> 注销后所有受保护端点返回 `{"code":40103,"msg":"账户已注销"}`；登录返回 `{"code":40310,"msg":"账户已注销。如需恢复，请在 30 天宽限期内使用「恢复账户」功能"}`。
> 硬删级联范围：user_watchlist / support_resistance / trading_strategies / conversations / user_agents / agent_runs / memory_chunks / user_memory_files / user_sessions / notifications / export_tasks（DB 层均为 ON DELETE CASCADE），chat_messages / backtest_tasks / backtest_results / agent_steps 经中间表级联；另删除 `data/memory/{user_id}/` 目录与导出 ZIP。

# 通知中心 API（Notifications）

## 1. 通知列表

- **接口名称**：通知列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/notifications
- **接口作用**：当前用户通知列表（**未读优先**，其次时间倒序），返回总数与未读数；铃铛下拉面板数据源。
- **请求 Body**：无（Query：limit=50、offset=0；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/notifications?limit=50" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"items":[{"id":12,"type":"backtest_complete","title":"回测完成：贵州茅台","content":"胜率 50.0%，总收益 +10.00%。点击查看完整结果。","is_read":false,"created_at":"2026-09-17T08:00:00Z","read_at":null}],"total":1,"unread":1}}
```

## 2. 未读数

- **接口名称**：未读通知数
- **请求 Method**：GET
- **请求 Path**：/api/v1/notifications/unread-count
- **接口作用**：未读通知数（铃铛红点/计数）。
- **请求 Body**：无（Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/notifications/unread-count" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"unread":3}}
```

## 3. 单条标记已读

- **接口名称**：标记通知已读
- **请求 Method**：PATCH
- **请求 Path**：/api/v1/notifications/{id}/read
- **接口作用**：单条标记已读（仅本人通知，越权返回 404/40410）。
- **请求 Body**：无（Path：id；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X PATCH "http://127.0.0.1:8000/api/v1/notifications/12/read" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"id":12,"type":"backtest_complete","title":"回测完成：贵州茅台","is_read":true,"read_at":"2026-09-17T08:05:00Z"}}
```

## 4. 全部标记已读

- **接口名称**：全部标记已读
- **请求 Method**：PATCH
- **请求 Path**：/api/v1/notifications/read-all
- **接口作用**：当前用户全部未读通知置已读，返回受影响条数。
- **请求 Body**：无（Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl -X PATCH "http://127.0.0.1:8000/api/v1/notifications/read-all" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"updated":3}}
```

> **WS 推送**：服务端在回测完成/失败、深度分析完成、管理员发布公告时推送
> `{"type":"notification","data":{"id":0,"type":"system","title":"系统公告：xxx","content":"...","is_read":false,"created_at":"..."}}`。
> 前端收到后未读数 +1，打开面板时拉取列表。

# 系统公告 API（Announcements）

## 1. 活跃公告

- **接口名称**：当前活跃公告
- **请求 Method**：GET
- **请求 Path**：/api/v1/announcements/active
- **接口作用**：`is_active=true` 且未过期的公告（按创建倒序），前端顶部 banner 数据源。**公开免鉴权**。
- **请求 Body**：无（Query：limit=10）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/announcements/active"
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":1,"title":"系统维护通知","content":"今晚 22:00 例行维护","type":"maintenance","is_active":true,"created_at":"2026-09-17T08:00:00Z","expires_at":null}]}
```

## 2. 公告历史

- **接口名称**：公告历史列表
- **请求 Method**：GET
- **请求 Path**：/api/v1/announcements
- **接口作用**：全部公告（含历史/已停用），I 区「系统公告」入口查看。
- **请求 Body**：无（Query：limit=50、offset=0；Header：Authorization: Bearer <token>）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/announcements" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"id":1,"title":"系统维护通知","content":"...","type":"maintenance","is_active":false,"created_at":"...","expires_at":null}]}
```

# 管理员 API（Admin）

## 1. 发布系统公告

- **接口名称**：发布系统公告
- **请求 Method**：POST
- **请求 Path**：/api/v1/admin/announcements
- **接口作用**：管理员发布公告（**is_admin 鉴权**）；可选向全部用户分发站内通知 + WS 全局广播。管理员由 `ADMIN_USERNAMES` 环境变量配置，正常注册后自动获得 is_admin。
- **请求 Body**：有（Body-JSON：title、content、type=info|warning|maintenance、expires_at?、notify_users=true；Header：Authorization: Bearer <token>，需 is_admin）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/admin/announcements" -H "Authorization: Bearer eyJhbGciOi..." -H "Content-Type: application/json" -d '{"title":"系统维护通知","content":"今晚 22:00 例行维护","type":"maintenance","notify_users":true}'
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":{"announcement":{"id":1,"title":"系统维护通知","content":"今晚 22:00 例行维护","type":"maintenance","is_active":true,"created_at":"2026-09-17T08:00:00Z","expires_at":null},"notified_users":13}}
```

（非管理员返回 `{"code":40300,"msg":"需要管理员权限"}`；type 非法返回 422）

## 2. Provider 健康检查

- **接口名称**：行情 Provider 健康状态
- **请求 Method**：GET
- **请求 Path**：/api/v1/admin/providers/health
- **接口作用**：返回各行情 Provider（eastmoney/sina/ths）可用状态/熔断中/失败次数/最近成功时间（is_admin 鉴权）。
- **请求 Body**：无（Header：Authorization: Bearer <token>，需 is_admin）

**请求示例（curl）**

```bash
curl "http://127.0.0.1:8000/api/v1/admin/providers/health" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"ok","data":[{"name":"eastmoney","state":"closed","failures":0,"last_success_at":"2026-08-20T10:00:00Z","cooldown_remaining":0},...]}
```

## 2. 全量目录同步（手动触发）

- **接口名称**：触发标的目录同步
- **请求 Method**：POST
- **请求 Path**：/api/v1/admin/catalog/sync
- **接口作用**：手动触发全量A股+ETF目录同步（akshare），异步执行，返回任务 ID（is_admin 鉴权）。
- **请求 Body**：无（Header：Authorization: Bearer <token>，需 is_admin）

**请求示例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/admin/catalog/sync" -H "Authorization: Bearer eyJhbGciOi..."
```

**成功返回示例**

```json
{"code":0,"msg":"目录同步已提交","data":{"task_id":"e2a1...","status":"queued"}}
```

# 实时行情 WebSocket API（WS）

## 1. 实时行情推送

- **接口名称**：实时行情 WebSocket
- **请求 Method**：WS
- **请求 Path**：/api/v1/ws/market
- **接口作用**：实时快照/K线增量推送。**鉴权走 HttpOnly Cookie（G29，token 不再出现在 URL）**；订阅消息 `{"action":"subscribe","symbol_ids":[1,2]}`；服务端每 15s 发 `{"type":"ping"}`，30s 无 pong 断开；断线补拉 `{"action":"sync","since":"ISO时间"}`。
- **请求 Body**：无（无 Query 参数）

**鉴权方式（G29 / P0-5）**

| 客户端 | 方式 | 说明 |
|---|---|---|
| 浏览器 | HttpOnly Cookie | `new WebSocket(url)` 自动携带 `access_token` Cookie，服务端握手时校验（含 Redis 黑名单） |
| 非浏览器（脚本/移动端） | 首条 auth 消息 | 握手后 5s 内发 `{"action":"auth","token":"<JWT>"}`，校验通过即认证 |

- 校验失败：Cookie 存在但无效 → 握手直接拒绝（4001）；无 Cookie 且 5s 内未发 auth → accept 后 4001 关闭。
- 心跳期间复查 jti 黑名单：登出/踢出设备后，已建立的 WS 连接会在下一次心跳（≤15s）被断开（4001）。
- **query 参数 `?token=` 已不再是鉴权途径**（即使 token 有效也拒绝），避免 Nginx/代理日志泄露。

**请求示例（JS 伪代码）**

```js
// 浏览器：Cookie 自动携带，无需传 token
const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/v1/ws/market`);
ws.onopen = () => ws.send(JSON.stringify({action:"subscribe", symbol_ids:[125,70]}));
ws.onmessage = e => console.log(e.data); // {"type":"ping"} / {"type":"snapshot","data":{...}} / {"type":"kline",...}
```

```js
// 非浏览器客户端：首条 auth 消息兜底
const ws = new WebSocket("wss://host/api/v1/ws/market");
ws.onopen = () => ws.send(JSON.stringify({action:"auth", token: jwt}));
```

**成功返回示例（推送消息）**

```json
{"type":"snapshot","data":{"125":{"price":1309.22,"change":4.57,"change_pct":0.35,"updated_at":"2026-08-20T10:00:00Z"}}}
```

# V0.2 现有端点增强说明

- `GET /api/v1/symbols/search`：新增 Query `type`（stock/etf/index 过滤）与 `limit`；返回字段新增 `is_catalog`（TRUE=仅目录未同步K线）、`has_kline`（是否已有K线），前端据此标注"已同步/未同步"。
- `GET /api/v1/snapshot`：返回字段新增 `data_age_seconds`（快照数据龄，当前时间-updated_at），前端据此标注"数据时间"而非"--"；请求带有效登录 token 且 symbol 集合 ⊆ 该用户关注列表时，结果按 `watchlist_snap:{user_id}` 缓存（交易时段 10s / 非交易 300s）。
- `GET /api/v1/watchlist`：返回字段新增 `sync_status`（pending/syncing/done/failed）与 `last_synced_at`，前端展示"同步中/已同步/失败"。
- `GET /api/v1/kline`：默认区间（未传 start/end）走 Redis "最近N根"缓存，连续请求毫秒级返回；显式区间仍直查 PG。
