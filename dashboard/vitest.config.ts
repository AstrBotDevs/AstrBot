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
    },
  }),
);
