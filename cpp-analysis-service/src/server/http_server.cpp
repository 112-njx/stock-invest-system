//httplib  HTTP请求解析路由分发  调用 handler
#include "http_server.h"
#include <iostream>
#include "cpp-httplib/httplib.h"

void HttpServer::start(const std::string& host, int port) {
    httplib::Server server;

    server.Get("/ping", [](const httplib::Request&, httplib::Response& res) {
        res.set_content("pong", "text/plain");
    });

    std::cout << "HTTP server listening on "
              << host << ":" << port << std::endl;

    server.listen(host.c_str(), port);
}