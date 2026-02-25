package com.example.stock_invest_backend.backtest.repository;

import com.example.stock_invest_backend.backtest.dto.BacktestResultView;

import java.util.List;

public interface BacktestResultRepository {

    List<BacktestResultView> findBySymbolAndStrategy(String symbol, String strategyCode, int limit);
}
