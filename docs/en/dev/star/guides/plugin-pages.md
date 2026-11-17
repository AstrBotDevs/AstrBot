---
search: false
---

<script setup>
import { onMounted } from 'vue';
import { withBase } from 'vitepress';

const destinations = {
  "directory-layout": "plugin-page.html#directory-layout",
  "development-flow": "plugin-page.html#register-the-page",
  "minimal-complete-example": "plugin-page.html#register-the-page",
  "backend": "plugin-page.html#register-the-page",
  "frontend": "plugin-page.html#frontend",
  "backend-web-apis": "web-api.html#backend-web-apis",
  "route-registration": "web-api.html#route-registration",
  "request-object": "web-api.html#request-object",
  "responses": "web-api.html#responses",
  "quart-compatibility": "web-api.html#quart-compatibility",
  "bridge-api": "bridge.html#bridge-api",
  "context": "bridge.html#context",
  "request-and-return-rules": "bridge.html#request-and-return-rules",
  "apiget-endpoint-params": "bridge.html#apiget-endpoint-params",
  "apipost-endpoint-body": "bridge.html#apipost-endpoint-body",
  "upload-endpoint-file": "bridge.html#upload-endpoint-file",
  "download-endpoint-params-filename": "bridge.html#download-endpoint-params-filename",
  "subscribesse-endpoint-handlers-params": "bridge.html#subscribesse-endpoint-handlers-params",
  "view-metadata-and-internationalization": "bridge.html#view-metadata-and-internationalization",
  "light-dark-theme": "bridge.html#light-dark-theme",
  "following-user-selected-colors": "bridge.html#following-user-selected-colors",
  "static-asset-paths": "bridge.html#static-asset-paths",
  "security-constraints": "bridge.html#security-constraints",
  "debugging-tips": "bridge.html#debugging-tips"
};
onMounted(() => {
  const anchor = decodeURIComponent(window.location.hash.slice(1));
  window.location.replace(withBase("/en/dev/star/guides/plugin-views/" + (destinations[anchor] || "plugin-page.html")));
});
</script>

# Documentation moved

The content is now organized under [Plugin views](./plugin-views/index.md):

- [Standalone plugin page](./plugin-views/plugin-page.md)
- [Interactive message component](./plugin-views/chat-message.md)
- [Workbench page](./plugin-views/workbench.md)
- [Shared Bridge API](./plugin-views/bridge.md)
- [Backend Web APIs](./plugin-views/web-api.md)
