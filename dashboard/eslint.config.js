const vue = require('eslint-plugin-vue');
const prettierPlugin = require('eslint-plugin-prettier');
const configPrettier = require('eslint-config-prettier');
const tseslint = require('typescript-eslint');

const { rules: vueRules } = vue;
const vue3Recommended = vue.configs['vue3-recommended'];

module.exports = [
  {
    ignores: ['dist/', 'build/', 'node_modules/', 'public/', 'dashboard/dist/', 'dashboard/node_modules/', 'env.d.ts', '.vite/', '.cache/'],
  },
  {
    files: ['**/*.vue'],
    ...vue3Recommended,
    languageOptions: {
      parser: require('vue-eslint-parser'),
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
      },
    },
    plugins: {
      vue,
      prettier: prettierPlugin,
      ...tseslint.plugin,
    },
    rules: {
      ...vue3Recommended.rules,
      ...tseslint.plugin.configs.recommended.rules,
      'vue/multi-word-component-names': 'off',
      'vue/html-self-closing': ['error', { html: { void: 'never', normal: 'always', component: 'always' }, svg: 'always', math: 'always' }],
      'vue/valid-v-slot': 'off',
      'vue/v-on-event-hyphenation': 'off',
      'vue/no-unused-components': 'off',
      'vue/no-unused-vars': 'off',
      'vue/require-default-prop': 'off',
      'vue/no-v-html': 'warn',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' }],
      '@typescript-eslint/explicit-module-boundary-types': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      'no-console': ['warn', { allow: ['warn', 'error', 'info'] }],
      'no-debugger': 'warn',
      'prettier/prettier': 'error',
    },
  },
  {
    files: ['**/*.ts', '**/*.tsx', 'src/**/*.ts', 'src/**/*.tsx'],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
      },
    },
    plugins: {
      prettier: prettierPlugin,
      ...tseslint.plugin,
    },
    rules: {
      ...tseslint.plugin.configs.recommended.rules,
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' }],
      '@typescript-eslint/explicit-module-boundary-types': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      'no-console': ['warn', { allow: ['warn', 'error', 'info'] }],
      'no-debugger': 'warn',
      'prettier/prettier': 'error',
    },
  },
  {
    files: ['scripts/**/*.mjs', 'scripts/**/*.cjs', '*.cjs'],
    languageOptions: {
      parserOptions: { sourceType: 'module' },
      env: { node: true },
    },
  },
  {
    files: ['src/components/extension/**', 'src/components/extension/componentPanel/**'],
    rules: {
      'vue/valid-v-slot': 'off',
    },
  },
  configPrettier,
];
