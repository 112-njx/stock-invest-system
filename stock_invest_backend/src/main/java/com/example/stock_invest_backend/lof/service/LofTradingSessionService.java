package com.example.stock_invest_backend.lof.service;

import org.springframework.stereotype.Service;

import java.time.DayOfWeek;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

@Service
public class LofTradingSessionService {

    private static final ZoneId CN_ZONE = ZoneId.of("Asia/Shanghai");
    private static final LocalTime MORNING_START = LocalTime.of(9, 30);
    private static final LocalTime MORNING_END = LocalTime.of(11, 30);
    private static final LocalTime AFTERNOON_START = LocalTime.of(13, 0);
    private static final LocalTime AFTERNOON_END = LocalTime.of(15, 0);

    public boolean isTradingOpenNow() {
        ZonedDateTime now = ZonedDateTime.now(CN_ZONE);
        DayOfWeek day = now.getDayOfWeek();
        if (day == DayOfWeek.SATURDAY || day == DayOfWeek.SUNDAY) {
            return false;
        }

        LocalTime t = now.toLocalTime();
        boolean inMorning = !t.isBefore(MORNING_START) && !t.isAfter(MORNING_END);
        boolean inAfternoon = !t.isBefore(AFTERNOON_START) && !t.isAfter(AFTERNOON_END);
        return inMorning || inAfternoon;
    }
}
