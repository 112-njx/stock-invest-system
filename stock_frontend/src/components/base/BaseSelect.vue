<script setup lang="ts">
defineOptions({ name: 'BaseSelect' })

withDefaults(
  defineProps<{
    modelValue: string | number
    options?: { label: string; value: string | number }[]
    placeholder?: string
  }>(),
  { options: () => [], placeholder: '请选择' }
)

defineEmits<{ (e: 'update:modelValue', value: string | number): void }>()
</script>

<template>
  <select
    class="base-select"
    :value="modelValue"
    @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
  >
    <option v-if="modelValue === '' || modelValue === undefined" value="" disabled hidden>
      {{ placeholder }}
    </option>
    <option v-for="o in options" :key="String(o.value)" :value="o.value">
      {{ o.label }}
    </option>
  </select>
</template>

<style scoped>
.base-select {
  height: 32px;
  padding: 0 8px;
  background: var(--bg-panel-2);
  color: var(--text);
  border: 1px solid var(--border-strong);
  border-radius: 4px;
  font-size: 13px;
  outline: none;
  cursor: pointer;
}
.base-select:focus {
  border-color: var(--accent);
}
</style>
