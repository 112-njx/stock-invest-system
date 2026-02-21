package com.example.stock_invest_backend.market.history.repository;

import com.example.stock_invest_backend.market.history.config.MySqlWriteProperties;
import com.example.stock_invest_backend.market.history.dto.StockDailyKlineRecord;
import org.springframework.stereotype.Repository;

import java.sql.Connection;
import java.sql.Date;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

@Repository
public class MySqlStockDailyKlineRepository implements StockDailyKlineRepository {

    private static final String UPSERT_SQL = """
            INSERT INTO stock_daily_kline
            (symbol, trade_date, open_price, high_price, low_price, close_price, volume, turnover, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
              open_price=VALUES(open_price),
              high_price=VALUES(high_price),
              low_price=VALUES(low_price),
              close_price=VALUES(close_price),
              volume=VALUES(volume),
              turnover=VALUES(turnover),
              source=VALUES(source),
              updated_at=CURRENT_TIMESTAMP
            """;

    private final MySqlWriteProperties properties;

    public MySqlStockDailyKlineRepository(MySqlWriteProperties properties) {
        this.properties = properties;
    }

    @Override
    public int upsertBatch(List<StockDailyKlineRecord> records) {
        if (!properties.isEnabled() || records == null || records.isEmpty()) {
            return 0;
        }

        try (Connection connection = DriverManager.getConnection(
                properties.getUrl(), properties.getUsername(), properties.getPassword());
             PreparedStatement ps = connection.prepareStatement(UPSERT_SQL)) {
            connection.setAutoCommit(false);

            for (StockDailyKlineRecord item : records) {
                ps.setString(1, item.getSymbol());
                ps.setDate(2, Date.valueOf(item.getTradeDate()));
                ps.setBigDecimal(3, item.getOpenPrice());
                ps.setBigDecimal(4, item.getHighPrice());
                ps.setBigDecimal(5, item.getLowPrice());
                ps.setBigDecimal(6, item.getClosePrice());
                ps.setLong(7, item.getVolume());
                ps.setBigDecimal(8, item.getTurnover());
                ps.setString(9, item.getSource());
                ps.addBatch();
            }

            int[] result = ps.executeBatch();
            connection.commit();
            int count = 0;
            for (int value : result) {
                if (value >= 0) {
                    count += value;
                }
            }
            return count;
        } catch (SQLException ex) {
            throw new IllegalStateException("Upsert stock_daily_kline failed: " + ex.getMessage(), ex);
        }
    }
}
