<template>
  <RouterView></RouterView>
</template>

<script setup lang="ts">
import { RouterView } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { onMounted } from 'vue';

const { locale } = useI18n();

onMounted(() => {
  const savedLanguage = localStorage.getItem('preferred-language');
  const supportedLanguages = ['zh-CN', 'en-US'];
  
  if (savedLanguage && supportedLanguages.includes(savedLanguage)) {
    locale.value = savedLanguage;
  } else {
    const browserLanguage = navigator.language || navigator.languages?.[0] || 'zh-CN';
    const matchedLanguage = supportedLanguages.find(lang => 
      browserLanguage.startsWith(lang) || browserLanguage.startsWith(lang.split('-')[0])
    );
    locale.value = matchedLanguage || 'zh-CN';
    localStorage.setItem('preferred-language', locale.value);
  }
});
</script>
