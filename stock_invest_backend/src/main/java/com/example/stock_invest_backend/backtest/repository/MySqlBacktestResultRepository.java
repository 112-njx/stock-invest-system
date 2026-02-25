package com.example.stock_invest_backend.backtest.repository;

import com.example.stock_invest_backend.backtest.dto.BacktestResultView;
import com.example.stock_invest_backend.backtest.dto.BacktestSignalDto;
import com.example.stock_invest_backend.market.history.config.MySqlWriteProperties;
import org.springframework.stereotype.Repository;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.List;

@Repository
public class MySqlBacktestResultRepository implements BacktestResultRepository {

    private static final String QUERY_SQL = """
            SELECT id, strategy_code, symbol, period, start_date, end_date, total_signals, win_signals,
                   success_rate, payload_json, created_at
            FROM strategy_backtest_result
            WHERE symbol = ? AND strategy_code = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """;

    private final MySqlWriteProperties properties;
    private final ObjectMapper objectMapper;

    public MySqlBacktestResultRepository(MySqlWriteProperties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    @Override
    public List<BacktestResultView> findBySymbolAndStrategy(String symbol, String strategyCode, int limit) {
        if (!properties.isEnabled() || limit <= 0) {
            return List.of();
        }

        final int safeLimit = Math.min(limit, 200);
        try (Connection connection = DriverManager.getConnection(
                properties.getUrl(), properties.getUsername(), properties.getPassword());
             PreparedStatement ps = connection.prepareStatement(QUERY_SQL)) {
            ps.setString(1, symbol);
            ps.setString(2, strategyCode);
            ps.setInt(3, safeLimit);

            try (ResultSet rs = ps.executeQuery()) {
                List<BacktestResultView> list = new ArrayList<>();
                while (rs.next()) {
                    BacktestResultView item = new BacktestResultView();
                    item.setId(rs.getLong("id"));
                    item.setStrategyCode(rs.getString("strategy_code"));
                    item.setSymbol(rs.getString("symbol"));
                    item.setPeriod(rs.getInt("period"));
                    item.setStartDate(rs.getDate("start_date").toLocalDate());
                    item.setEndDate(rs.getDate("end_date").toLocalDate());
                    item.setTotalSignals(rs.getInt("total_signals"));
                    item.setWinSignals(rs.getInt("win_signals"));
                    item.setSuccessRate(rs.getBigDecimal("success_rate"));

                    Timestamp createdAt = rs.getTimestamp("created_at");
                    if (createdAt != null) {
                        item.setCreatedAt(createdAt.toLocalDateTime());
                    }

                    String payload = rs.getString("payload_json");
                    item.setPayloadJson(payload);
                    fillPayloadFields(item, payload);
                    list.add(item);
                }
                return list;
            }
        } catch (SQLException ex) {
            throw new IllegalStateException("Query strategy_backtest_result failed: " + ex.getMessage(), ex);
        }
    }

    private void fillPayloadFields(BacktestResultView view, String payload) {
        if (payload == null || payload.isBlank()) {
            return;
        }
        try {
            JsonNode root = objectMapper.readTree(payload);

            JsonNode crossUpDates = root.get("crossUpDates");
            if (crossUpDates != null && crossUpDates.isArray()) {
                view.setCrossUpDates(objectMapper.convertValue(crossUpDates, new TypeReference<List<String>>() {}));
            }

            JsonNode crossDownDates = root.get("crossDownDates");
            if (crossDownDates != null && crossDownDates.isArray()) {
                view.setCrossDownDates(
                        objectMapper.convertValue(crossDownDates, new TypeReference<List<String>>() {}));
            }

            JsonNode signals = root.get("signals");
            if (signals != null && signals.isArray()) {
                view.setSignals(
                        objectMapper.convertValue(signals, new TypeReference<List<BacktestSignalDto>>() {}));
            }
        } catch (Exception ignored) {
            // Keep payloadJson raw for troubleshooting when payload parsing fails.
        }
    }
}
