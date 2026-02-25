#pragma once

#include <string>
#include <vector>

struct DailyBar {
    std::string tradeDate;
    double openPrice;
    double highPrice;
    double lowPrice;
    double closePrice;
};

enum class MaSignalType {
    CrossUp,
    CrossDown
};

struct MaSignal {
    std::string tradeDate;
    MaSignalType type;
    double closePrice;
    double maValue;
};

struct MaBacktestResult {
    int totalSignals = 0;
    int winSignals = 0;
    double successRate = 0.0;
    std::vector<MaSignal> signals;
};

//这是回测记录模型
struct StrategyBacktestRecord {
    std::string strategyCode;
    std::string symbol;
    int period = 0;
    std::string startDate;
    std::string endDate;
    int totalSignals = 0;
    int winSignals = 0;
    double successRate = 0.0;
    std::string payloadJson;
};
