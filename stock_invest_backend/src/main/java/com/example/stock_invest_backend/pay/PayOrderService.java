package com.example.stock_invest_backend.pay;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.Date;
import java.util.Set;
import java.util.concurrent.ThreadLocalRandom;

@Service
public class PayOrderService extends ServiceImpl<PayOrderMapper, PayOrder> {

    private static final Set<Long> ALLOWED_AMOUNTS = Set.of(1000L, 2000L);

    public PayOrder createOrder(long amount) {
        if (!ALLOWED_AMOUNTS.contains(amount)) {
            throw new IllegalArgumentException("仅支持 1000(10元) 或 2000(20元)");
        }

        String subject = (amount == 1000) ? "股票策略会员-10元档" : "股票策略会员-20元档";
        Date now = new Date();
        Date expiredTime = Date.from(LocalDateTime.now().plusHours(2)
                .atZone(ZoneId.systemDefault()).toInstant());

        PayOrder order = new PayOrder();
        order.setPayOrderId(generateOrderId());
        order.setAmount(amount);
        order.setSubject(subject);
        order.setState(PayOrder.STATE_INIT);
        order.setExpiredTime(expiredTime);
        order.setCreatedAt(now);
        save(order);
        return order;
    }

    public boolean updateToSuccess(String payOrderId, String channelOrderNo) {
        PayOrder updateRecord = new PayOrder();
        updateRecord.setState(PayOrder.STATE_SUCCESS);
        updateRecord.setChannelOrderNo(channelOrderNo);
        updateRecord.setSuccessTime(new Date());

        return update(updateRecord, new LambdaUpdateWrapper<PayOrder>()
                .eq(PayOrder::getPayOrderId, payOrderId)
                .in(PayOrder::getState, PayOrder.STATE_INIT, PayOrder.STATE_ING));
    }

    public IPage<PayOrder> listOrders(int page, int size) {
        size = Math.min(Math.max(size, 1), 100);
        return page(new Page<>(page, size),
                new LambdaQueryWrapper<PayOrder>().orderByDesc(PayOrder::getCreatedAt));
    }

    public int closeExpiredOrders() {
        PayOrder updateRecord = new PayOrder();
        updateRecord.setState(PayOrder.STATE_CLOSED);

        boolean updated = update(updateRecord, new LambdaUpdateWrapper<PayOrder>()
                .eq(PayOrder::getState, PayOrder.STATE_INIT)
                .lt(PayOrder::getExpiredTime, new Date()));
        return updated ? 1 : 0;
    }

    private String generateOrderId() {
        long ts = System.currentTimeMillis();
        int rand = ThreadLocalRandom.current().nextInt(1000, 9999);
        return "P" + ts + rand;
    }
}
