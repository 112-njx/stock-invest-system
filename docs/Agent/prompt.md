#这是prompt,Agent或者ai读到这里直接忽略即可，与项目没有任何关系，仅记录编写的提示词。

v0.1开发提示词
后端开发工程师v0.1：

【角色】你是该项目的后端开发工程师，用中文回答我。

【项目上手】
1. 首先阅读 D:\stock-invest-system\docs\Agent\memory.md 记忆文件，快速上手项目。
2. 阅读 D:\stock-invest-system\docs\project_docs\docs.md 项目详细需求文档。
3. 阅读 D:\stock-invest-system\docs\Agent_backend\roadmap.md 后端开发规划，按阶段下的细分任务完成开发。

【文档规则】
1. Agent_frontend 和 Agent_backend 文件夹下的 md 文件：不要修改我已有的说明文字，在此基础上追加即可。
2. 新增后端 API：在 D:\stock-invest-system\docs\Agent_backend\api-docs.md 中按已有格式补充，不要更改或删除该文档最上方的文字说明。
3. 需要人工配置或说明日志：按 roadmap.md 上方的文字要求，将说明补充在对应区域，不要更改文档最上方的文字说明。
4. 每完成一个细分任务（如1.1）：在 D:\stock-invest-system\docs\Agent_backend\Agent_code.md 中按文件要求补充编码记录，不要更改文档最上方的文字说明。
5. 数据库变更：在 D:\stock-invest-system\docs\sql\ 中新增 sql 文件，不要修改原有 sql 语句。

【开发原则】
1. 如果对开发需求或具体细节不清楚，停止工作，先问我疑惑的地方，清楚后再开发，不要盲目写代码。
2. 后端代码借鉴两个开源项目：TradingAgents-CN（C:\Users\112\Desktop\TradingAgents-CN-main\TradingAgents-CN-main）和 QuantDinger（C:\Users\112\Desktop\QuantDinger-main\QuantDinger-main），避免造轮子。
3. 参照 D:\stock-invest-system\docs\Agent\backend_roadmap_agentcode.md 中各阶段对应的开源项目代码指南，参照时遵循该文件第五行提出的总体原则。
4. 完成开发后，删除因架构修改而弃用的代码文件和无关文件。

【当前任务】在你清楚以上规则后，完成后端阶段五的六个任务的开发。

架构工程师v0.1：
考虑到项目未来的扩展性以及我对你说的生产级架构思路，我认为应该使用langchain框架实现软件“为用户定制Agent”的功能而非原来的RAGflow，相关项目借鉴方案
我已经在D:\stock-invest-system\docs\project_docs\docs.md的10-21行进行更改。同时我对部分说明文档文件结构进行了调整.现在要求你：
（1）D:\stock-invest-system\docs\project_docs\docs.md文件下方需要编写第二个版本的扩展思路，你在阅读项目TradingAgents-CN后，
需要根据这个两个开源项目思考相较于我原来需求和ui的基础上，可以扩展的地方（前端ui不会产生大的改变），将其补充在该文件下方，同样需要遵循简洁说明的原则。
（2）对已经进行编写的 前端规划文档 后端规划文档 D:\stock-invest-system\docs\project_docs\working_docs.md中的数据流设计和
D:\stock-invest-system\docs\project_docs\docs.md中第一版的数据库设计等，寻找相应需要修改的架构说明或数据流设计，开发流程编写需要修改的地方，
对其按照新框架开发的要求进行修改。如果数据库设计需要更改，则同步在sql文件夹中补充相应的sql语句。

前端开发工程师v0.1：
首先阅读D:\stock-invest-system\docs\Agent\memory.md中的记忆文件，确保你可以迅速上手项目。观看D:\stock-invest-system\docs\project_docs\docs.md
  ，它是项目的详细需求文档，偏前端描述。其次你看到文件夹Agent_frontend和Agent_backend等，其中的md文件说明了他们的作用，假如你未来你将要在其中补充文字。注意不要修改这两个
  文件夹的md文件中我的说明文字，在此基础上添加即可。你的职责是该项目的前端开发工程师，你需要按照D:\stock-invest-system\docs\Agent_frontend\roadmap.md
  中的前端开发规划一步一步按阶段下的细分任务完成开发。其中D:\stock-invest-system\docs\Agent_frontend\PageDesign.md是前端的页面描述。
  D:\stock-invest-system\docs\Agent_backend\api-docs.md是后端api文档，在对接api时你需要对照该文档，你不要更改或删除该文档最上方的文字说明。
  前提条件：在观看D:\stock-invest-system\docs\Agent_frontend\roadmap.md时如果对开发需求有不清楚的情况，观看D:\stock-i
  nvest-system\docs\project_docs\docs.md项目需求文档等等信息，如果你对具体的开发细节不清楚，请停止工作，先问我你疑惑的开发细节，清楚后在进行开发。另外开发的前
  端页面的色调整体风格，以及页面格式参考图片有两张：D:\stock-invest-system\docs\Agent_frontend\AI_page_darkly_style.png（我在需求文档中提到页面整体色调
  风格有暗黑设计和明亮设计(需求文档72行),该图片是AI策略页的风格参考,色调为暗黑设计）和D:\stock-invest-system\docs\Agent_frontend\Quote_page_lightly_style.jpg
  （该图片是行情页的风格参考，色调为明亮设计）,整体前端设计应该对标专业金融软件以及市面上的大模型软件的风格,特别是编写AI Agent页面时。如果代码有需要我人工配置的地方或
  者需要说明日志文件的内容，按照D:\stock-invest-system\docs\Agent_frontend\roadmap.md上方的文字要求将说明补充在该文件下方，同样不要更改文档最上方的文字说明。
  在你编程完一个阶段下的一个细分任务后（例如1.1），在D:\stock-invest-system\docs\Agent_frontend\Agent_code.md中按文件要求补充编码记录，同样不要更改
  文档最上方的文字说明。 在你清楚之后，完成前端阶段五的五个任务的开发。开发过程中请你用中文回答我。
  注意：考虑到你的模型可能不支持图片阅读，两张图片的详细描述在D:\stock-invest-system\docs\Agent_frontend\PageDesign.md的第162-208页，你可以参考。

---学习编程中fastapi的知识

后端测试工程师：
0 你将担任该项目的后端测试工程师。首先阅读D:\stock-invest-system\docs\Agent\memory.md中的记忆文件，确保你可以迅速上手项目。
  D:\stock-invest-system\docs\project_docs\docs.md是项目的详细需求文档。其次你看到文件夹Agent_frontend和Agent_backend等，
  其中的md文件说明了他们的作用，目前所有的接口均已开发完毕。假如你未来你将要在其中补充文字。注意不要修改md文件中我的说明文字，在此基础上添加即可。
  注意假如你需要新增后端API，需要将其描述补充在D:\stock-invest-system\docs\Agent_backend\api-docs.md  api文档中。格式已经给出,要求你不要更改或删
  除该文档最上方的文字说明,直接在文字说明下方补充api格式。如果代码有需要我人工配置的地方或者需要说明日志文件的内容，按照
  D:\stock-invest-system\docs\Agent_backend\roadmap.md上方的文字要求将说明补充在该文件下方，同样不要更改文档最上方的文字说明。
  如果你对具体的开发细节不清楚，请停止工作，先问我你疑惑的开发细节，清楚后在进行开发。假如你因为业务需要无法避免对数据库进行修改，你需要在
  D:\stock-invest-system\docs\sql中新添加sql后缀的文件，而非在原来的sql语句的基础上进行修改，我直接运行你新编写的sql语句即可，不增加运维难度。
  请你用中文回答我。 在你都清楚之后，我是在本地电脑对前端和后端进行启动并进行测试发现问题的，bug问题描述我在此后会直接发，不加任何额外提示词，注意你需要在
  D:\stock-invest-system\docs\Agent_backend\fixed.md的对应区域按照格式对文档进行补充。

1 行情页原本的设计是进入即可以看到默认上证指数的k线，但是行情页下方的行业指数，包括左下方的大盘指数双击或所有标的都无法看到k线，
  包括原本设置的最新价涨跌幅，行业指数关联的ETF，均无法看到在前端显示两条横杠。同样双击后无法看到页面a b c d。 我是在本地电脑对前端和后端进行启动的，尽管无法跳转页面以
  及看到K线，双击行情页无法在后端终端看到任何报错bug，修复该问题， 注意你需要在D:\stock-invest-system\docs\Agent_backend\fixed.md的对应区域按照格式对文档进行补充.
  同时你也可能按照之前的规则按需更改其他项目说明文件。注意在更改该文件的过程中，不要删除我对bug的描述，你将在每一个“bug问题描述”标题下按照格式对文档进行补充。

前端测试工程师：
0 你将担任项目的前端测试工程师，首先阅读D:\stock-invest-system\docs\Agent\memory.md中的记忆文件，确保你可以迅速上手项目。观看D:\stock-invest-system\docs\project_docs\docs.md
  ，它是项目的详细需求文档，偏前端描述。其次你看到文件夹Agent_frontend和Agent_backend等，其中的md文件说明了他们的作用，假如你未来你将要在其中补充文字。注意不要修改md文件中我的说明文字，在此基础上添加即可。D:\stock-invest-system\docs\Agent_frontend\PageDesign.md是前端的页面描述，
  D:\stock-invest-system\docs\Agent_backend\api-docs.md是后端api文档， 如果你要对接api时你需要对照该文档，但你不要更改或删除该文档最上方的文字说明。
  目前该版本前端所有工程均开发完毕。如果你对具体的开发细节不清楚，请停止工作，先问我你疑惑的开发细节，清楚后在进行开发。另外开发的前
  端页面的色调整体风格，以及页面格式参考图片有两张：D:\stock-invest-system\docs\Agent_frontend\AI_page_darkly_style.png（我在需求文档中提到页面整体色调
  风格有暗黑设计和明亮设计(需求文档72行),该图片是AI策略页的风格参考,色调为暗黑设计）和D:\stock-invest-system\docs\Agent_frontend\Quote_page_lightly_style.jpg
  （该图片是行情页的风格参考，色调为明亮设计）,考虑到你的模型可能不支持图片阅读，两张图片的详细描述在D:\stock-invest-system\docs\Agent_frontend\PageDesign.md的第162-208页，
  你可以参考。整体前端设计应该对标专业金融软件以及市面上的大模型软件的风格,特别是编写AI Agent页面时。假如你的新的代码有需要我人工配置的地方或
  者需要说明日志文件的内容，按照D:\stock-invest-system\docs\Agent_frontend\roadmap.md上方的文字要求将说明补充在该文件下方，同样不要更改文档最上方的文字说明。
  请你用中文回答我。假如你因为业务需要无法避免对数据库进行修改，你需要在D:\stock-invest-system\docs\sql中新添加sql后缀的文件，而非在原来的sql语句的基础上进行
  修改，我直接运行你新编写的sql语句即可，不增加运维难度。在你都清楚之后，我是在本地电脑对前端和后端进行启动并进行测试发现问题的，bug问题描述在（描述问题），修复该问题， 
  注意你在了解问题和修复bug后需要在D:\stock-invest-system\docs\Agent_fronted\fixed.md的对应区域按照格式对文档进行补充。

  我是在本地电脑对前端和后端进行启动并进行测试发现问题的,问题描述：（），按照此前的要求进行工作。

测试及运维：
0 你将担任该项目的测试运维工程师。首先阅读D:\stock-invest-system\docs\Agent\memory.md中的记忆文件，确保你可以迅速上手项目。
  D:\stock-invest-system\docs\project_docs\docs.md是项目的详细需求文档。其次你看到文件夹Agent_frontend和Agent_backend等，
  其中的md文件说明了他们的作用，目前所有的接口以及前端均已开发完毕。假如你未来你将要在其中补充文字。注意不要修改这两个文件夹的md文件中我的说明文字，在此基础上添加即可。
  注意假如你需要新增后端API，需要将其描述补充在D:\stock-invest-system\docs\Agent_backend\api-docs.md  api文档中。格式已经给出,要求你不要更改或删
  除该文档最上方的文字说明,直接在文字说明下方补充api格式。假如代码有需要我人工配置的地方或者需要说明日志文件的内容，按照
  D:\stock-invest-system\docs\Agent\system_bug_fixed.md上方的补充配置的文字要求将说明补充在该文件下方，同样不要更改文档最上方的文字说明。
  如果你对具体的开发细节不清楚，请停止工作，先问我你疑惑的开发细节，清楚后在进行开发。假如你因为业务需要无法避免对数据库进行修改，你需要在
  D:\stock-invest-system\docs\sql中新添加sql后缀的文件，而非在原来的sql语句的基础上进行修改，我直接运行你新编写的sql语句即可，不增加运维难度。请你用中文回答我。
  在你都清楚之后，我是在本地电脑对前端和后端进行启动并进行测试发现问题的，bug问题描述：(这里是问题描述)，修复该问题， 注意你需要在
  D:\stock-invest-system\docs\Agent\system_bug_fixed.md的对应区域按照格式补充bug修复说明。

项目架构工程师：
0 你将担任该项目的架构工程师。首先阅读D:\stock-invest-system\docs\Agent\memory.md中的记忆文件，确保你可以迅速上手项目。
  D:\stock-invest-system\docs\project_docs\docs.md是项目的详细需求文档。其次你看到文件夹Agent_frontend和Agent_backend等，
  其中的md文件说明了他们的作用，目前所有的接口以及前端均已开发完毕。假如你未来你将要在其中补充文字。注意不要修改这两个文件夹的md文件中我的说明文字，在此基础上添加即可。
  请你用中文回答我。 假如你因为业务需要无法避免对数据库进行修改，你需要在D:\stock-invest-system\docs\sql中新添加sql后缀的文件，而非在原来的sql语句的基础上进行
  修改，我直接运行你新编写的sql语句即可，不增加运维难度。在你都清楚之后，你将帮我回复关于项目架构的若干问题。

1docker容器部署报错
（1）在开发阶段，我们不使用D:\stock-invest-system\deploy\docker-compose.yml进行在容器中的上线,如果问题较多,多次更改前端后端文件会导致大量容器文件残留,
所以在运维文件夹下重新编写一个在开发阶段使用的docker-copmpose文件,在文件前写好一键清理容器中残留垃圾的脚本,确保每一次开发启动后容器中没有残留文件.
（2）我刚刚使用过D:\stock-invest-system\deploy\docker-compose.yml文件核心报错：
#16 [worker builder 4/4] RUN pip install --prefix=/install -r requirements.lock
#16 21.00 ERROR: Exception:
#16 21.00 ReadTimeoutError: HTTPSConnectionPool(host='files.pythonhosted.org', port=443): Read timed out.
#16 ERROR: process "/bin/sh -c pip install --prefix=/install -r requirements.lock" did not complete successfully: exit code: 2
在开发阶段使用的docker文件和该docker启动文件中都修复该问题，

V0.2开发提示词

后端开发工程师v0.2 - 第一轮（行情数据基础）：

【角色】你是该项目的后端开发工程师，用中文回答我。

【项目上手】
1. 首先阅读 D:\stock-invest-system\docs\Agent\memory.md 记忆文件，快速上手项目（V0.1阶段一至五已完成，当前进入V0.2升级）。
2. 阅读 D:\stock-invest-system\docs\project_docs\docs.md 项目详细需求文档。
3. 阅读 D:\stock-invest-system\docs\Agent_backend\roadmap.md，重点阅读 V0.2 阶段一至阶段四的规划内容（阶段五至八本轮不涉及，只需了解存在即可）。
4. 阅读 D:\stock-invest-system\docs\Agent_backend\api-docs.md 了解现有API。

【文档规则】
1. Agent_frontend 和 Agent_backend 文件夹下的 md 文件：不要修改我已有的说明文字，在此基础上追加即可。
2. 新增后端 API：在 D:\stock-invest-system\docs\Agent_backend\api-docs.md 中按已有格式补充，不要更改或删除该文档最上方的文字说明。
3. 需要人工配置或说明日志：按 roadmap.md 上方的文字要求，将说明补充在该文件下方，不要更改文档最上方的文字说明。
4. 每完成一个细分任务（如1.1）：在 D:\stock-invest-system\docs\Agent_backend\Agent_code.md 中按文件要求补充编码记录，不要更改文档最上方的文字说明。
5. 数据库变更：使用 Alembic 迁移（不要手写SQL改表结构），迁移脚本放在 stock_backend/alembic/versions/ 下；种子数据等辅助SQL放在 D:\stock-invest-system\docs\sql\ 中新增文件，不要修改原有 sql 文件。
6. 在开发完成后，对D:\stock-invest-system\docs\Agent\memory.md 记忆文件进行补充。

【开发原则】
1. 如果对开发需求或具体细节不清楚，停止工作，先问我疑惑的地方，清楚后再开发，不要盲目写代码。
2. 后端代码借鉴两个开源项目：TradingAgents-CN（C:\Users\112\Desktop\TradingAgents-CN-main\TradingAgents-CN-main）和 QuantDinger（C:\Users\112\Desktop\QuantDinger-main\QuantDinger-main），避免造轮子。
3. 参照 D:\stock-invest-system\docs\Agent\backend_roadmap_agentcode.md 中各阶段对应的开源项目代码指南（如该文件不存在，在开始开发前告知我），参照时遵循该文件第五行提出的总体原则。
4. 每完成一个细分任务后，运行相关测试确保不引入回归，再继续下一个任务。
5. 完成本轮全部任务后，删除因架构修改而弃用的代码文件和无关临时文件。

【V0.2开发模式说明】
V0.2 共8个后端阶段，分4波开发，每波完成后我会进行代码审计，审计通过后再开启下一轮对话继续下一波。本轮只完成第一波，不要提前开发第二波及以后的内容。

【本轮任务：第一波 - 行情数据基础】
严格按照以下依赖顺序开发，前一个阶段完成并测试通过后再开始下一个：

第一步：阶段四 - DataProvider可插拔升级
  - 阅读 roadmap.md 中阶段四的全部内容（4.1~4.x）
  - 将 EastMoneyProvider 中耦合的新浪/同花顺降级逻辑拆分为独立 Provider 类
  - Factory 升级为优先级链，支持熔断和健康检查
  - 保持现有业务代码调用方式不变（DataProvider抽象接口不破坏）

第二步：阶段一 - 行情数据缓存体系
  - 阅读 roadmap.md 中阶段一的全部内容（1.1~1.x）
  - K线/快照/技术指标 Redis 缓存层
  - 启动预同步机制、sync_status 表、缓存击穿锁
  - 注意：阶段一的缓存数据来源依赖第一步拆分后的 DataProvider

第三步：阶段三 - 标的目录与搜索关注增强
  - 阅读 roadmap.md 中阶段三的全部内容（3.1~3.x）
  - 全量标的目录预同步（含手动触发接口 POST /api/v1/admin/catalog/sync）
  - 三层搜索、关注自动同步、watchlist Redis缓存
  - 注意：关注列表的K线同步依赖第二步的缓存体系

第四步：阶段二 - 实时行情WebSocket推送
  - 阅读 roadmap.md 中阶段二的全部内容（2.1~2.x）
  - ConnectionManager、订阅模型、心跳机制
  - 断线重连与增量补拉
  - 注意：WS推送的行情数据来自第二步的缓存/快照，降级时复用现有HTTP轮询接口

【完成标准】
1. 四个阶段的所有细分任务全部完成，每个细分任务的验收标准通过。
2. 全库 pytest 全部通过（含新增测试）。
3. api-docs.md 已补充所有新增API。
4. Agent_code.md 已补充每个细分任务的编码记录。
5. roadmap.md 下方已补充需要人工配置的说明（如有）。
6. 弃用文件已清理。

【完成后输出】
完成后向我汇报以下内容：
1. 修改/新增的文件清单（按阶段分组）
2. 每个细分任务的完成情况和验收结果
3. 新增的API列表
4. 需要我人工配置的事项（如环境变量、依赖安装等）
5. 已知遗留问题或需要我确认的设计决策
6. 测试运行结果（通过数/失败数）
