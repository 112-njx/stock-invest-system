package com.example.stock_invest_backend.lof.event;

import com.example.stock_invest_backend.lof.config.LofPremiumProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

/**
 桥接预留实现
 当前桥接实现只做标准化 payload 预留日志，后续可替换为 Redis Stream/Kafka/
 HTTP bridge
 */
@Component
public class CppBridgeLofPremiumEventPublisher implements LofPremiumEventPublisher {

    private static final Logger log = LoggerFactory.getLogger(CppBridgeLofPremiumEventPublisher.class);

    private final LofPremiumProperties properties;
    private final ObjectMapper objectMapper;

    public CppBridgeLofPremiumEventPublisher(LofPremiumProperties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    @Override
    public void publish(LofPremiumEvent event) {
        if (!properties.isBridgeEnabled()) {
            return;
        }
        try {
            String payload = objectMapper.writeValueAsString(event);
            // Reserved: push this payload to Redis Stream / Kafka / HTTP bridge in next stage.
            log.info("LOF_EVENT_BRIDGE[channel={}]: {}", channelName(), payload);
        } catch (Exception ex) {
            log.warn("LOF_EVENT_BRIDGE serialize failed, eventId={}, reason={}",
                    event.getEventId(), ex.getMessage());
        }
    }

    @Override
    public String channelName() {
        return "cpp-bridge";
    }
}
