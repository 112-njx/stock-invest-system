package com.example.stock_invest_backend.lof.repository;

import com.example.stock_invest_backend.market.history.config.MySqlWriteProperties;
import org.springframework.stereotype.Repository;
import org.springframework.util.StringUtils;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.List;

@Repository
public class MySqlLofSymbolRegistryRepository implements LofSymbolRegistryRepository {

    private static final String QUERY_ENABLED_SQL = """
            SELECT id, symbol, name, market, enabled, priority, tags, created_at, updated_at
            FROM lof_symbol_registry
            WHERE enabled = 1
            ORDER BY priority ASC, symbol ASC
            LIMIT ?
            """;

    private static final String UPSERT_SQL = """
            INSERT INTO lof_symbol_registry (symbol, name, market, enabled, priority, tags)
            VALUES (?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                market = VALUES(market),
                enabled = VALUES(enabled),
                priority = VALUES(priority),
                tags = VALUES(tags),
                updated_at = CURRENT_TIMESTAMP
            """;

    private final MySqlWriteProperties properties;

    public MySqlLofSymbolRegistryRepository(MySqlWriteProperties properties) {
        this.properties = properties;
    }

    @Override
    public List<LofSymbolRegistryRecord> findEnabledSymbols(int limit) {
        if (!properties.isEnabled()) {
            return List.of();
        }

        int safeLimit = Math.max(1, Math.min(limit, 5000));
        try (Connection connection = DriverManager.getConnection(
                properties.getUrl(), properties.getUsername(), properties.getPassword());
             PreparedStatement ps = connection.prepareStatement(QUERY_ENABLED_SQL)) {
            ps.setInt(1, safeLimit);
            try (ResultSet rs = ps.executeQuery()) {
                List<LofSymbolRegistryRecord> records = new ArrayList<>();
                while (rs.next()) {
                    records.add(mapRecord(rs));
                }
                return records;
            }
        } catch (SQLException ex) {
            throw new IllegalStateException("Query lof_symbol_registry failed: " + ex.getMessage(), ex);
        }
    }

    @Override
    public int upsertBatch(List<LofSymbolRegistryRecord> records) {
        if (!properties.isEnabled() || records == null || records.isEmpty()) {
            return 0;
        }

        try (Connection connection = DriverManager.getConnection(
                properties.getUrl(), properties.getUsername(), properties.getPassword());
             PreparedStatement ps = connection.prepareStatement(UPSERT_SQL)) {
            connection.setAutoCommit(false);

            for (LofSymbolRegistryRecord record : records) {
                if (!StringUtils.hasText(record.getSymbol())) {
                    continue;
                }
                ps.setString(1, record.getSymbol().trim().toLowerCase());
                ps.setString(2, record.getName());
                ps.setString(3, normalizeMarket(record.getMarket()));
                ps.setBoolean(4, record.isEnabled());
                ps.setInt(5, record.getPriority() == null ? 100 : record.getPriority());
                ps.setString(6, record.getTags());
                ps.addBatch();
            }

            int[] result = ps.executeBatch();
            connection.commit();
            int affected = 0;
            for (int value : result) {
                if (value > 0) {
                    affected += value;
                }
            }
            return affected;
        } catch (SQLException ex) {
            throw new IllegalStateException("Upsert lof_symbol_registry failed: " + ex.getMessage(), ex);
        }
    }

    private LofSymbolRegistryRecord mapRecord(ResultSet rs) throws SQLException {
        LofSymbolRegistryRecord record = new LofSymbolRegistryRecord();
        record.setId(rs.getLong("id"));
        record.setSymbol(rs.getString("symbol"));
        record.setName(rs.getString("name"));
        record.setMarket(rs.getString("market"));
        record.setEnabled(rs.getBoolean("enabled"));
        record.setPriority(rs.getInt("priority"));
        record.setTags(rs.getString("tags"));

        Timestamp createdAt = rs.getTimestamp("created_at");
        if (createdAt != null) {
            record.setCreatedAt(createdAt.toLocalDateTime());
        }
        Timestamp updatedAt = rs.getTimestamp("updated_at");
        if (updatedAt != null) {
            record.setUpdatedAt(updatedAt.toLocalDateTime());
        }
        return record;
    }

    private String normalizeMarket(String market) {
        if (!StringUtils.hasText(market)) {
            return null;
        }
        String normalized = market.trim().toUpperCase();
        if ("SH".equals(normalized) || "SZ".equals(normalized)) {
            return normalized;
        }
        return normalized;
    }
}
