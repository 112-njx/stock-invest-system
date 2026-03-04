package com.example.stock_invest_backend.lof.event;

/*
    这是lof溢价率与触发条件联动时的
    发送事件接口
 */
public interface LofPremiumEventPublisher {

    void publish(LofPremiumEvent event);

    String channelName();
}
