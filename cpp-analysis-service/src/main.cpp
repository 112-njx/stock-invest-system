//启动 HTTP 服务  加载配置  注册路由
#include "server/http_server.h"

int main() {
    HttpServer server;
    server.start("127.0.0.1", 8080);
    return 0;
}