#include "repository/mysql_market_data_repository.h"

#include <cstring>
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

bool isValidStrategyCode(const std::string& strategyCode) {
    static const std::regex codePattern("^[A-Z0-9_]+$");
    return std::regex_match(strategyCode, codePattern);
}

#if CPP_BACKTEST_HAS_MYSQL
MYSQL* connectOrThrow(const MySqlConnectionOptions& options) {
    MYSQL* connection = mysql_init(nullptr);
    if (connection == nullptr) {
        throw std::runtime_error("mysql_init failed");
    }

    if (mysql_real_connect(
            connection,
            options.host.c_str(),
            options.username.c_str(),
            options.password.c_str(),
            options.database.c_str(),
            options.port,
            nullptr,
            0) == nullptr) {
        const std::string error = mysql_error(connection);
        mysql_close(connection);
        throw std::runtime_error("mysql_real_connect failed: " + error);
    }
    return connection;
}
#endif

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
    MYSQL* connection = connectOrThrow(options_);

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

//实现回测数据的插入
void MySqlMarketDataRepository::insertBacktestResult(const StrategyBacktestRecord& record) const {
    if (!isValidStrategyCode(record.strategyCode)) {
        throw std::invalid_argument("strategyCode format invalid, expected pattern: MA_CROSS_5");
    }
    if (!isValidSymbol(record.symbol)) {
        throw std::invalid_argument("symbol format invalid, expected example: sh600519");
    }
    if (!isValidDate(record.startDate) || !isValidDate(record.endDate)) {
        throw std::invalid_argument("date format invalid, expected yyyy-MM-dd");
    }

#if !CPP_BACKTEST_HAS_MYSQL
    throw std::runtime_error(
        "mysql client dependency not enabled. Build with MySQL headers and library.");
#else
    MYSQL* connection = connectOrThrow(options_);

    const char* sql =
        "INSERT INTO strategy_backtest_result "
        "(strategy_code, symbol, period, start_date, end_date, total_signals, win_signals, success_rate, payload_json) "
        "VALUES (?, ?, ?, STR_TO_DATE(?, '%Y-%m-%d'), STR_TO_DATE(?, '%Y-%m-%d'), ?, ?, ?, CAST(? AS JSON))";

    MYSQL_STMT* stmt = mysql_stmt_init(connection);
    if (stmt == nullptr) {
        const std::string error = mysql_error(connection);
        mysql_close(connection);
        throw std::runtime_error("mysql_stmt_init failed: " + error);
    }

    if (mysql_stmt_prepare(stmt, sql, static_cast<unsigned long>(std::strlen(sql))) != 0) {
        const std::string error = mysql_stmt_error(stmt);
        mysql_stmt_close(stmt);
        mysql_close(connection);
        throw std::runtime_error("mysql_stmt_prepare failed: " + error);
    }

    int period = record.period;
    int totalSignals = record.totalSignals;
    int winSignals = record.winSignals;
    double successRate = record.successRate;

    unsigned long strategyCodeLength = static_cast<unsigned long>(record.strategyCode.size());
    unsigned long symbolLength = static_cast<unsigned long>(record.symbol.size());
    unsigned long startDateLength = static_cast<unsigned long>(record.startDate.size());
    unsigned long endDateLength = static_cast<unsigned long>(record.endDate.size());
    unsigned long payloadLength = static_cast<unsigned long>(record.payloadJson.size());

    MYSQL_BIND bind[9] = {};

    bind[0].buffer_type = MYSQL_TYPE_STRING;
    bind[0].buffer = const_cast<char*>(record.strategyCode.c_str());
    bind[0].buffer_length = strategyCodeLength;
    bind[0].length = &strategyCodeLength;

    bind[1].buffer_type = MYSQL_TYPE_STRING;
    bind[1].buffer = const_cast<char*>(record.symbol.c_str());
    bind[1].buffer_length = symbolLength;
    bind[1].length = &symbolLength;

    bind[2].buffer_type = MYSQL_TYPE_LONG;
    bind[2].buffer = &period;

    bind[3].buffer_type = MYSQL_TYPE_STRING;
    bind[3].buffer = const_cast<char*>(record.startDate.c_str());
    bind[3].buffer_length = startDateLength;
    bind[3].length = &startDateLength;

    bind[4].buffer_type = MYSQL_TYPE_STRING;
    bind[4].buffer = const_cast<char*>(record.endDate.c_str());
    bind[4].buffer_length = endDateLength;
    bind[4].length = &endDateLength;

    bind[5].buffer_type = MYSQL_TYPE_LONG;
    bind[5].buffer = &totalSignals;

    bind[6].buffer_type = MYSQL_TYPE_LONG;
    bind[6].buffer = &winSignals;

    bind[7].buffer_type = MYSQL_TYPE_DOUBLE;
    bind[7].buffer = &successRate;

    bind[8].buffer_type = MYSQL_TYPE_STRING;
    bind[8].buffer = const_cast<char*>(record.payloadJson.c_str());
    bind[8].buffer_length = payloadLength;
    bind[8].length = &payloadLength;

    if (mysql_stmt_bind_param(stmt, bind) != 0) {
        const std::string error = mysql_stmt_error(stmt);
        mysql_stmt_close(stmt);
        mysql_close(connection);
        throw std::runtime_error("mysql_stmt_bind_param failed: " + error);
    }

    if (mysql_stmt_execute(stmt) != 0) {
        const std::string error = mysql_stmt_error(stmt);
        mysql_stmt_close(stmt);
        mysql_close(connection);
        throw std::runtime_error("mysql_stmt_execute failed: " + error);
    }

    mysql_stmt_close(stmt);
    mysql_close(connection);
#endif
}
