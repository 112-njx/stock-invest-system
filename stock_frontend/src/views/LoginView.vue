<script setup lang="ts">
/**
 * G35 · 独立登录页（方案 B：`/login`，deep link 强制跳转用）。
 *
 * 视觉严格按规格书 `docs/Agent_v0.3/login_page_design_v0.3.md` 实现：
 * - 左右 56/44 分栏 + 深色科技渐变背景（§1.1/§1.2）
 * - 左上角**无 logo**（§2.1）
 * - 左侧三卡片（page1/page2/page3）纵向排列，鼠标重心 3D 倾斜（§2.2/§2.4）
 * - 右侧表单复用 AuthForm（含 QQ 邮箱按钮 §3.2、分隔线 §3.3、Tab §3.1）
 * - <1024px 上下堆叠、纵向滚动（§4）
 *
 * 底部版权条由 App.vue 的 AppFooter 全局提供（G03），此处不重复渲染。
 */
import { useRoute, useRouter } from 'vue-router'
import AuthForm from '@/components/auth/AuthForm.vue'
import LoginFeatureCard from '@/components/login/LoginFeatureCard.vue'
import { loginCards } from '@/config/loginCards'

const route = useRoute()
const router = useRouter()

/** 登录/注册成功：回到来源页（默认行情首页），独立页保留跳转语义 */
function onSuccess() {
  const redirect = (route.query.redirect as string) || '/'
  router.push(redirect)
}
</script>

<template>
  <div class="login-page">
    <div class="login-split">
      <!-- 左侧功能区（约 56%） -->
      <section class="login-left">
        <!-- 规格书 §2.1：不渲染任何品牌 logo；仅两行大标题 + 一行副标题 -->
        <div class="left-head">
          <h1 class="left-head__title">追踪收益，领取奖励，<br />切换策略</h1>
          <p class="left-head__sub">行情、策略与 AI Agent，一个终端完成</p>
        </div>

        <!-- 规格书 §2.2：三卡片纵向排列，内容可配置（见 src/config/loginCards.ts） -->
        <div class="left-cards">
          <LoginFeatureCard v-for="card in loginCards" :key="card.id" :card="card" />
        </div>
      </section>

      <!-- 右侧表单区（约 44%） -->
      <section class="login-right">
        <div class="login-right__inner">
          <AuthForm @success="onSuccess" />
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  /* 规格书 §6：深色科技渐变背景 */
  background: linear-gradient(135deg, #0b1020 0%, #101828 45%, #0d1b2e 100%);
  /* 极淡光晕装饰（透明度 ≤0.06，不抢内容） */
  background-image:
    radial-gradient(60% 50% at 18% 12%, rgba(59, 130, 246, 0.06), transparent 70%),
    radial-gradient(50% 45% at 85% 85%, rgba(34, 197, 94, 0.05), transparent 70%),
    linear-gradient(135deg, #0b1020 0%, #101828 45%, #0d1b2e 100%);
}
.login-split {
  display: flex;
  height: 100%;
  min-height: 0;
}

/* ---- 左侧 56% ---- */
.login-left {
  flex: 0 0 56%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  padding: 48px 56px;
}
.left-head {
  flex: none;
  margin-bottom: 32px;
}
.left-head__title {
  font-size: 30px;
  font-weight: 700;
  line-height: 1.35;
  color: #fff;
}
.left-head__sub {
  margin-top: 10px;
  font-size: 14px;
  color: var(--text-muted);
}
.left-cards {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ---- 右侧 44% ---- */
.login-right {
  flex: 0 0 44%;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 56px;
}
.login-right__inner {
  width: 100%;
  max-width: 380px;
}

/* ---- 规格书 §4：窄屏（<1024px）上下堆叠、纵向滚动 ---- */
@media (max-width: 1023px) {
  .login-page {
    overflow-y: auto;
  }
  .login-split {
    flex-direction: column;
    height: auto;
  }
  .login-left,
  .login-right {
    flex: none;
    padding: 32px 20px;
  }
  .login-left {
    /* 堆叠时三卡片改横向排列，避免纵向占用过长 */
    gap: 20px;
  }
  .left-cards {
    flex: none;
    flex-direction: row;
    height: 180px;
  }
  .login-right__inner {
    max-width: none;
  }
}
</style>
