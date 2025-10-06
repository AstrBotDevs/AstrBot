<template>
  <div class="welcome-container fade-in">
    <div class="welcome-title">
      <span>Hello, I'm</span>
      <span class="bot-name">AstrBot ⭐</span>
    </div>
    <div class="welcome-hint markdown-content">
      <span>{{ t('core.common.type') }}</span>
      <code>help</code>
      <span>{{ tm('shortcuts.help') }} 😊</span>
    </div>
    <div class="welcome-hint markdown-content">
      <span>{{ t('core.common.longPress') }}</span>
      <code>Ctrl + B</code>
      <span>{{ tm('shortcuts.voiceRecord') }} 🎤</span>
    </div>
    <div class="welcome-hint markdown-content">
      <span>{{ t('core.common.press') }}</span>
      <code>Ctrl + V</code>
      <span>{{ tm('shortcuts.pasteImage') }} 🏞️</span>
    </div>
  </div>
</template>

<script>
import { useI18n, useModuleI18n } from '@/i18n/composables';

export default {
  name: 'WelcomePanel',
  setup() {
    const { t } = useI18n();
    const { tm } = useModuleI18n('features/chat');
    return { t, tm };
  },
};
</script>
