<template>
  <v-menu>
    <template v-slot:activator="{ props }">
      <v-btn
        v-bind="props"
        variant="text"
        icon
        size="small"
        class="language-switcher"
      >
        <v-icon>mdi-translate</v-icon>
        <v-tooltip activator="parent" location="bottom">
          {{ $t('common.language') }}
        </v-tooltip>
      </v-btn>
    </template>
    
    <v-list density="compact" min-width="140">
      <v-list-item
        v-for="lang in languages"
        :key="lang.code"
        :value="lang.code"
        @click="changeLanguage(lang.code)"
        :class="{ 'v-list-item--active': currentLocale === lang.code }"
      >
        <template v-slot:prepend>
          <span class="language-flag">{{ lang.flag }}</span>
        </template>
        <v-list-item-title>{{ lang.name }}</v-list-item-title>
        <template v-slot:append v-if="currentLocale === lang.code">
          <v-icon color="primary" size="small">mdi-check</v-icon>
        </template>
      </v-list-item>
    </v-list>
  </v-menu>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { locale } = useI18n()

const languages = [
  { code: 'zh-CN', name: '简体中文', flag: '🇨🇳' },
  { code: 'en-US', name: 'English', flag: '🇺🇸' }
]

const currentLocale = computed(() => locale.value)

const changeLanguage = (langCode: string) => {
  locale.value = langCode
  localStorage.setItem('locale', langCode)
  
  // 可选：刷新页面以确保所有文本都更新
  // window.location.reload()
}
</script>

<style scoped>
.language-flag {
  font-size: 16px;
  margin-right: 8px;
}

.language-switcher {
  margin: 0 4px;
}
</style> 