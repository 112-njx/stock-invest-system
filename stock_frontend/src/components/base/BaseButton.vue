<script setup lang="ts">
defineOptions({ name: 'BaseButton' })

withDefaults(
  defineProps<{
    variant?: 'primary' | 'ghost' | 'outline' | 'danger'
    size?: 'sm' | 'md' | 'lg'
    disabled?: boolean
    loading?: boolean
    block?: boolean
  }>(),
  { variant: 'primary', size: 'md', disabled: false, loading: false, block: false }
)
</script>

<template>
  <button
    class="base-btn"
    :class="[
      `variant-${variant}`,
      `size-${size}`,
      { 'is-block': block, 'is-loading': loading },
    ]"
    :disabled="disabled || loading"
  >
    <span v-if="loading" class="spinner" />
    <slot />
  </button>
</template>

<style scoped>
.base-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid transparent;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  user-select: none;
  transition:
    background-color 0.15s,
    border-color 0.15s,
    color 0.15s,
    opacity 0.15s,
    filter 0.15s;
}
.base-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.size-sm {
  height: 26px;
  padding: 0 10px;
  font-size: 12px;
}
.size-md {
  height: 32px;
  padding: 0 14px;
}
.size-lg {
  height: 38px;
  padding: 0 18px;
  font-size: 14px;
}
.is-block {
  width: 100%;
}
.variant-primary {
  background: var(--accent);
  color: #fff;
}
.variant-primary:hover:not(:disabled) {
  filter: brightness(1.1);
}
.variant-ghost {
  background: transparent;
  color: var(--text-secondary);
}
.variant-ghost:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text);
}
.variant-outline {
  background: transparent;
  border-color: var(--border-strong);
  color: var(--text);
}
.variant-outline:hover:not(:disabled) {
  background: var(--bg-hover);
}
.variant-danger {
  background: transparent;
  color: var(--up);
}
.variant-danger:hover:not(:disabled) {
  background: var(--up-soft);
}
.spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
