//header层 这里相当于java的controller层
#include "json/json.hpp"
using json = nlohmann::json;
#include "cpp-httplib/httplib.h"
#include "service/analysis_service.h"

void register_analysis_routes(httplib::Server& server) {

    server.Post("/api/analysis/ma", [](const httplib::Request& req,
                                       httplib::Response& res) {

        try {
            auto body = json::parse(req.body);

            std::string symbol = body["symbol"];
            int period = body["period"];
            std::vector<double> prices = body["prices"]
                                                 .get<std::vector<double>>();

            double ma = calculate_ma(prices, period);

            json response = {
                    {"symbol", symbol},
                    {"period", period},
                    {"ma", ma}
            };

            res.set_content(response.dump(), "application/json");

        } catch (...) {
            res.status = 400;
            res.set_content("{\"error\":\"bad request\"}", "application/json");
        }
    });
}