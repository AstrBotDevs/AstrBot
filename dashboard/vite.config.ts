import { readFileSync } from 'fs';
import { fileURLToPath, URL } from 'url';
import { defineConfig, type Plugin } from 'vite';
import vue from '@vitejs/plugin-vue';
import vuetify from 'vite-plugin-vuetify';
import webfontDl from 'vite-plugin-webfont-dl';
// @ts-ignore — .mjs not in TS project scope; Vite resolves this at runtime
import { runMdiSubset } from './scripts/subset-mdi-font.mjs';

const vadRuntimeAssets = new Map<string, string>([
  [
    '/vad/bundle.min.js',
    fileURLToPath(new URL('./node_modules/@ricky0123/vad-web/dist/bundle.min.js', import.meta.url))
  ],
  [
    '/vad/vad.worklet.bundle.min.js',
    fileURLToPath(
      new URL('./node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js', import.meta.url)
    )
  ],
  [
    '/vad/silero_vad_v5.onnx',
    fileURLToPath(new URL('./node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx', import.meta.url))
  ],
  [
    '/vad/silero_vad_legacy.onnx',
    fileURLToPath(new URL('./node_modules/@ricky0123/vad-web/dist/silero_vad_legacy.onnx', import.meta.url))
  ],
  [
    '/vad/onnx/ort.wasm.min.js',
    fileURLToPath(new URL('./node_modules/onnxruntime-web/dist/ort.wasm.min.js', import.meta.url))
  ],
  [
    '/vad/onnx/ort-wasm-simd-threaded.mjs',
    fileURLToPath(
      new URL('./node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs', import.meta.url)
    )
  ],
  [
    '/vad/onnx/ort-wasm-simd-threaded.wasm',
    fileURLToPath(
      new URL('./node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm', import.meta.url)
    )
  ]
]);

// Vite plugin: run MDI icon font subsetting (build only)
function mdiSubset() {
  return {
    name: 'vite-plugin-mdi-subset',
    async buildStart() {
      console.log('\n🔧 Running MDI icon font subsetting...');
      await runMdiSubset();
    },
  };
}

function vadRuntimeAssetsPlugin(): Plugin {
  return {
    name: 'vite-plugin-vad-runtime-assets',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const pathname = new URL(request.url ?? '/', 'http://localhost').pathname;
        const assetPath = vadRuntimeAssets.get(pathname);
        if (!assetPath) {
          next();
          return;
        }

        const extension = pathname.slice(pathname.lastIndexOf('.') + 1);
        response.statusCode = 200;
        response.setHeader(
          'Content-Type',
          extension === 'wasm'
            ? 'application/wasm'
            : extension === 'onnx'
              ? 'application/octet-stream'
              : 'text/javascript; charset=utf-8'
        );
        response.end(readFileSync(assetPath));
      });
    },
    generateBundle() {
      for (const [path, sourcePath] of vadRuntimeAssets) {
        this.emitFile({
          type: 'asset',
          fileName: path.slice(1),
          source: readFileSync(sourcePath)
        });
      }
    }
  };
}

// https://vitejs.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [
    // Only run MDI subsetting during production builds, skip in dev server
    ...(command === 'build' ? [mdiSubset()] : []),
    vadRuntimeAssetsPlugin(),
    vue({
      template: {
        compilerOptions: {
          isCustomElement: (tag) => ['v-list-recognize-title'].includes(tag)
        }
      }
    }),
    vuetify({
      autoImport: true
    }),
    webfontDl()
  ],
  resolve: {
    alias: [
      {
        find: /^shiki$/,
        replacement: fileURLToPath(new URL('./src/utils/shikiLimitedBundle.js', import.meta.url))
      },
      {
        find: /^stream-monaco$/,
        replacement: fileURLToPath(new URL('./src/utils/streamMonacoDisabled.js', import.meta.url))
      },
      {
        find: 'mermaid',
        replacement: 'mermaid/dist/mermaid.js'
      },
      {
        find: '@',
        replacement: fileURLToPath(new URL('./src', import.meta.url))
      }
    ]
  },
  css: {
    preprocessorOptions: {
      scss: {}
    }
  },
  build: {
    sourcemap: false,
    chunkSizeWarningLimit: 1024 * 1024 // Set the limit to 1 MB
  },
  optimizeDeps: {
    exclude: ['vuetify'],
    entries: ['./src/**/*.vue']
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:6185/',
        changeOrigin: true,
        ws: true
      }
    }
  }
}));
