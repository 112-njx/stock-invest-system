//该文件，软件包是MySql接入回测引擎。
//按 symbol + startDate + endDate 读取区间日K
#include "repository/mysql_market_data_repository.h"

#include <cstdlib>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <utility>

#ifndef CPP_BACKTEST_HAS_MYSQL
#define CPP_BACKTEST_HAS_MYSQL 0
#endif

#if CPP_BACKTEST_HAS_MYSQL
#if __has_include(<mysql/mysql.h>)
#include <mysql/mysql.h>
#elif __has_include(<mysql.h>)
#include <mysql.h>
#else
#error "MySQL client header not found."
#endif
#endif

namespace {

bool isValidSymbol(const std::string& symbol) {
    static const std::regex symbolPattern("^[a-z]{2}[0-9]{6}$");
    return std::regex_match(symbol, symbolPattern);
}

bool isValidDate(const std::string& date) {
    static const std::regex datePattern("^[0-9]{4}-[0-9]{2}-[0-9]{2}$");
    return std::regex_match(date, datePattern);
}

}  // namespace

MySqlMarketDataRepository::MySqlMarketDataRepository(MySqlConnectionOptions options)
    : options_(std::move(options)) {}

std::vector<DailyBar> MySqlMarketDataRepository::queryDailyBars(
    const std::string& symbol,
    const std::string& startDate,
    const std::string& endDate) const {
    if (!isValidSymbol(symbol)) {
        throw std::invalid_argument("symbol format invalid, expected example: sh600519");
    }
    if (!isValidDate(startDate) || !isValidDate(endDate)) {
        throw std::invalid_argument("date format invalid, expected yyyy-MM-dd");
    }
    if (startDate > endDate) {
        throw std::invalid_argument("startDate must be <= endDate");
    }

#if !CPP_BACKTEST_HAS_MYSQL
    throw std::runtime_error(
        "mysql client dependency not enabled. Build with MySQL headers and library.");
#else
    MYSQL* connection = mysql_init(nullptr);
    if (connection == nullptr) {
        throw std::runtime_error("mysql_init failed");
    }

    if (mysql_real_connect(
            connection,
            options_.host.c_str(),
            options_.username.c_str(),
            options_.password.c_str(),
            options_.database.c_str(),
            options_.port,
            nullptr,
            0) == nullptr) {
        const std::string error = mysql_error(connection);
        mysql_close(connection);
        throw std::runtime_error("mysql_real_connect failed: " + error);
    }

    std::ostringstream sql;
    sql << "SELECT trade_date, open_price, high_price, low_price, close_price "
           "FROM stock_daily_kline "
           "WHERE symbol='"
        << symbol << "' "
        << "AND trade_date BETWEEN '" << startDate << "' AND '" << endDate << "' "
        << "ORDER BY trade_date ASC";

    if (mysql_query(connection, sql.str().c_str()) != 0) {
        const std::string error = mysql_error(connection);
        mysql_close(connection);
        throw std::runtime_error("mysql_query failed: " + error);
    }

    MYSQL_RES* rawResult = mysql_store_result(connection);
    if (rawResult == nullptr) {
        if (mysql_field_count(connection) != 0) {
            const std::string error = mysql_error(connection);
            mysql_close(connection);
            throw std::runtime_error("mysql_store_result failed: " + error);
        }
        mysql_close(connection);
        return {};
    }

    std::vector<DailyBar> bars;
    MYSQL_ROW row;
    while ((row = mysql_fetch_row(rawResult)) != nullptr) {
        if (row[0] == nullptr || row[4] == nullptr) {
            continue;
        }

        DailyBar bar{};
        bar.tradeDate = row[0];
        bar.openPrice = row[1] == nullptr ? 0.0 : std::stod(row[1]);
        bar.highPrice = row[2] == nullptr ? 0.0 : std::stod(row[2]);
        bar.lowPrice = row[3] == nullptr ? 0.0 : std::stod(row[3]);
        bar.closePrice = std::stod(row[4]);
        bars.push_back(bar);
    }

    mysql_free_result(rawResult);
    mysql_close(connection);
    return bars;
#endif
}
