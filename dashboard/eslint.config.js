// eslint-disable-next-line @typescript-eslint/no-require-imports
const prettierPlugin = require("eslint-plugin-prettier");
// eslint-disable-next-line @typescript-eslint/no-require-imports
const configPrettier = require("eslint-config-prettier");
// eslint-disable-next-line @typescript-eslint/no-require-imports
const vueTsConfig = require("@vue/eslint-config-typescript");

module.exports = [
  {
    ignores: [
      "dist/",
      "build/",
      "node_modules/",
      "public/",
      "dashboard/dist/",
      "dashboard/node_modules/",
      "env.d.ts",
      ".vite/",
      ".cache/",
    ],
  },
  ...vueTsConfig.createConfig(),
  {
    plugins: {
      prettier: prettierPlugin,
    },
    rules: {
      "vue/multi-word-component-names": "off",
      "vue/html-self-closing": [
        "error",
        {
          html: { void: "never", normal: "always", component: "always" },
          svg: "always",
          math: "always",
        },
      ],
      "vue/valid-v-slot": "off",
      "vue/v-on-event-hyphenation": "off",
      "vue/no-unused-components": "off",
      "vue/no-unused-vars": "off",
      "vue/require-default-prop": "off",
      "vue/no-v-html": "warn",
      "vue/block-lang": "off",
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
      "no-console": ["warn", { allow: ["warn", "error", "info"] }],
      "no-debugger": "warn",
      "prettier/prettier": "error",
    },
  },
  {
    files: ["scripts/**/*.mjs", "scripts/**/*.cjs", "*.cjs"],
    languageOptions: {
      parserOptions: { sourceType: "module" },
      globals: { node: true },
    },
  },
  {
    files: [
      "src/components/extension/**",
      "src/components/extension/componentPanel/**",
    ],
    rules: {
      "vue/valid-v-slot": "off",
    },
  },
  configPrettier,
];
