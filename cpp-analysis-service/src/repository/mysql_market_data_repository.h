#pragma once

#include <string>
#include <vector>

#include "model/market_data.h"

struct MySqlConnectionOptions {
    std::string host = "127.0.0.1";
    unsigned int port = 3306;
    std::string username = "root";
    std::string password = "123456";
    std::string database = "invest_stock_system";
};

class MySqlMarketDataRepository {
public:
    explicit MySqlMarketDataRepository(MySqlConnectionOptions options);

    std::vector<DailyBar> queryDailyBars(
        const std::string& symbol,
        const std::string& startDate,
        const std::string& endDate) const;

private:
    MySqlConnectionOptions options_;
};
