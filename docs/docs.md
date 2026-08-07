该文档中，你将细化 软件需求 项目架构 数据流 数据库设计等 软件文档关键信息
在描述中你需要遵循简洁明了的原则，用最简洁的话说清楚相应的要求。 

软件商业化目标：（1）使用户更加方便的根据自己的策略选择股票的买入和卖出
（2）外接deepseek api，将交易员的主观感受通过Agent转换成相应的量化因子或者可视化回测显示策略成功率。
（3）为用户定制自己的交易大模型或者Agent，记忆文件保存在本地，使得大模型可以根据用户的交易体系交易规则等更好地辅助用户决策。

软件的注意事项：要求达到生产级架构，即可维护，可扩展，可演进，稳定性，可观测，可部署。

借鉴开源项目：
RAG基础系统：infiniflow/ragflow: RAGFlow is a leading open-source Retrieval-Augmented Generation (RAG) engine that fuses cutting-edge RAG with Agent capabilities to create a superior context layer for LLMs
github:https://github.com/infiniflow/ragflow
本地目录：C:\Users\112\Desktop\ragflow-main\ragflow-main
AI Agent：OpenByteInc/QuantDinger: AI quantitative trading platform for crypto, stocks, and forex with backtesting, live trading, market data, and multi-agent research.vibe-trading ,trading-agents,ai-trader,ai-trading
github:https://github.com/OpenByteInc/QuantDinger
本地目录：C:\Users\112\Desktop\QuantDinger-main\QuantDinger-main
Akshark等等。
特别注意：在项目vibe过程中，要特别借鉴这两个项目，尽量避免造轮子的出现。
例如，对于第二个项目的AI Agent，我的项目的J,K,和L区和该开源项目架构相同甚至可以完全借鉴。

软件期望的软件最小生产级原型机：
a.	行情页功能及具体实现页面：(双层页面)
具体实现前端页面：
第一层：（当用户双击鼠标左键点开个股/ETF/行业指数具体K线，可通过按Esc以及左上角退出按钮退出）
┌─────────────────────────────┬───────────────┐
│                 A区域（k线图）   │C区域（基本数据）│
│                                   │                  │
│                                   │                  │
│        B区域（技术指标）          │  D区域(重点关注股票列)│
└──────────────────────────────┴───────────────┘
（1）	“k线图”包含：个股/ETF/行业指数/大盘指数 日k，周k，月k，15mink线显示。
（2）“基本数据”包含当前选中个股/ETF/行业指数/大盘指数的以下信息：
基本行情数据显示（个股/ETF/指数）：
三类资产类型共同显示示例：
字段	说明	示例
标的名称	名称	贵州茅台
标的代码	股票代码	600519
当前价格	最新成交价	1450.50
涨跌额	当前价-昨日收盘	+10.2
涨跌幅	百分比	+0.71%
昨日收盘	昨收	1440.3
今开	开盘价	1445
最高	当日最高	1460
最低	当日最低	1438
成交量	成交数量	500万手
成交额	成交金额	72亿
换手率	活跃程度	0.8%
振幅	日内波动	1.5%
更新时间	行情时间	14:35:22

对于个股，特殊显示：总市值,pe。
对于ETF特殊显示：溢价。
对于指数特殊显示：指数总PE。
（3）B区域（技术指标）：包含个股/ETF/行业指数/大盘指数技术指标：成交量，成交额，MACD，KDJ。
同时，技术指标区域左上角添加设置按键图标，其中可以设置股票压力位或支撑位的显示。要求用户指定后输入股价压力位或者支撑位，在k线图上显示相应的支撑线或者压力线。
（4）D区域：重点关注股票列，显示用户重点关注的股票。
在D区域的下方，有搜索栏，搜索栏可以仅由A股股票代码6位数字搜索股票并添加，同时对于已在数据库中存储数据的股票，搜索栏中要实时显示用户可能搜索的股票。
第二层：（用户没有点击个股，是默认软件开启页面）
┌────────────────────┬──             ─────────────┐
│ E区域(重点关注股票列)               │ F区域(单击k线图)           │
│                        │                              │
│                        │                              │
│ G区域（大盘指数及涨跌幅，机会指标）│H区域（全行业指数/ETF涨跌幅，机会指标）   | I区域(通用设置，开发者信息)                          │
└──────────────────────────────┴───────────────┘
（2）	E区域：重点关注股票列，选择重点关注股票并在列表显示.每一行显示：股票代码，股票名称，最新价，涨跌幅（红色代表涨幅，绿色代表跌幅）。
（3）	F区域：显示在E,G,H区域中鼠标左键单击的股票K线图， ui设计和a区域类似。
（4）	全大盘指数及机会指标。这一部分对于任何用户来说都是固定的大盘指数。大盘指数行从上至下依次包括：上证指数，沪深300，创业板指，科创50，深证成指，上证50，中证1000，中证2000，日经指数，韩国综合，道琼斯指数，纳斯达克指数，标普500，现货黄金。每一行显示：指数名称，最新价，涨跌幅，关联ETF，机会指标。机会指标在目前编程阶段可以先忽略置空值。由于指数行过多可以通过上下滑动鼠标来调整显示指数行。
（5）	全行业指数及机会指标。同样这一部分对于任何用户来说都是固定的行业指数，包括：通信设备，半导体，元件，游戏，教育，半导体设备，光学光电子，软件开发，消费电子，创新药，商业航天，电网设备，文化传媒，军工，机器人概念，电池，工业金属，光伏设备，贵金属，消费，细分化工，油气开采及服务，电力，证券，工程机械，农业种植，房地产，煤炭开采加工，猪肉，白酒，港口航运，公路铁路运输，汽车整车，保险，银行。显示规则和指数显示列相同。
（6）	I区域(通用设置，开发者信息)：在该区域中，靠上一点显示用户登录时的头像及名称。中间左边显示软件设置，右边显示软件显示风格设置，分为暗黑设计和明亮设计，默认为暗黑设计。下方显示开发者信息：“本软件由Xhope(发誓不做夜猫子)全程开发”。

b.	AI策略页功能
高仿：

┌───────────────────────┬─────────────────────────────────────────────────────┐
│ J区(聊天记录侧边栏)    │ K区(AI主操作区)                                            │
│                         │                                                             │
│                         │                                                             │
│                         │                                                             │
├───────────────────────┼─────────────────────────────────────────────────────┤
│  M区（交易策略和记忆文件） │ L区(快捷功能卡片区)                                        │
│                         │                                                             │
│                         │                                                             │


（1）J 区 (左侧会话列表栏)
页面左侧竖直固定侧边栏，顶部显示「策略/聊天」标识，下方空白区域展示用户和ai的对话，用于存放历史聊天会话记录。「策略/聊天」标识作为页面的切换入口，默认是聊天页面，点击策略页跳转到策略页，当前在哪个页面，对应的标识底部呈现浅白色圆角矩形背景，标识当前选中该页面。
（2）K 区 (顶部标题介绍区)
中部居中放置图标、主标题《定制你的交易Agent》及辅助说明小字(询问市场情况，解释日志，定制策略，永久记忆)，作为页面功能总介绍。
（3）L 区 (功能快捷卡片区)
K 区下方上部区域，采用两行三列布局，排布 4 个功能卡片，分别是创建交易策略（下方小字说明：描述一个入场想法，AI 会补齐规则和风控。），诊断符号（下方小字说明：趋势、动量、支撑 / 阻力、流动性和风险。）、交易计划（下方小字说明：把当前行情整理成可执行的交易检查清单。）、机会雷达（下方小字说明：密切关注未来 24 小时内可能出现的机会。），快速跳转对应量化分析功能。其中，创建交易策略在第一行的正中间列，第一行只有”创建交易策略”这一块，第二行三列分别是: 诊断符号、交易计划、机会雷达。
当用户点击相应功能卡片后，直接将对应prompt写入下方对话框中：
1如果点击诊断符号，对话框中显示：
请使用系统行情数据，为（检测当前标的选择行的标的并填入）生成一份可执行的交易分析。

要求：
1. 说明当前价格、K 线周期和数据时间；如果数据不可用，请明确说明，不要编造。
2. 分析趋势、成交量、关键支撑/阻力、资金流和风险。
3. 给出偏多、震荡和偏空三种触发条件。
4. 提供具体行动：观察价位、入场确认、失效止损，以及止盈/减仓逻辑。
5. 结论优先，不要只返回通用框架。

2如果点击交易计划，对话框中显示：
请为（检测当前标的选择行的标的并填入）制定一份可执行的交易计划：方向判断、关键价位、入场触发、止损、止盈、仓位控制，以及什么情况下应该等待不做。

3如果点击机会雷达，对话框中显示：
请基于当前选中的（检测当前标的选择行的标的并填入）分析标的做机会雷达扫描。
要求：
1. 分析必须锁定当前标的和市场。
2. 找出未来24小时可能触发的交易机会。
3. 列出触发条件、确认信号、失效位和主要风险。
4. 区分事实、假设和不确定性。
5. 输出要简洁，可执行。

4特殊的是，如果点击“创建交易策略”，对话框中上方，标的选择行的下方插入显示交易策略模块：
模块详细布局：整体三层垂直布局：顶层横向排布折线图标、标题“你希望策略怎么交易？”、提示标签“可直接发送”；中层单行说明文字“不需要写代码。可以直接发送，也可以点选你最关心的规则。”；底层横向并列按钮“+ 入场规则”“+ 止损止盈”“+ 仓位管理”。同时对话框同步输入prompt：
当用户点击“入场规则”时，加入“使用清晰的入场条件，并避免在行情末端追涨杀跌。”
当用户点击“止损止盈”时，加入“加入稳健的止损和止盈规则。”
当用户点击“仓位管理”时，加入“加入简单的仓位管理，并限制每笔交易的最大风险。”
同时在标的选择行增加一行：“我不选择标的，我思考的是通用的交易体系”。
同时如果创建交易策略并且选择了具体的标的（如果没有选择具体标的则在返回内容添加”保存该交易策略到回测页面”，随后跳转到J,M,N区域的页面，方便用户进行回测。）， ai返回内容后，在对话框ai输出结束的下方。添加保存交易策略和回测显示按钮。其中保存交易策略和m区域的交易策略栏相连动，回测显示按钮则自动跳转到对应相应的个股/ETF/行业指数/大盘指数全景k线图，全景K线图指的是：
┌─────────────────────────────┬───────────────┐
│                 A区域（k线图）   │C区域（基本数据）│
│                                   │                  │
│                                   │                  │
│        B区域（技术指标）          │  D区域(重点关注股票列)│
└──────────────────────────────┴───────────────┘
图为ABCD演示区域
相对于该ABCD展示区域，将D区域更改成策略指标显示页。策略的指标显示包含：策略胜率，盈亏比，夏普比率，累计买入，累计卖出，年化收益率，最大回撤等等。
如果用户保存了该交易策略，在数据库中保存该策略回测的结果，并且转化为相应的agent记忆文件，保存在用户本地电脑。
在用户点击返回对话框中保存交易策略按钮后，将用户描述该交易策略的文字保存在数据库中，并且M区的策略添该交易策略的显示。

L区页面最下方完整区域，从上至下分为三层：
① 标的选择行：文字提示 + 下拉选择框，锁定需要分析的交易标的；文字提示显示：选择要分析的标的。
右方下拉选择框，选择框中显示：股票/指数/ETF名称 + 标的类型（股票/指数/ETF）。
② 大文本输入框：输入用户提问信息，背景附带示例引导文字；示例文字：“例如：帮我分析一小时内上证指数的趋势……”
③ 底部操作栏：左侧风险提示文字，具体为：“风险提示：AI 输出仅用于研究参考，不构成投资建议。决策前请自行核对数据、风险和仓位。”右侧「发送」操作按钮。

（4）M区（交易策略和记忆文件）：
交易策略栏。每一行前端的显示格式像上面对话记录一样，用于保存用户的交易策略，点击具体的交易策略后，原K区和L区变成N区，如图所示：
┌───────────────────────┬─────────────────────────────────────────────────────   ┐
│ J区(聊天记录侧边栏)       │ N区(交易策略显示区)                                     │
│                         │                                                      │
│                         │                                                      │
│                         │                                                      │
├───────────────────────                                                         ┤
│  M区（交易策略和记忆文件） │                                                       │
│                         │                                                      │
│                         │                                                      │


在n区中,所有文字均居中显示。该区域共分为四部分，交易策略描述模块，回测结果模块以及具体的代码实现模块，回测模块。
首先显示用户描述的该交易策略，回测结果模块中显示已经保存的该交易策略的回测结果，具体的代码实现模块中可以选择展示或者修改该交易策略编写的代码，回测模块中可以选择标的（股票/指数/ETF），额外调用回测功能对该策略进行测试，跳转定义页面并保存回测结果。

记忆文件用于打开Agent在本地保存的记忆文件夹。

注：以下是软件未来的优化方向：
在实现核心功能的基础上，考虑加入其他软件的MCP对功能进行扩展。
考虑增加AI对财报等数据的获取，对阶策略加入财报等检测。

项目规划：
1.整体技术架构：Python + PostgreSQL + Vue + Redis + Celery + Nginx。


从D:\stock-invest-system\docs\docs.md中读取软件需求文档，
  （1）首先思考项目的生产级开发方案，从可维护，可扩展，可演进，稳定性，可观测，可部署六个部分进行考虑总结，分这六个部
  分写在docs/working_docs.md文档中,作为生产级架构说明文档。
  （2）完善项目完整的数据流方案，写在docs.md文件下方，作为第二部分。
  （3）完善项目的数据库设计，写在docs.md文件下方，作为第三部分。
  特别注意：在描述中你需要遵循简洁明了的原则，用最简洁的话说清楚相应的要求即可，多说无益。

## 第二部分：完整数据流方案

### 2.1 全局数据流总览

```
行情源(东方财富API) ──同步──▶ PostgreSQL ──缓存──▶ Redis
                                    │
                        行情快照/最新价(轮询/WebSocket)
                                    ▼
                        前端(行情双层页 + AI策略页)
                                    │ 用户请求
                                    ▼
                        FastAPI ──▶ Celery(回测/同步/AI异步)
                                    │
                        DeepSeek API ◀──(上下文:行情+指标+记忆)
                                    │
                        本地记忆文件 ◀──(抽取/写入)──▶ RAG 检索
```

### 2.2 行情数据接入流（同步任务）
```
Celery Beat 定时触发
  → worker 经 DataProvider 调东方财富API
  → 清洗/校验(空值、停牌、异常价格)
  → K线分区表 upsert(幂等，按 symbol+ts 去重)
  → 最新快照写 snapshot_realtime
  → 写 Redis 缓存(TTL)
  → 更新 sync_tasks 状态
```
- 初始化：首次拉取标的全量历史K线。
- 增量：每日收盘后定时拉日K；交易时段轮询实时价。
- 前端：双击打开双层页时拉取 K线+指标+快照；D/E 区实时价走轮询/WebSocket 增量。

### 2.3 技术指标计算流（后端，前端不计算）
```
K线数据 → 指标服务(服务端计算 MACD/KDJ/成交量/成交额)
  → 结果写缓存 + 关联K线图
  → 前端只做渲染
```
- 支撑/压力位：用户在 B 区设置 → `support_resistance` 入库 → K线图叠加横线。

### 2.4 AI 分析流（L 区对话）
```
用户输入(标的选择 + prompt/功能卡片模板)
  → FastAPI 校验+限流
  → 组装上下文: 标的行情快照 + 技术指标 + 记忆检索结果(RAG)
  → 调 DeepSeek(流式输出, 超时/重试/熔断)
  → 前端流式渲染
  → 对话写入 chat_messages
  → 必要时抽取记忆写入本地文件
```

### 2.5 创建交易策略流
```
点击「创建交易策略」→ 插入策略模板模块(入场/止损/止盈/仓位)
  → 用户描述 + AI 补齐规则 → 生成策略代码 + 参数
  → 保存 trading_strategies
  → 返回内容下出现「保存策略」「回测显示」按钮
  → 保存策略 → M 区联动显示
  → 回测显示 → 跳转全景K线图(D区改策略指标: 胜率/盈亏比/夏普/累计买卖/年化/最大回撤)
```

### 2.6 回测流（异步，不阻塞主线程）
```
用户选标的发起回测
  → 创建 backtest_tasks(status=queued)
  → Celery worker 执行: 拉行情 → 回测引擎 → 计算指标
  → backtest_results 入库(事务, 与策略原子保存)
  → 结果转 Agent 记忆文件(本地)
  → 前端轮询任务状态 → N 区展示回测结果
```

### 2.7 记忆流（本地存储）
```
对话/策略结果 → 抽取关键事实(交易体系/规则/偏好)
  → 写本地记忆文件(JSON/文本) → 建立索引
  → 后续请求检索相关记忆 → 注入 AI 上下文
```
- 记忆文件归属用户目录，M 区「记忆文件」按钮打开本地文件夹。

### 2.8 重点关注股票流
```
搜索(6位代码联想, 查 symbols) → 添加 → user_watchlist 入库
  → E/D 区列表展示(代码/名称/最新价/涨跌幅, 红涨绿跌)
  → 实时价定时刷新
```

### 2.9 数据一致性要点
- 行情同步/回测任务幂等，重复触发不产生脏数据。
- 策略 + 回测结果 + 记忆文件写入用事务/补偿保证原子性。
- Redis 缓存与 PostgreSQL 以快照时间戳对齐，缓存失效回源库。

## 第三部分：数据库设计

> 存储：PostgreSQL；行情时序表按月分区；Alembic 迁移管理。

### 3.1 用户域
**users** — 用户账号
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGSERIAL PK | 用户ID |
| username | VARCHAR(64) UNIQUE | 用户名 |
| password_hash | VARCHAR(255) | 密码哈希 |
| email | VARCHAR(128) | 邮箱 |
| nickname | VARCHAR(64) | 昵称 |
| avatar_url | VARCHAR(255) | 头像(登录头像) |
| created_at / updated_at | TIMESTAMP | 时间 |

**user_watchlist** — 重点关注股票
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGSERIAL PK | |
| user_id | BIGINT FK→users | 用户 |
| symbol_id | BIGINT FK→symbols | 标的 |
| created_at | TIMESTAMP | 添加时间 |

**user_memory_files** — 记忆文件索引
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGSERIAL PK | |
| user_id | BIGINT FK→users | 用户 |
| file_path | VARCHAR(512) | 本地记忆文件路径 |
| content_type | VARCHAR(32) | 类型(strategy/rule/preference) |
| updated_at | TIMESTAMP | 更新时间 |

### 3.2 行情域
**symbols** — 标的统一模型（股票/ETF/指数）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGSERIAL PK | |
| code | VARCHAR(16) | 代码(600519) |
| name | VARCHAR(64) | 名称 |
| type | VARCHAR(16) | stock/etf/index |
| market | VARCHAR(16) | 市场(SSE/SZSE/US/HK...) |
| industry | VARCHAR(64) | 行业(指数/行业) |
| etf_linked | VARCHAR(16) | 关联ETF代码 |
| is_fixed_index | BOOLEAN | 是否固定大盘/行业指数 |
| sort_order | INT | 固定列表排序 |
| updated_at | TIMESTAMP | 更新时间 |

**kline_15m / kline_1d / kline_1w / kline_1mon** — K线数据（按月分区）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGSERIAL PK | |
| symbol_id | BIGINT FK→symbols | 标的 |
| ts | TIMESTAMP | K线时间 |
| open/high/low/close | NUMERIC(12,3) | OHLC |
| volume | BIGINT | 成交量 |
| amount | NUMERIC(20,2) | 成交额 |
| UNIQUE(symbol_id, ts) | | 幂等去重 |

**snapshot_realtime** — 实时行情快照（每标的一行，轮询更新）
| 字段 | 类型 | 说明 |
|---|---|---|
| symbol_id | BIGINT PK FK | |
| price | NUMERIC(12,3) | 最新价 |
| change / change_pct | NUMERIC | 涨跌额 / 涨跌幅 |
| open/high/low | NUMERIC(12,3) | 今开/最高/最低 |
| pre_close | NUMERIC(12,3) | 昨收 |
| volume / amount | BIGINT / NUMERIC | 成交量 / 成交额 |
| turnover | NUMERIC(8,4) | 换手率 |
| amplitude | NUMERIC(8,4) | 振幅 |
| updated_at | TIMESTAMP | 更新时间(14:35:22) |

**stock_fundamentals** — 个股特殊数据（总市值/PE）
| 字段 | 类型 | 说明 |
|---|---|---|
| symbol_id | BIGINT PK FK | |
| market_cap | NUMERIC(20,2) | 总市值 |
| pe | NUMERIC(12,3) | 市盈率 |

**etf_premiums** — ETF 特殊数据（溢价）
| 字段 | 类型 | 说明 |
|---|---|---|
| symbol_id | BIGINT PK FK | |
| nav | NUMERIC(12,3) | 净值 |
| premium | NUMERIC(8,4) | 溢价率 |

**index_valuations** — 指数特殊数据（指数总PE）
| 字段 | 类型 | 说明 |
|---|---|---|
| symbol_id | BIGINT PK FK | |
| pe | NUMERIC(12,3) | 指数PE |

**support_resistance** — 支撑/压力位（B 区设置）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGSERIAL PK | |
| user_id | BIGINT FK→users | |
| symbol_id | BIGINT FK→symbols | |
| type | VARCHAR(16) | support/pressure |
| price | NUMERIC(12,3) | 价位 |
| note | VARCHAR(255) | 备注 |
| created_at | TIMESTAMP | |

### 3.3 策略 / AI 域
**conversations** — 会话
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGSERIAL PK | |
| user_id | BIGINT FK→users | |
| title | VARCHAR(128) | 会话标题 |
| created_at / updated_at | TIMESTAMP | |

**chat_messages** — 聊天消息
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGSERIAL PK | |
| conversation_id | BIGINT FK→conversations | |
| role | VARCHAR(16) | user/assistant/system |
| symbol_id | BIGINT FK→symbols NULL | 绑定标的 |
| content | TEXT | 消息内容 |
| tokens | INT | token 数 |
| created_at | TIMESTAMP | |

**trading_strategies** — 交易策略
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGSERIAL PK | |
| user_id | BIGINT FK→users | |
| title | VARCHAR(128) | 策略名 |
| description | TEXT | 用户描述文字 |
| code | TEXT | 策略代码 |
| params | JSONB | 参数(入场/止损/仓位) |
| status | VARCHAR(16) | active/draft |
| created_at / updated_at | TIMESTAMP | |

**backtest_tasks** — 回测任务
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGSERIAL PK | |
| strategy_id | BIGINT FK→trading_strategies | |
| symbol_id | BIGINT FK→symbols | 回测标的 |
| status | VARCHAR(16) | queued/running/success/failed |
| progress | INT | 进度 0-100 |
| error | TEXT | 失败原因 |
| created_at / updated_at | TIMESTAMP | |

**backtest_results** — 回测结果
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGSERIAL PK | |
| task_id | BIGINT FK→backtest_tasks | |
| strategy_id | BIGINT FK→trading_strategies | |
| symbol_id | BIGINT FK→symbols | |
| win_rate | NUMERIC(8,4) | 策略胜率 |
| profit_loss_ratio | NUMERIC(8,4) | 盈亏比 |
| sharpe | NUMERIC(8,4) | 夏普比率 |
| total_buys / total_sells | INT | 累计买入/卖出 |
| annual_return | NUMERIC(8,4) | 年化收益率 |
| max_drawdown | NUMERIC(8,4) | 最大回撤 |
| metrics_json | JSONB | 扩展指标 |
| start_ts / end_ts | TIMESTAMP | 回测区间 |
| created_at | TIMESTAMP | |

### 3.4 运维域
**sync_tasks** — 行情同步任务
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGSERIAL PK | |
| task_type | VARCHAR(32) | kline_init/kline_incremental/realtime |
| symbol_id | BIGINT FK→symbols | |
| status | VARCHAR(16) | running/success/failed |
| last_run_at / next_run_at | TIMESTAMP | 运行时间 |

**task_logs** — 任务日志（全链路）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGSERIAL PK | |
| task_type | VARCHAR(32) | |
| task_id | VARCHAR(64) | Celery 任务ID |
| request_id | VARCHAR(64) | 全链路 request-id |
| status | VARCHAR(16) | |
| message | TEXT | 日志内容 |
| created_at | TIMESTAMP | |

### 3.5 设计要点
- K线/快照表按月分区，按 symbol_id + ts 建索引。
- 固定大盘/行业指数用 `is_fixed_index + sort_order` 驱动 G/H 区固定顺序渲染。
- 策略 + 回测结果 + 记忆文件写入事务保证原子性。
- 用户专属数据(user_watchlist/strategies/记忆)均带 user_id，支持多用户隔离。


