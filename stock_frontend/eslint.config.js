import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'

export default [
  { ignores: ['dist', 'node_modules', 'coverage'] },
  js.configs.recommended,
  ...pluginVue.configs['flat/essential'],
  {
    // TS / JS 文件使用 TS parser
    files: ['**/*.{ts,js,mjs,cjs}'],
    languageOptions: {
      parser: tseslint.parser,
      globals: { ...globals.browser, ...globals.node },
    },
    rules: {
      // 类型/未使用检查交给 vue-tsc，ESLint 只做基础质量检查
      'no-unused-vars': 'off',
    },
  },
  {
    // Vue SFC：script 内部使用 TS parser
    files: ['**/*.vue'],
    languageOptions: {
      globals: { ...globals.browser },
      parserOptions: { parser: tseslint.parser, extraFileExtensions: ['.vue'] },
    },
    rules: {
      'vue/multi-word-component-names': 'off',
      'no-unused-vars': 'off',
    },
  },
]
