package com.example.stock_invest_backend.pay;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@EnableScheduling
public class PayOrderExpiredTask {

    private static final Logger log = LoggerFactory.getLogger(PayOrderExpiredTask.class);
    private final PayOrderService payOrderService;

    public PayOrderExpiredTask(PayOrderService payOrderService) {
        this.payOrderService = payOrderService;
    }

    @Scheduled(fixedRate = 5 * 60 * 1000)
    public void closeExpiredOrders() {
        int count = payOrderService.closeExpiredOrders();
        if (count > 0) {
            log.info("定时关单: 关闭过期订单 {} 批次", count);
        }
    }
}
