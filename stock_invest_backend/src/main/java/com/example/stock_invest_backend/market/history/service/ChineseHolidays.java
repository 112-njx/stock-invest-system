package com.example.stock_invest_backend.market.history.service;

import java.time.LocalDate;
import java.time.MonthDay;
import java.util.Set;

/**
 * Minimal A-share holiday calendar (weekend already filtered upstream).
 *
 * <p>Covers observed CSRC holiday closures 2024-2026 plus fixed-date rules.
 * Non-exhaustive on purpose: completeness check tolerates a 5% error window,
 * and Python补数 will still upsert idempotently on actual trading days.
 */
final class ChineseHolidays {

    private ChineseHolidays() {}

    private static final Set<MonthDay> FIXED_DAYS = Set.of(
            MonthDay.of(1, 1),
            MonthDay.of(5, 1),
            MonthDay.of(10, 1),
            MonthDay.of(10, 2),
            MonthDay.of(10, 3)
    );

    private static final Set<LocalDate> OBSERVED = Set.of(
            LocalDate.of(2024, 2, 12), LocalDate.of(2024, 2, 13), LocalDate.of(2024, 2, 14),
            LocalDate.of(2024, 2, 15), LocalDate.of(2024, 2, 16),
            LocalDate.of(2024, 4, 4), LocalDate.of(2024, 4, 5),
            LocalDate.of(2024, 5, 2), LocalDate.of(2024, 5, 3),
            LocalDate.of(2024, 6, 10),
            LocalDate.of(2024, 9, 16), LocalDate.of(2024, 9, 17),
            LocalDate.of(2024, 10, 2), LocalDate.of(2024, 10, 3), LocalDate.of(2024, 10, 4),
            LocalDate.of(2024, 10, 7),
            LocalDate.of(2025, 1, 28), LocalDate.of(2025, 1, 29), LocalDate.of(2025, 1, 30),
            LocalDate.of(2025, 1, 31), LocalDate.of(2025, 2, 3), LocalDate.of(2025, 2, 4),
            LocalDate.of(2025, 4, 4),
            LocalDate.of(2025, 5, 2), LocalDate.of(2025, 5, 5),
            LocalDate.of(2025, 5, 31), LocalDate.of(2025, 6, 2),
            LocalDate.of(2025, 10, 2), LocalDate.of(2025, 10, 3), LocalDate.of(2025, 10, 6),
            LocalDate.of(2025, 10, 7), LocalDate.of(2025, 10, 8),
            LocalDate.of(2026, 2, 16), LocalDate.of(2026, 2, 17), LocalDate.of(2026, 2, 18),
            LocalDate.of(2026, 2, 19), LocalDate.of(2026, 2, 20),
            LocalDate.of(2026, 4, 6),
            LocalDate.of(2026, 5, 4), LocalDate.of(2026, 5, 5),
            LocalDate.of(2026, 6, 19),
            LocalDate.of(2026, 9, 25),
            LocalDate.of(2026, 10, 2), LocalDate.of(2026, 10, 5), LocalDate.of(2026, 10, 6),
            LocalDate.of(2026, 10, 7), LocalDate.of(2026, 10, 8)
    );

    static boolean isHoliday(LocalDate d) {
        if (FIXED_DAYS.contains(MonthDay.of(d.getMonthValue(), d.getDayOfMonth()))) return true;
        return OBSERVED.contains(d);
    }
}
