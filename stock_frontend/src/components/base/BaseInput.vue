<script setup lang="ts">
defineOptions({ name: 'BaseInput' })

withDefaults(
  defineProps<{
    modelValue: string
    type?: 'text' | 'password'
    placeholder?: string
    label?: string
    error?: string
    autocomplete?: string
    maxlength?: number
  }>(),
  { type: 'text', placeholder: '', label: '', error: '', autocomplete: 'off' }
)

defineEmits<{ (e: 'update:modelValue', value: string): void }>()
</script>

<template>
  <label class="base-input">
    <span v-if="label" class="base-input__label">{{ label }}</span>
    <input
      :type="type"
      :value="modelValue"
      :placeholder="placeholder"
      :autocomplete="autocomplete"
      :maxlength="maxlength"
      class="base-input__field"
      :class="{ 'has-error': error }"
      @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
    <span v-if="error" class="base-input__error">{{ error }}</span>
  </label>
</template>

<style scoped>
.base-input {
  display: flex;
  flex-direction: column;
  gap: 5px;
  width: 100%;
}
.base-input__label {
  font-size: 13px;
  color: var(--text-secondary);
}
.base-input__field {
  height: 34px;
  padding: 0 10px;
  background: var(--bg-panel-2);
  border: 1px solid var(--border-strong);
  border-radius: 4px;
  color: var(--text);
  font-size: 13px;
  outline: none;
  transition:
    border-color 0.15s,
    box-shadow 0.15s;
}
.base-input__field:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}
.base-input__field::placeholder {
  color: var(--text-muted);
}
.base-input__field.has-error {
  border-color: var(--up);
}
.base-input__error {
  font-size: 12px;
  color: var(--up);
}
</style>
