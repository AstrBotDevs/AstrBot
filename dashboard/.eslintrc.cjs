module.exports = {
  root: true,
  env: {
    browser: true,
    node: true,
    es2021: true,
  },

  // Use vue-eslint-parser so .vue SFCs are parsed correctly.
  parser: "vue-eslint-parser",

  parserOptions: {
    // vue-eslint-parser will forward the script content to this parser
    parser: "@typescript-eslint/parser",
    ecmaVersion: "latest",
    sourceType: "module",
    extraFileExtensions: [".vue"],
    ecmaFeatures: {
      jsx: true,
    },
    // NOTE: Intentionally NO `project` here to avoid requiring type-aware linting.
    // This keeps eslint fast and avoids the TSConfig inclusion errors.
  },

  plugins: ["vue", "@typescript-eslint"],

  extends: [
    "eslint:recommended",
    "plugin:vue/vue3-recommended",
    "plugin:@typescript-eslint/recommended",
    // Intentionally not extending type-aware or prettier-requiring configs.
  ],

  settings: {
    // Allow using Vue compiler macros like defineProps/defineEmits in templates
    "vue/setup-compiler-macros": true,
  },

  // Avoid linting build artifacts and generated files
  ignorePatterns: [
    "dist/",
    "build/",
    "node_modules/",
    "public/",
    "dashboard/dist/",
    "dashboard/node_modules/",
    "env.d.ts",
    "scripts/**/*.mjs",
    ".vite/",
    ".cache/",
  ],

  rules: {
    // Keep console/debug permissible but warned
    "no-console": ["warn", { allow: ["warn", "error", "info"] }],
    "no-debugger": "warn",

    // TypeScript rules (relaxed)
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

    // Vue rules adjustments — relax a few rules that generate a lot of noise
    // These are intentionally relaxed to allow incremental, safe fixes of template code.
    "vue/multi-word-component-names": "off",
    "vue/html-self-closing": [
      "error",
      {
        html: {
          void: "never",
          normal: "always",
          component: "always",
        },
        svg: "always",
        math: "always",
      },
    ],

    // Reduce template noise for legacy / Vuetify patterns used across this codebase
    "vue/valid-v-slot": "off",
    "vue/v-on-event-hyphenation": "off",
    "vue/no-unused-components": "off",
    // Broadly disable unused vars detection for templates to avoid false positives from compiled/generated template usage
    "vue/no-unused-vars": "off",
    "vue/require-default-prop": "off",
    // Keep v-html as a warn so security-sensitive usage is highlighted
    "vue/no-v-html": "warn",
  },

  overrides: [
    // Vue Single File Components
    {
      files: ["*.vue", "src/**/*.vue"],
      parser: "vue-eslint-parser",
      parserOptions: {
        parser: "@typescript-eslint/parser",
        extraFileExtensions: [".vue"],
        ecmaVersion: "latest",
        sourceType: "module",
        // Enable type-aware rules for script blocks inside .vue files
        project: "./tsconfig.eslint.json",
        tsconfigRootDir: __dirname,
      },
      rules: {
        // Component/template specific overrides can go here
      },
    },

    // TypeScript files (no project required)
    {
      files: ["*.ts", "*.tsx", "src/**/*.ts", "src/**/*.tsx"],
      parser: "@typescript-eslint/parser",
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        // Use type-aware linting for TS files via the dedicated tsconfig for ESLint
        project: "./tsconfig.eslint.json",
        tsconfigRootDir: __dirname,
      },
      rules: {
        // Project-specific relaxations for TS files
      },
    },

    // Node scripts / tooling
    {
      files: ["scripts/**/*.mjs", "scripts/**/*.cjs", "*.cjs"],
      env: { node: true },
      parserOptions: { sourceType: "module" },
    },
    // Disable strict v-slot validation for extension component panels where shorthand slots are used
    {
      files: [
        "src/components/extension/componentPanel/**",
        "src/components/extension/**",
      ],
      rules: {
        "vue/valid-v-slot": "off",
      },
    },
  ],
};
