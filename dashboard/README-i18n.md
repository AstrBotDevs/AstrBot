# 多语言国际化使用指南

本项目已集成Vue I18n国际化支持，目前支持中文(zh-CN)和英文(en-US)两种语言。

## 快速开始

### 1. 安装依赖

```bash
npm install vue-i18n@^9.8.0
```

### 2. 项目结构

```
src/
├── i18n/
│   ├── index.ts              # i18n配置入口
│   └── locales/
│       ├── zh-CN.json        # 中文语言文件
│       └── en-US.json        # 英文语言文件
├── components/
│   └── shared/
│       └── LanguageSwitcher.vue  # 语言切换组件
```

## 使用方法

### 在Vue组件中使用

#### 1. 在模板中使用

```vue
<template>
  <div>
    <!-- 使用$t()函数翻译文本 -->
    <h1>{{ $t('common.save') }}</h1>
    <p>{{ $t('extension.title') }}</p>
    
    <!-- 带参数的翻译 -->
    <p>{{ $t('provider.openaiDescription', { type: 'OpenAI' }) }}</p>
  </div>
</template>
```

#### 2. 在脚本中使用 (Composition API)

```vue
<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t, locale } = useI18n()

// 使用翻译函数
const title = t('extension.title')

// 切换语言
const changeLanguage = (lang: string) => {
  locale.value = lang
  localStorage.setItem('locale', lang)
}
</script>
```

#### 3. 在脚本中使用 (Options API)

```vue
<script>
export default {
  mounted() {
    // 使用this.$t()翻译
    console.log(this.$t('common.loading'))
  },
  methods: {
    showMessage() {
      const message = this.$t('common.success')
      // 使用翻译后的文本
    }
  }
}
</script>
```

## 语言文件结构

### 中文 (zh-CN.json)
```json
{
  "sidebar": {
    "dashboard": "统计",
    "extension": "插件管理"
  },
  "common": {
    "save": "保存",
    "cancel": "取消"
  }
}
```

### 英文 (en-US.json)
```json
{
  "sidebar": {
    "dashboard": "Dashboard", 
    "extension": "Extensions"
  },
  "common": {
    "save": "Save",
    "cancel": "Cancel"
  }
}
```

## 添加新语言

### 1. 创建新的语言文件

在 `src/i18n/locales/` 目录下创建新的语言文件，如 `ja-JP.json`：

```json
{
  "sidebar": {
    "dashboard": "ダッシュボード",
    "extension": "拡張機能"
  }
}
```

### 2. 在i18n配置中注册

在 `src/i18n/index.ts` 中添加：

```typescript
import jaJP from './locales/ja-JP.json'

const i18n = createI18n({
  // ...其他配置
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS,
    'ja-JP': jaJP  // 添加日文
  }
})
```

### 3. 在语言切换器中添加选项

在 `LanguageSwitcher.vue` 中添加：

```typescript
const languages = [
  { code: 'zh-CN', name: '简体中文', flag: '🇨🇳' },
  { code: 'en-US', name: 'English', flag: '🇺🇸' },
  { code: 'ja-JP', name: '日本語', flag: '🇯🇵' }  // 添加日文选项
]
```

## 最佳实践

### 1. 命名规范

- 使用点号分隔的层级结构，如 `page.section.item`
- 通用文本放在 `common` 下
- 页面特定文本使用页面名作为顶级键

### 2. 占位符使用

对于需要动态内容的文本，使用占位符：

```json
{
  "message": "欢迎 {username}，您有 {count} 条新消息"
}
```

```vue
<template>
  <p>{{ $t('message', { username: 'John', count: 5 }) }}</p>
</template>
```

### 3. 复数形式

Vue I18n支持复数形式：

```json
{
  "items": "没有项目 | 1个项目 | {count}个项目"
}
```

```vue
<template>
  <p>{{ $tc('items', count, { count }) }}</p>
</template>
```

## 语言切换器

项目已包含一个语言切换器组件 `LanguageSwitcher.vue`，位于顶部导航栏。用户可以通过点击翻译图标来切换语言，选择的语言会保存在localStorage中。

## 注意事项

1. 确保所有支持的语言都有相应的翻译文本
2. 新增文本时，记得在所有语言文件中添加对应的翻译
3. 语言切换后，某些组件可能需要重新加载才能完全更新
4. 建议在开发时优先完善中文翻译，然后再添加其他语言

## 贡献翻译

欢迎提交其他语言的翻译！请按照现有的文件结构创建新的语言文件，并确保翻译的准确性和一致性。 