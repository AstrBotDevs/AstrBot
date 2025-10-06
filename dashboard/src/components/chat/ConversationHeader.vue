<template>
  <div class="conversation-header fade-in">
    <div v-if="currCid">
      <h3 style="max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
        {{ title || tm('conversation.newConversation') }}
      </h3>
      <span style="font-size: 12px;">{{ formatDate(updatedAt) }}</span>
    </div>
    <div class="conversation-header-actions">
      <!-- router 推送到 /chatbox -->
      <v-tooltip :text="tm('actions.fullscreen')" v-if="!chatboxMode">
        <template #activator="{ props }">
          <v-icon v-bind="props" class="fullscreen-icon" @click="$emit('fullscreen')">mdi-fullscreen</v-icon>
        </template>
      </v-tooltip>
      <!-- 语言切换按钮 -->
      <v-tooltip :text="t('core.common.language')" v-if="chatboxMode">
        <template #activator="{ props }">
          <LanguageSwitcher variant="chatbox" />
        </template>
      </v-tooltip>
      <!-- 主题切换按钮 -->
      <v-tooltip :text="isDark ? tm('modes.lightMode') : tm('modes.darkMode')" v-if="chatboxMode">
        <template #activator="{ props }">
          <v-btn v-bind="props" icon @click="$emit('toggle-theme')" class="theme-toggle-icon" size="small" rounded="sm" style="margin-right: 8px;" variant="text">
            <v-icon>{{ isDark ? 'mdi-weather-night' : 'mdi-white-balance-sunny' }}</v-icon>
          </v-btn>
        </template>
      </v-tooltip>
      <!-- router 推送到 /chat -->
      <v-tooltip :text="tm('actions.exitFullscreen')" v-if="chatboxMode">
        <template #activator="{ props }">
          <v-icon v-bind="props" class="fullscreen-icon" @click="$emit('exit-fullscreen')">mdi-fullscreen-exit</v-icon>
        </template>
      </v-tooltip>
    </div>
  </div>
</template>

<script>
import { useI18n, useModuleI18n } from '@/i18n/composables';
import LanguageSwitcher from '@/components/shared/LanguageSwitcher.vue';
import { formatTimestampSeconds } from '@/composables/chat/useDateFormat';

export default {
  name: 'ConversationHeader',
  components: { LanguageSwitcher },
  props: {
    chatboxMode: { type: Boolean, default: false },
    currCid: { type: String, default: '' },
    isDark: { type: Boolean, default: false },
    title: { type: String, default: '' },
    updatedAt: { type: Number, default: 0 },
  },
  emits: ['toggle-theme', 'fullscreen', 'exit-fullscreen'],
  setup() {
    const { t } = useI18n();
    const { tm } = useModuleI18n('features/chat');
    return { t, tm };
  },
  methods: {
    formatDate(timestamp) {
      const locale = this.t('core.common.locale') || 'zh-CN';
      return formatTimestampSeconds(timestamp, locale);
    },
  },
};
</script>
