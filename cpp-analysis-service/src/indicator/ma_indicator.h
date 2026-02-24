#pragma once

#include <vector>

namespace indicator {

std::vector<double> calculateSimpleMovingAverageSeries(const std::vector<double>& prices, int period);

bool isValidMaPoint(double maValue);

}  // namespace indicator
