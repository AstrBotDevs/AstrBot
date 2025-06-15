<template>
  <div style="background-color: var(--v-theme-surface, #fff); padding: 8px; padding-left: 16px; border-radius: 8px; margin-bottom: 16px;">
    <v-list lines="two">
      <v-list-subheader>{{ t('settings.sections.network') }}</v-list-subheader>

      <v-list-item :subtitle="t('settings.network.githubProxyDesc')" :title="t('settings.network.githubProxy')">
        <v-combobox 
          variant="outlined" 
          style="width: 100%; margin-top: 16px;" 
          v-model="selectedGitHubProxy" 
          :items="githubProxies"
          :label="t('settings.network.selectGithubProxy')"
        />
      </v-list-item>

      <v-list-subheader>{{ t('settings.sections.system') }}</v-list-subheader>

      <v-list-item :subtitle="t('settings.system.restartDesc')" :title="t('settings.system.restart')">
        <v-btn style="margin-top: 16px;" color="error" @click="restartAstrBot">
          {{ t('settings.system.restartButton') }}
        </v-btn>
      </v-list-item>

      <v-list-subheader>{{ t('settings.sections.internationalization') }}</v-list-subheader>

      <v-list-item :subtitle="t('settings.i18n.desc')" :title="t('settings.i18n.title')">
        <div style="margin-top: 16px; width: 100%;">
          <div class="mb-3">
            <span class="text-body-2 text-medium-emphasis">{{ t('settings.i18n.currentLanguage') }}: </span>
            <v-chip size="small" color="primary" variant="flat">
              {{ t(`language.${locale}`) }}
            </v-chip>
          </div>
          
          <v-select
            v-model="locale"
            :items="languages"
            item-title="label"
            item-value="value"
            variant="outlined"
            density="comfortable"
            :label="t('settings.i18n.selectLanguage')"
            @update:model-value="changeLanguage"
            style="max-width: 300px;"
          >
            <template #selection="{ item }">
              <div class="d-flex align-center">
                <v-icon class="me-2">mdi-translate</v-icon>
                {{ item.raw.label }}
              </div>
            </template>
            <template #item="{ props, item }">
              <v-list-item v-bind="props" :title="item.raw.label">
                <template #prepend>
                  <v-icon>mdi-translate</v-icon>
                </template>
              </v-list-item>
            </template>
          </v-select>
        </div>
      </v-list-item>
    </v-list>
  </div>

  <WaitingForRestart ref="wfr"></WaitingForRestart>
</template>

<script>
import axios from 'axios';
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue';
import { useI18n } from 'vue-i18n';

export default {
  components: {
    WaitingForRestart,
  },
  setup() {
    const { t, locale } = useI18n();
    return { t, locale };
  },
  data() {
    return {
      githubProxies: [
        "https://gh.llkk.cc",
        "https://gitproxy.click",
      ],
      selectedGitHubProxy: "",
      languages: [
        { value: 'zh-CN', label: '简体中文' },
        { value: 'en-US', label: 'English' }
      ]
    }
  },
  methods: {
    restartAstrBot() {
      axios.post('/api/stat/restart-core').then(() => {
        this.$refs.wfr.check();
      })
    },
    changeLanguage(lang) {
      this.locale = lang;
      localStorage.setItem('preferred-language', lang);
    }
  },
  mounted() {
    this.selectedGitHubProxy = localStorage.getItem('selectedGitHubProxy') || "";
    
    // 从本地存储恢复语言设置
    const savedLang = localStorage.getItem('preferred-language');
    if (savedLang && this.languages.some(lang => lang.value === savedLang)) {
      this.locale = savedLang;
    }
  },
  watch: {
    selectedGitHubProxy: function (newVal, oldVal) {
      if (!newVal) {
        newVal = ""
      }
      localStorage.setItem('selectedGitHubProxy', newVal);
    }
  }
}
</script>