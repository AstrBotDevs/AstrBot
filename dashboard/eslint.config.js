import prettierPlugin from "eslint-plugin-prettier";
import pluginVue from "eslint-plugin-vue";
import skipFormatting from "@vue/eslint-config-prettier/skip-formatting";
import {
  defineConfigWithVueTs,
  vueTsConfigs,
} from "@vue/eslint-config-typescript";
import globals from "globals";

// Global ignores dir
const ignores = {
  ignores: [
    "**/node_modules/**",
    "dist/",
    "build/",
    "public/",
    "env.d.ts",
    ".vite/",
    ".cache/",
  ],
};

// Base Prettier and ESLint Config
const base = {
  plugins: {
    prettier: prettierPlugin,
  },
  rules: {
    "prettier/prettier": "error",
    "no-console": ["warn", { allow: ["warn", "error", "info"] }],
    "no-debugger": "warn",
    "linebreak-style": ["off", "unix"],
    "@typescript-eslint/no-unused-vars": [
      "warn",
      {
        argsIgnorePattern: "^_",
        varsIgnorePattern: "^_",
        caughtErrorsIgnorePattern: "^_",
      },
    ],
    "@typescript-eslint/explicit-module-boundary-types": "off",
    "@typescript-eslint/no-explicit-any": "off",
  },
};

// Base Config for Vue
const vue = {
  rules: {
    "vue/multi-word-component-names": "off",
    "vue/valid-v-slot": "off",
    "vue/v-on-event-hyphenation": "off",
    "vue/require-default-prop": "off",
    "vue/no-v-html": "warn",
    "vue/block-lang": "off",
    "vue/no-unused-components": "off",
    "vue/no-unused-vars": "off",
  },
};

// Special config for scripts/*
const scripts = {
  files: ["scripts/**/*.mjs", "scripts/**/*.cjs", "*.cjs"],
  languageOptions: {
    parserOptions: { sourceType: "module" },
    globals: { ...globals.node },
  },
};

// Export all configs
export default defineConfigWithVueTs(
  // ignore first
  ignores,
  // use recommanded configs
  pluginVue.configs["flat/essential"],
  vueTsConfigs.recommended,
  // custom configs
  base,
  vue,
  scripts,
  // add skip formatting for prettier because already have eslint
  skipFormatting,
);
