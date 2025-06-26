<template>
  <v-menu offset="12" location="bottom center">
    <template v-slot:activator="{ props: activatorProps }">
      <v-btn
        v-bind="activatorProps"
        :variant="(props.variant === 'header' || props.variant === 'chatbox') ? 'flat' : 'text'"
        :color="(props.variant === 'header' || props.variant === 'chatbox') ? 'var(--v-theme-surface)' : undefined"
        :rounded="(props.variant === 'header' || props.variant === 'chatbox') ? 'sm' : undefined"
        icon
        size="small"
        :class="['language-switcher', `language-switcher--${props.variant}`, (props.variant === 'header' || props.variant === 'chatbox') ? 'action-btn' : '']"
      >
        <v-icon 
          size="18"
          :color="props.variant === 'default' ? (useCustomizerStore().uiTheme === 'PurpleTheme' ? '#5e35b1' : '#d7c5fa') : undefined"
        >
          mdi-translate
        </v-icon>
        <v-tooltip activator="parent" location="top">
          {{ t('core.common.language') }}
        </v-tooltip>
      </v-btn>
    </template>
    
    <v-card class="language-dropdown" elevation="8" rounded="lg">
      <v-list density="compact" class="pa-1">
        <v-list-item
          v-for="lang in languages"
          :key="lang.code"
          :value="lang.code"
          @click="changeLanguage(lang.code)"
          :class="{ 'v-list-item--active': currentLocale === lang.code, 'language-item-selected': currentLocale === lang.code }"
          class="language-item"
          rounded="md"
        >
          <template v-slot:prepend>
            <span class="language-flag">{{ lang.flag }}</span>
          </template>
          <v-list-item-title>{{ lang.name }}</v-list-item-title>
        </v-list-item>
      </v-list>
    </v-card>
  </v-menu>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n, useLanguageSwitcher } from '@/i18n/composables'
import { useCustomizerStore } from '@/stores/customizer'
import type { Locale } from '@/i18n/types'

// 定义props来控制样式变体
const props = withDefaults(defineProps<{
  variant?: 'default' | 'header' | 'chatbox'
}>(), {
  variant: 'default'
})

// 使用新的i18n系统
const { t } = useI18n()
const { languageOptions, currentLanguage, switchLanguage, locale } = useLanguageSwitcher()

const languages = computed(() => 
  languageOptions.value.map(lang => ({
    code: lang.value,
    name: lang.label,
    flag: lang.flag
  }))
)

const currentLocale = computed(() => locale.value)

const changeLanguage = async (langCode: string) => {
  await switchLanguage(langCode as Locale)
}
</script>

<style scoped>
.language-flag {
  font-size: 16px;
  margin-right: 8px;
}

/* 默认变体样式 - 圆形按钮用于登录页 */
.language-switcher--default {
  margin: 0 4px;
  transition: all 0.3s ease;
  border-radius: 50% !important;
  min-width: 32px !important;
  width: 32px !important;
  height: 32px !important;
}

.language-switcher--default:hover {
  transform: scale(1.05);
  background: rgba(94, 53, 177, 0.08) !important;
}

/* Header变体样式 - 完全继承Vuetify和action-btn的默认样式 */
.language-switcher--header {
  /* action-btn类已经处理了margin-right: 6px，不需要额外样式 */
}

/* ChatBox变体样式 - 与Header保持一致 */
.language-switcher--chatbox {
  /* 继承action-btn样式，与工具栏主题按钮保持一致 */
}

/* 深色模式下的悬停效果（仅对default变体） */
:deep(.v-theme--PurpleThemeDark) .language-switcher--default:hover {
  background: rgba(114, 46, 209, 0.12) !important;
}

.language-dropdown {
  min-width: 100px;
  width: fit-content;
  border: 1px solid rgba(94, 53, 177, 0.15) !important;
  background: #f8f6fc !important;
  backdrop-filter: blur(10px);
}

/* 深色模式下的下拉框样式 */
:deep(.v-theme--PurpleThemeDark) .language-dropdown {
  background: #2a2733 !important;
  border: 1px solid rgba(110, 60, 180, 0.692) !important;
}

.language-item {
  margin: 2px 0;
  transition: all 0.2s ease;
}

.language-item:hover {
  background: rgba(94, 53, 177, 0.08) !important;
}

.language-item-selected {
  background: rgba(94, 53, 177, 0.15) !important;
  font-weight: 500;
}

.language-item-selected:hover {
  background: rgba(94, 53, 177, 0.2) !important;
}

/* 深色模式下的列表项悬停效果 */
:deep(.v-theme--PurpleThemeDark) .language-item:hover {
  background: rgba(114, 46, 209, 0.12) !important;
}

:deep(.v-theme--PurpleThemeDark) .language-item-selected {
  background: rgba(114, 46, 209, 0.2) !important;
}

:deep(.v-theme--PurpleThemeDark) .language-item-selected:hover {
  background: rgba(114, 46, 209, 0.25) !important;
}
</style> 