该文档中你将记录对整个系统修复的bug，
我在指出bug后,你的格式按照：
时间：
修复bug内容（描述）：
需要我手动配置（如果有的话）：
的格式对该文档进行编写，要求编码内容简练而说明主要内容，
一次编写的编码内容描述在200字以内
另外不准更改或删除我对问题的描述。
在文件最后方写出工作完成后需要人配置的地方或日志文件说明，要求遵循简洁的原则，一条一句话总结即可并且每一条都必须是需要开发者手动配置或观看系统运行的。

## 问题一：docker容器部署报错
（1）在开发阶段，我们不使用D:\stock-invest-system\deploy\docker-compose.yml进行在容器中的上线,如果问题较多,多次更改前端后端文件会导致大量容器文件残留,
所以在运维文件夹下重新编写一个在开发阶段使用的docker-copmpose文件,在文件前写好一键清理容器中残留垃圾的脚本,确保每一次开发启动后容器中没有残留文件.
（2）我刚刚使用过D:\stock-invest-system\deploy\docker-compose.yml文件核心报错：
#16 [worker builder 4/4] RUN pip install --prefix=/install -r requirements.lock
#16 21.00 ERROR: Exception:
#16 21.00 ReadTimeoutError: HTTPSConnectionPool(host='files.pythonhosted.org', port=443): Read timed out.
#16 ERROR: process "/bin/sh -c pip install --prefix=/install -r requirements.lock" did not complete successfully: exit code: 2
在开发阶段使用的docker文件和该docker启动文件中都修复该问题，

时间：2026-08-11
修复bug内容（描述）：Dockerfile 依赖安装改用国内 PyPI 镜像（默认清华 TUNA）并加长超时/重试，修复 pip 连国外源 ReadTimeout；新增开发阶段编排 deploy/docker-compose.dev.yml（后端 bind mount + uvicorn --reload、前端 nginx 托管宿主 dist）+ cleanup_dev.sh / start_dev.sh 一键清理容器残留。生产/开发 compose 共用 Dockerfile，均修复。
需要我手动配置（如果有的话）：1) 根目录 .env.docker 配置 JWT_SECRET_KEY 与 DEEPSEEK_API_KEY；2) 如需换 PyPI 源，构建传 --build-arg PIP_INDEX_URL=<镜像>；3) 开发栈端口冲突可在 .env.docker 设 DEV_API_PORT / DEV_NGINX_PORT。

---

## 工作完成后需手动配置 / 日志文件说明
- 手动配置：.env.docker 需配置 JWT_SECRET_KEY（生产改强随机值）与 DEEPSEEK_API_KEY（容器内用 AI 才需要）。
- 手动配置：PyPI 默认清华镜像，换源用 `docker compose build --build-arg PIP_INDEX_URL=<镜像>`。
- 手动配置：开发栈端口默认 API 8000 / 前端 8081，冲突时在 .env.docker 设 DEV_API_PORT / DEV_NGINX_PORT。
- 日志查看：`docker compose --env-file .env.docker -f deploy/docker-compose.dev.yml logs -f api` 观察后端/热重载日志。
- 日志查看：多次构建残留多时，先跑 `bash deploy/cleanup_dev.sh`（-f 连数据卷清空）再构建。