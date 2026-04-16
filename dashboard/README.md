# AstrBot 管理面板

基于 [CodedThemes/Berry](https://codedthemes.com/item/berry-free-vuetify-vuejs-admin-template/) 模板开发。

技术栈：Vue 3、Vite、Vuetify 3。  
支持 Material Design 风格与 i18n 国际化。

测试框架采用 Node.js 内置的 `node:test`。

## 项目结构
```
dashboard
  src           # 源代码目录
    assets        # 静态资源文件
    components    # 页面级组件
    composables
    i18n          # 国际化配置
    layouts       # 页面布局
    plugins       # Vue 插件初始化逻辑
    router        # 路由定义
    scss          # SASS/SCSS样式文件
    stores        # Pinia 状态管理（localStorage 持久化）
    styles
    theme         # Vuetify 主题定制
    types         # TypeScript 类型声明
    utils
    views         # 视图页面
    App.vue       # 根组件
    main.ts       # 应用入口
  tests         # 测试代码目录
  index.html
  package.json
  pnpm-lock.yaml
  tsconfig.json
  tsconfig.vite-config.json
  vite.config.ts
```

## 环境变量

- `VITE_ASTRBOT_RELEASE_BASE_URL`（可选）
  - 默认值：`https://github.com/AstrBotDevs/AstrBot/releases`
  - 用途：管理面板内“更新到最新版本”外部跳转所使用的 release 基地址。集成方可按需覆盖（例如 Desktop 指向其自身发布页）。
  - 建议传入仓库的 `.../releases` 基地址（不带 `/latest`）。
