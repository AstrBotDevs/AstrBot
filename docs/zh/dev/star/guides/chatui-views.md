---
search: false
---

<script setup>
import { onMounted } from 'vue';
import { withBase } from 'vitepress';

const destinations = {
  "注册与创建": "chat-message.html#注册并创建组件",
  "选择展示位置": "index.html",
  "前端": "chat-message.html#前端",
  "交互数据与回复": "chat-message.html#交互数据与回复",
  "历史、并发与限制": "chat-message.html#历史、并发与限制",
  "工作台与常驻视图": "workbench.html",
  "从常驻视图填入或发送消息": "workbench.html#从常驻视图填入或发送消息",
  "本地偏好存储": "workbench.html#本地偏好存储"
};
onMounted(() => {
  const anchor = decodeURIComponent(window.location.hash.slice(1));
  window.location.replace(withBase("/dev/star/guides/plugin-views/" + (destinations[anchor] || "chat-message.html")));
});
</script>

# 文档已调整

内容已按使用场景整理到[插件可视化视图](./plugin-views/index.md)：

- [独立插件页面](./plugin-views/plugin-page.md)
- [消息交互组件](./plugin-views/chat-message.md)
- [工作台页面](./plugin-views/workbench.md)
- [共享 Bridge API](./plugin-views/bridge.md)
- [后端 Web API](./plugin-views/web-api.md)
