---
search: false
---

<script setup>
import { onMounted } from 'vue';
import { withBase } from 'vitepress';

const destinations = {
  "registration-and-creation": "chat-message.html#register-and-create-the-component",
  "choosing-the-host": "index.html",
  "frontend": "chat-message.html#frontend",
  "interaction-contract": "chat-message.html#interaction-contract",
  "persistence-and-boundaries": "chat-message.html#persistence-and-boundaries",
  "workbench-and-launcher-views": "workbench.html",
  "fill-or-send-a-chat-message-from-a-resident-view": "workbench.html#fill-or-send-a-chat-message-from-a-resident-view",
  "local-preference-storage": "workbench.html#local-preference-storage"
};
onMounted(() => {
  const anchor = decodeURIComponent(window.location.hash.slice(1));
  window.location.replace(withBase("/en/dev/star/guides/plugin-views/" + (destinations[anchor] || "chat-message.html")));
});
</script>

# Documentation moved

The content is now organized under [Plugin views](./plugin-views/index.md):

- [Standalone plugin page](./plugin-views/plugin-page.md)
- [Interactive message component](./plugin-views/chat-message.md)
- [Workbench page](./plugin-views/workbench.md)
- [Shared Bridge API](./plugin-views/bridge.md)
- [Backend Web APIs](./plugin-views/web-api.md)
