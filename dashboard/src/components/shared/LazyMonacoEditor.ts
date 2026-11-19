import { defineAsyncComponent } from 'vue';
import { setupMonaco } from '@/plugins/monaco';

/**
 * Drop-in replacement for VueMonacoEditor that loads the Monaco bundle
 * lazily on first render instead of from the entry chunk.
 */
export const LazyMonacoEditor = defineAsyncComponent(async () => {
  const { VueMonacoEditor, loader } = await import('@guolao/vue-monaco-editor');
  await setupMonaco(loader);
  return VueMonacoEditor;
});
