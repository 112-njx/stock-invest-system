#include "http_server.h"
#include <iostream>
#include "cpp-httplib/httplib.h"
#include "json/json.hpp"

using json = nlohmann::json;

void HttpServer::start(const std::string& host, int port) {
    httplib::Server server;

    // 健康检查
    server.Get("/ping", [](const httplib::Request&, httplib::Response& res) {
        res.set_content("pong", "text/plain");
    });

    //  MA 分析接口
    server.Post("/api/analysis/ma",
                [](const httplib::Request& req, httplib::Response& res) {

                    try {
                        // 解析请求JSON
                        auto bodyJson = json::parse(req.body);

                        std::string symbol = bodyJson["symbol"];
                        int period = bodyJson["period"];

                        std::cout << "收到MA请求: "
                                  << symbol << " period=" << period << std::endl;

                        // 假装计算MA
                        double fakeMa = 123.45;  // 以后替换成真实算法

                        // 构造返回JSON
                        json result = {
                                {"symbol", symbol},
                                {"period", period},
                                {"ma", fakeMa}
                        };

                        res.set_content(result.dump(), "application/json");
                    }
                    catch (const std::exception& e) {
                        res.status = 400;
                        res.set_content(
                                std::string("JSON parse error: ") + e.what(),
                                "text/plain"
                        );
                    }
                });


    // MA 回测接口（最小链路版）
    server.Post("/api/backtest/ma",
                [](const httplib::Request& req, httplib::Response& res) {
                    try {
                        auto bodyJson = json::parse(req.body);

                        std::string symbol = bodyJson.value("symbol", "");
                        int period = bodyJson.value("period", 5);
                        std::string startDate = bodyJson.value("startDate", "");
                        std::string endDate = bodyJson.value("endDate", "");

                        // TODO: 下一步替换为 C++ 直接从 MySQL 拉取 [startDate, endDate] 的日K，计算 MA 策略胜率。
                        int totalSignals = 12;
                        int winSignals = 7;
                        double successRate = totalSignals == 0 ? 0.0 : static_cast<double>(winSignals) / totalSignals;

                        json result = {
                                {"symbol", symbol},
                                {"period", period},
                                {"totalSignals", totalSignals},
                                {"winSignals", winSignals},
                                {"successRate", successRate},
                                {"source", "cpp-backtest-mock"},
                                {"message", std::string("mock result; dateRange=") + startDate + "~" + endDate}
                        };

                        res.set_content(result.dump(), "application/json");
                    }
                    catch (const std::exception& e) {
                        res.status = 400;
                        res.set_content(
                                std::string("JSON parse error: ") + e.what(),
                                "text/plain"
                        );
                    }
                });

    // 未匹配路由打印
    server.set_error_handler([](const httplib::Request& req,
                                httplib::Response& res) {
        std::cout << "未匹配路径: "
                  << req.method << " "
                  << req.path << std::endl;
    });

    std::cout << "HTTP server listening on "
              << host << ":" << port << std::endl;

    server.listen(host.c_str(), port);
}