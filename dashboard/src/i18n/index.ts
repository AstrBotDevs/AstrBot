import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN.json'
import enUS from './locales/en-US.json'

// 从localStorage获取用户选择的语言，默认为中文
const savedLocale = localStorage.getItem('locale') || 'zh-CN'

// 创建i18n实例
const i18n = createI18n({
  legacy: false, // 使用Composition API模式
  locale: savedLocale, // 设置地区
  fallbackLocale: 'zh-CN', // 设置备用语言
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS
  },
  globalInjection: true // 全局注入
})

export default i18n 