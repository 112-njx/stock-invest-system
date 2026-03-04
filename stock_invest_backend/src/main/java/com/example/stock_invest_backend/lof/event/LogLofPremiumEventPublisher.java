package com.example.stock_invest_backend.lof.event;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

@Component
public class LogLofPremiumEventPublisher implements LofPremiumEventPublisher {

    private static final Logger log = LoggerFactory.getLogger(LogLofPremiumEventPublisher.class);

    private final ObjectMapper objectMapper;

    public LogLofPremiumEventPublisher(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void publish(LofPremiumEvent event) {
        try {
            log.info("LOF_EVENT[channel={}]: {}", channelName(), objectMapper.writeValueAsString(event));
        } catch (Exception ex) {
            log.warn("LOF_EVENT serialize failed, channel={}, eventId={}, reason={}",
                    channelName(), event.getEventId(), ex.getMessage());
        }
    }

    @Override
    public String channelName() {
        return "log";
    }
}
