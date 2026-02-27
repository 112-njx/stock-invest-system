package com.example.stock_invest_backend.lof.cache;

import com.example.stock_invest_backend.lof.config.LofPremiumProperties;
import com.example.stock_invest_backend.lof.dto.LofPremiumItem;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

import java.time.Duration;
import java.util.Optional;

//lof基金redis缓存实现
//缓存规则：
//      - Key：lof:premium:{symbol}
//      - Value：LofPremiumItem JSON
//      - TTL：读取 lof.premium.cache-ttl-seconds，并强制夹紧到 3~10 秒
//      - 缓存读写失败不影响主流程（best-effort）

@Component
public class RedisLofPremiumCacheGateway implements LofPremiumCacheGateway {

    private static final String KEY_PREFIX = "lof:premium:";

    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper;
    private final LofPremiumProperties properties;

    public RedisLofPremiumCacheGateway(StringRedisTemplate redisTemplate,
                                       ObjectMapper objectMapper,
                                       LofPremiumProperties properties) {
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
        this.properties = properties;
    }

    @Override
    public Optional<LofPremiumItem> get(String symbol) {
        try {
            String json = redisTemplate.opsForValue().get(buildKey(symbol));
            if (json == null || json.isBlank()) {
                return Optional.empty();
            }
            LofPremiumItem item = objectMapper.readValue(json, LofPremiumItem.class);
            return Optional.of(item);
        } catch (RuntimeException ex) {
            return Optional.empty();
        } catch (Exception ex) {
            return Optional.empty();
        }
    }

    @Override
    public void put(String symbol, LofPremiumItem item) {
        try {
            String json = objectMapper.writeValueAsString(item);
            redisTemplate.opsForValue().set(buildKey(symbol), json, resolveTtl());
        } catch (Exception ignored) {
            // cache write is best effort, should not break main response path
        }
    }

    private String buildKey(String symbol) {
        return KEY_PREFIX + symbol.toLowerCase();
    }

    private Duration resolveTtl() {
        int ttl = Math.max(3, Math.min(properties.getCacheTtlSeconds(), 10));
        return Duration.ofSeconds(ttl);
    }
}
