---
search: false
---

<script setup>
import { onMounted } from 'vue';
import { withBase } from 'vitepress';

const destinations = {
  "目录结构": "plugin-page.html#目录结构",
  "开发流程": "plugin-page.html#注册页面",
  "最小完整示例": "plugin-page.html#注册页面",
  "后端": "plugin-page.html#注册页面",
  "前端": "plugin-page.html#前端",
  "后端-web-api": "web-api.html#后端-web-api",
  "路由注册": "web-api.html#路由注册",
  "请求对象": "web-api.html#请求对象",
  "响应对象": "web-api.html#响应对象",
  "quart-兼容": "web-api.html#quart-兼容",
  "bridge-api": "bridge.html#bridge-api",
  "上下文": "bridge.html#上下文",
  "请求和返回值规则": "bridge.html#请求和返回值规则",
  "apiget-endpoint-params": "bridge.html#apiget-endpoint-params",
  "apipost-endpoint-body": "bridge.html#apipost-endpoint-body",
  "upload-endpoint-file": "bridge.html#upload-endpoint-file",
  "download-endpoint-params-filename": "bridge.html#download-endpoint-params-filename",
  "subscribesse-endpoint-handlers-params": "bridge.html#subscribesse-endpoint-handlers-params",
  "视图元数据与国际化": "bridge.html#视图元数据与国际化",
  "亮暗主题": "bridge.html#亮暗主题",
  "跟随用户配色": "bridge.html#跟随用户配色",
  "静态资源路径": "bridge.html#静态资源路径",
  "安全约束": "bridge.html#安全约束",
  "调试建议": "bridge.html#调试建议"
};
onMounted(() => {
  const anchor = decodeURIComponent(window.location.hash.slice(1));
  window.location.replace(withBase("/dev/star/guides/plugin-views/" + (destinations[anchor] || "plugin-page.html")));
});
</script>

# 文档已调整

内容已按使用场景整理到[插件可视化视图](./plugin-views/index.md)：

- [独立插件页面](./plugin-views/plugin-page.md)
- [消息交互组件](./plugin-views/chat-message.md)
- [工作台页面](./plugin-views/workbench.md)
- [共享 Bridge API](./plugin-views/bridge.md)
- [后端 Web API](./plugin-views/web-api.md)
