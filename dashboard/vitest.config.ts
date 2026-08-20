import { defineConfig, mergeConfig } from 'vitest/config';
import viteConfig from './vite.config.ts';

const baseConfig =
  typeof viteConfig === 'function'
    ? viteConfig({
        command: 'serve',
        mode: 'test',
        isPreview: false,
        isSsrBuild: false,
      })
    : viteConfig;

export default mergeConfig(
  baseConfig,
  defineConfig({
    ssr: {
      noExternal: ['vuetify'],
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./tests/setup.vitest.ts'],
      include: ['./tests/**/*.{vitest.ts,test.mjs}'],
      exclude: ['./tests/setup.vitest.ts', './tests/subsetMdiFont.test.mjs'],
      css: false,
      restoreMocks: true,
      clearMocks: true,
      coverage: {
        provider: 'v8',
        reportsDirectory: './coverage',
        reporter: ['text', 'json-summary'],
        include: ['src/**/*.ts'],
        exclude: [
          'src/api/generated/**',
          'src/**/*.d.ts',
          'src/main.ts',
          'src/views/**',
          'src/router/index.ts',
          'src/plugins/**',
          'src/composables/useMessages.ts',
          'src/composables/useProviderSources.ts',
          'src/composables/useVADRecording.ts',
          'src/utils/monacoLoader.ts',
          'src/utils/shiki.ts',
          'src/utils/shikiLimitedBundle.ts',
          'tests/**',
        ],
        thresholds: {
          lines: 91,
          functions: 94,
          statements: 90,
        },
      },
    },
  }),
);
