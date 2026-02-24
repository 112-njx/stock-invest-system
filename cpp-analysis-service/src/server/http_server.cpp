#include "http_server.h"

#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "cpp-httplib/httplib.h"
#include "json/json.hpp"
#include "repository/mysql_market_data_repository.h"
#include "service/ma_backtest_service.h"

using json = nlohmann::json;

void HttpServer::start(const std::string& host, int port) {
    httplib::Server server;

    server.Get("/ping", [](const httplib::Request&, httplib::Response& res) {
        res.set_content("pong", "text/plain");
    });

    server.Post("/api/analysis/ma", [](const httplib::Request& req, httplib::Response& res) {
        try {
            const auto bodyJson = json::parse(req.body);
            const std::string symbol = bodyJson.value("symbol", "");
            const int period = bodyJson.value("period", 5);

            const double fakeMa = 123.45;
            const json result = {
                {"symbol", symbol},
                {"period", period},
                {"ma", fakeMa}
            };

            res.set_content(result.dump(), "application/json");
        } catch (const std::exception& e) {
            res.status = 400;
            res.set_content(std::string("JSON parse error: ") + e.what(), "text/plain");
        }
    });

    // MA backtest API: reads range data from MySQL and calculates MA cross signals.
    server.Post("/api/backtest/ma", [](const httplib::Request& req, httplib::Response& res) {
        try {
            const auto bodyJson = json::parse(req.body);

            const std::string symbol = bodyJson.value("symbol", "");
            const int period = bodyJson.value("period", 5);
            const std::string startDate = bodyJson.value("startDate", "");
            const std::string endDate = bodyJson.value("endDate", "");

            if (symbol.empty() || startDate.empty() || endDate.empty()) {
                throw std::invalid_argument("symbol/startDate/endDate must not be empty");
            }
            if (period <= 0) {
                throw std::invalid_argument("period must be > 0");
            }

            // Defaults align with Java config; can be overridden by environment variables.
            MySqlConnectionOptions options;
            if (const char* hostEnv = std::getenv("MYSQL_HOST")) options.host = hostEnv;
            if (const char* userEnv = std::getenv("MYSQL_USER")) options.username = userEnv;
            if (const char* passwordEnv = std::getenv("MYSQL_PASSWORD")) options.password = passwordEnv;
            if (const char* databaseEnv = std::getenv("MYSQL_DATABASE")) options.database = databaseEnv;
            if (const char* portEnv = std::getenv("MYSQL_PORT")) {
                options.port = static_cast<unsigned int>(std::stoul(portEnv));
            }

            MySqlMarketDataRepository repository(options);
            const std::vector<DailyBar> bars = repository.queryDailyBars(symbol, startDate, endDate);

            MaBacktestService backtestService;
            const MaBacktestResult backtestResult = backtestService.runBacktest(bars, period);

            json crossUpDates = json::array();
            json crossDownDates = json::array();
            json signalDetails = json::array();
            const std::string crossUpLabel = period == 5 ? "上穿5日线" : ("上穿MA" + std::to_string(period));
            const std::string crossDownLabel = period == 5 ? "下破5日线" : ("下破MA" + std::to_string(period));

            for (const MaSignal& signal : backtestResult.signals) {
                const bool isCrossUp = signal.type == MaSignalType::CrossUp;
                if (isCrossUp) {
                    crossUpDates.push_back(signal.tradeDate);
                } else {
                    crossDownDates.push_back(signal.tradeDate);
                }

                signalDetails.push_back({
                    {"date", signal.tradeDate},
                    {"signalCode", isCrossUp ? "CROSS_UP" : "CROSS_DOWN"},
                    {"signal", isCrossUp ? crossUpLabel : crossDownLabel},
                    {"legacySignal5", isCrossUp ? "上穿5日线" : "下破5日线"},
                    {"closePrice", signal.closePrice},
                    {"ma", signal.maValue}
                });
            }

            const json result = {
                {"symbol", symbol},
                {"period", period},
                {"totalSignals", backtestResult.totalSignals},
                {"winSignals", backtestResult.winSignals},
                {"successRate", backtestResult.successRate},
                {"records", bars.size()},
                {"source", "cpp-backtest-mysql"},
                {"message", std::string("ok; dateRange=") + startDate + "~" + endDate},
                {"crossUpDates", crossUpDates},
                {"crossDownDates", crossDownDates},
                {"signals", signalDetails}
            };

            res.set_content(result.dump(), "application/json");
        } catch (const std::invalid_argument& e) {
            res.status = 400;
            res.set_content(std::string("invalid request: ") + e.what(), "text/plain");
        } catch (const std::exception& e) {
            res.status = 500;
            res.set_content(std::string("backtest error: ") + e.what(), "text/plain");
        }
    });

    server.set_error_handler([](const httplib::Request& req, httplib::Response&) {
        std::cout << "unmatched route: " << req.method << " " << req.path << std::endl;
    });

    std::cout << "HTTP server listening on " << host << ":" << port << std::endl;
    server.listen(host.c_str(), port);
}
