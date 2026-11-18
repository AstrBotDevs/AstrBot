import type { loader } from '@guolao/vue-monaco-editor';

type MonacoLoader = typeof loader;

let monacoSetupPromise: Promise<void> | null = null;

/**
 * Load Monaco Editor on demand and wire it into @guolao/vue-monaco-editor.
 * The editor bundle is several MB, so it is kept out of the entry chunk and
 * only fetched the first time an editor is actually mounted.
 *
 * Args:
 *   loaderInstance: The loader exported by @guolao/vue-monaco-editor.
 *
 * Returns:
 *   A promise resolving once Monaco is configured on the loader.
 */
export function setupMonaco(loaderInstance: MonacoLoader): Promise<void> {
  if (!monacoSetupPromise) {
    monacoSetupPromise = (async () => {
      const [monaco, editorWorkerModule, jsonWorkerModule, cssWorkerModule, htmlWorkerModule] =
        await Promise.all([
          import('monaco-editor/esm/vs/editor/editor.api'),
          import('monaco-editor/esm/vs/editor/editor.worker?worker'),
          import('monaco-editor/esm/vs/language/json/json.worker?worker'),
          import('monaco-editor/esm/vs/language/css/css.worker?worker'),
          import('monaco-editor/esm/vs/language/html/html.worker?worker'),
          // Side-effect-only language contributions
          import('monaco-editor/esm/vs/basic-languages/dockerfile/dockerfile.contribution'),
          import('monaco-editor/esm/vs/basic-languages/ini/ini.contribution'),
          import('monaco-editor/esm/vs/basic-languages/javascript/javascript.contribution'),
          import('monaco-editor/esm/vs/basic-languages/markdown/markdown.contribution'),
          import('monaco-editor/esm/vs/basic-languages/powershell/powershell.contribution'),
          import('monaco-editor/esm/vs/basic-languages/python/python.contribution'),
          import('monaco-editor/esm/vs/basic-languages/shell/shell.contribution'),
          import('monaco-editor/esm/vs/basic-languages/sql/sql.contribution'),
          import('monaco-editor/esm/vs/basic-languages/typescript/typescript.contribution'),
          import('monaco-editor/esm/vs/basic-languages/xml/xml.contribution'),
          import('monaco-editor/esm/vs/basic-languages/yaml/yaml.contribution'),
          import('monaco-editor/esm/vs/language/css/monaco.contribution'),
          import('monaco-editor/esm/vs/language/html/monaco.contribution'),
          import('monaco-editor/esm/vs/language/json/monaco.contribution')
        ]);

      (self as any).MonacoEnvironment = {
        getWorker(_: string, label: string) {
          if (label === 'json') {
            return new jsonWorkerModule.default();
          }
          if (label === 'css' || label === 'scss' || label === 'less') {
            return new cssWorkerModule.default();
          }
          if (label === 'html' || label === 'handlebars' || label === 'razor') {
            return new htmlWorkerModule.default();
          }
          return new editorWorkerModule.default();
        }
      };

      loaderInstance.config({ monaco });
    })();
  }
  return monacoSetupPromise;
}
