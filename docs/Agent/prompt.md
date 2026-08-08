#这是prompt,Agent或者ai读到这里直接忽略即可，与项目没有任何关系，仅记录编写的提示词。

首先阅读D:\stock-invest-system\docs\Agent\memory.md中的记忆文件，确保你可以迅速上手项目。其次你看到文件夹Agent_frontend和Agent_backend等，其中的md文件说明了他们的作用，假如
  你未来你将要在其中补充文字。注意不要修改这两个文件夹的md文件中我的说明文字，在此基础上添加即可。你的职责是后端开发工程师，你需要按照D:\stock-invest-system\docs\Agent_backend\r
  oadmap.md中的后端开发规划一步一步按阶段下的细分任务完成开发。前提条件：在观看D:\stock-invest-system\docs\Agent_backend\roadmap.md时如果对开发需求有不清楚的情况，观看D:\stock-i
  nvest-system\docs\project_docs\docs.md项目需求文档等等信息，如果你对具体的开发细节不清楚请及时问我在进行开发。另外后端开发过程中
  代码遵循特别借鉴D:\stock-invest-system\docs\project_docs\docs.md中提到的两个开源项目的原则，尽量避免不对照开源项目盲目开发代码的出现。注意如果新增后端API，需要将
  其描述补充在D:\stock-invest-system\docs\Agent_backend\api-docs.mdapi文档中 格式已经给出,要求你不要更改或删除该文档最上方的文字说明
  直接在文字说明下方补充api格式。如果代码有需要我人工配置的地方或者需要说明日志文件的内容，按照D:\stock-invest-system\docs\Agent_backend\roadmap.md上方的文字要求将说明补充在该文件下方，同样
  不要更改文档最上方的文字说明。在你编程完一个阶段下的一个细分任务后（例如1.1），在D:\stock-invest-system\docs\Agent_backend\Agent_code.md中按文件要求补充编码记录，同样不要更改
  文档最上方的文字说明。
  在你清楚之后，首先完成阶段一的7个任务的开发。

考虑到项目未来的扩展性以及我对你说的生产级架构思路，我认为应该使用langchain框架实现软件“为用户定制Agent”的功能而非原来的RAGflow，相关项目借鉴方案
我已经在D:\stock-invest-system\docs\project_docs\docs.md的10-21行进行更改。同时我对部分说明文档文件结构进行了调整.现在要求你：
（1）D:\stock-invest-system\docs\project_docs\docs.md文件下方需要编写第二个版本的扩展思路，你在阅读项目TradingAgents-CN后，
需要根据这个两个开源项目思考相较于我原来需求和ui的基础上，可以扩展的地方（前端ui不会产生大的改变），将其补充在该文件下方，同样需要遵循简洁说明的原则。
（2）对已经进行编写的 前端规划文档 后端规划文档 D:\stock-invest-system\docs\project_docs\working_docs.md中的数据流设计和
D:\stock-invest-system\docs\project_docs\docs.md中第一版的数据库设计等，寻找相应需要修改的架构说明或数据流设计，开发流程编写需要修改的地方，
对其按照新框架开发的要求进行修改。如果数据库设计需要更改，则同步在sql文件夹中补充相应的sql语句。

首先阅读D:\stock-invest-system\docs\Agent\memory.md中的记忆文件，确保你可以迅速上手项目。其次你看到文件夹Agent_frontend和Agent_backend等，其中的md文件说明了他们的作用，假如
  你未来你将要在其中补充文字。注意不要修改这两个文件夹的md文件中我的说明文字，在此基础上添加即可。你的职责是该项目的前端开发工程师，你需要按照D:\stock-invest-system\docs\Agent_frontend\roadmap.md
  中的前端开发规划一步一步按阶段下的细分任务完成开发。其中D:\stock-invest-system\docs\Agent_frontend\PageDesign.md是前端页面设计。
  前提条件：在观看D:\stock-invest-system\docs\Agent_frontend\roadmap.md时如果对开发需求有不清楚的情况，观看D:\stock-i
  nvest-system\docs\project_docs\docs.md项目需求文档等等信息，如果你对具体的开发细节不清楚请及时问我在进行开发。另外后端开发过程中
  代码遵循特别借鉴D:\stock-invest-system\docs\docs.md中提到的两个开源项目的原则，尽量避免不对照开源项目盲目开发代码的出现。注意如果新增后端API，需要将
  其描述补充在D:\stock-invest-system\docs\Agent_backend\api-docs.mdapi文档中 格式已经给出,要求你不要更改或删除该文档最上方的文字说明
  直接在文字说明下方补充api格式。如果代码有需要我人工配置的地方或者需要说明日志文件的内容，按照D:\stock-invest-system\docs\Agent_backend\roadmap.md上方的文字要求将说明补充在该文件下方，同样
  不要更改文档最上方的文字说明。在你编程完一个阶段下的一个细分任务后（例如1.1），在D:\stock-invest-system\docs\Agent_backend\Agent_code.md中按文件要求补充编码记录，同样不要更改
  文档最上方的文字说明。
  在你清楚之后，首先完成阶段一的7个任务的开发。