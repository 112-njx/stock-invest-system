package com.example.stock_invest_backend.lof.service;

import com.example.stock_invest_backend.lof.config.LofPremiumProperties;
import com.example.stock_invest_backend.lof.dto.LofPremiumItem;
import com.example.stock_invest_backend.lof.dto.LofPremiumStatus;
import com.example.stock_invest_backend.lof.event.LofPremiumEvent;
import com.example.stock_invest_backend.lof.event.LofPremiumEventPublisher;
import com.example.stock_invest_backend.lof.event.LofPremiumEventType;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
/**
  这是溢价率提示风险告警
  每个 item 发布 LOF_PREMIUM_SNAPSHOT
    溢价率越过阈值发布 LOF_PREMIUM_ALERT
    按 symbol 冷却（cooldownSeconds）避免重复告警风暴
 */
@Service
public class LofPremiumEventService {

    private final List<LofPremiumEventPublisher> publishers;
    private final LofPremiumProperties properties;
    private final Map<String, Long> alertCooldownGate = new ConcurrentHashMap<>();

    public LofPremiumEventService(List<LofPremiumEventPublisher> publishers,
                                  LofPremiumProperties properties) {
        this.publishers = publishers;
        this.properties = properties;
    }

    public void publishSnapshotAndAlerts(List<LofPremiumItem> items) {
        if (!properties.isEventPublishEnabled() || items == null || items.isEmpty()) {
            return;
        }

        for (LofPremiumItem item : items) {
            if (!StringUtils.hasText(item.getSymbol())) {
                continue;
            }
            publish(buildEvent(item, LofPremiumEventType.LOF_PREMIUM_SNAPSHOT, "snapshot"));
            maybePublishAlert(item);
        }
    }

    private void maybePublishAlert(LofPremiumItem item) {
        if (item.getStatus() != LofPremiumStatus.OK || item.getPremiumRate() == null) {
            return;
        }

        BigDecimal up = BigDecimal.valueOf(properties.getAlertThresholdUp());
        BigDecimal down = BigDecimal.valueOf(properties.getAlertThresholdDown());
        BigDecimal rate = item.getPremiumRate();
        boolean trigger = rate.compareTo(up) >= 0 || rate.compareTo(down) <= 0;
        if (!trigger) {
            return;
        }

        long now = System.currentTimeMillis();
        long cooldownMs = Math.max(10, properties.getAlertCooldownSeconds()) * 1000L;
        Long nextAllowed = alertCooldownGate.get(item.getSymbol());
        if (nextAllowed != null && now < nextAllowed) {
            return;
        }
        alertCooldownGate.put(item.getSymbol(), now + cooldownMs);
        publish(buildEvent(item, LofPremiumEventType.LOF_PREMIUM_ALERT, "threshold crossed"));
    }

    private LofPremiumEvent buildEvent(LofPremiumItem item, LofPremiumEventType type, String message) {
        LofPremiumEvent event = new LofPremiumEvent();
        event.setEventId(UUID.randomUUID().toString());
        event.setEventType(type);
        event.setSymbol(item.getSymbol());
        event.setPremiumRate(item.getPremiumRate());
        event.setStatus(item.getStatus());
        event.setNavType(item.getNavType());
        event.setQuoteTime(item.getQuoteTime());
        event.setProducedAt(Instant.now());
        event.setSource("lof-premium-service");
        event.setVersion(properties.getEventVersion());
        event.setMessage(message);
        return event;
    }

    private void publish(LofPremiumEvent event) {
        for (LofPremiumEventPublisher publisher : publishers) {
            publisher.publish(event);
        }
    }
}
