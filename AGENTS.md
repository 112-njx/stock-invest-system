# 本地联调交付

在本仓库新增或修改功能模块后，先验证改动，再将对应提交推送到远端 `njx-branch`。推送成功后重启本地后端和受改动影响的服务。若开发环境通过 Docker 提供前端静态页面，前端有改动时需重建镜像并重启前端容器。最后确认服务可访问，并告知用户本地测试地址和提交号。

# 前端响应式开发

新增或修改页面时使用现有应用外壳，复用 `stock_frontend/src/responsive.css` 的安全区、弹窗、宽表和触控尺寸约定。手机布局覆盖 767px 及以下，以及较矮的触屏横屏。关键操作须有可点按的入口。宽表、代码块等需要横向滚动的内容只在各自容器内滚动。

提交前在 `stock_frontend` 运行 `npm run build` 和 `npm run test:responsive`。新增路由同时补充 `tests/responsive/layout.spec.ts` 的路由用例。改动软键盘、弹窗或图表手势时，在 iOS Safari 和 Android Chrome 真机复核。
