<script setup>
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';
import { useModuleI18n } from '@/i18n/composables';
import axios from 'axios';

const { tm } = useModuleI18n('features/console');
</script>

<template>
  <div style="height: 100%;">
    <div
      style="background-color: var(--v-theme-surface); padding: 8px; padding-left: 16px; border-radius: 8px; margin-bottom: 16px; display: flex; flex-direction: row; align-items: center; justify-content: space-between;">
      <div>
        <h4>{{ tm('title') }}</h4>
        <v-alert
          type="info"
          variant="tonal"
          density="compact"
          class="mt-2"
          style="max-width: 600px;"
        >
          {{ tm('debugHint.text') }}
        </v-alert>
      </div>
      <div class="d-flex align-center">
        <v-switch
          v-model="autoScrollEnabled"
          :label="autoScrollEnabled ? tm('autoScroll.enabled') : tm('autoScroll.disabled')"
          hide-details
          density="compact"
          color="primary"
          style="margin-right: 16px;"
        ></v-switch>
        <v-select
          :model-value="logLangLocale"
          :items="logLanguageItems"
          :label="tm('loggingLocalization.button')"
          hide-details
          density="compact"
          rounded="md"
          variant="outlined"
          style="max-width: 200px; margin-right: 16px;"
          @update:model-value="setLogLanguage"
        />
        <v-dialog v-model="pipDialog" width="400">
          <template v-slot:activator="{ props }">
            <v-btn variant="plain" v-bind="props">{{ tm('pipInstall.button') }}</v-btn>
          </template>
          <v-card>
            <v-card-title>
              <span class="text-h5">{{ tm('pipInstall.dialogTitle') }}</span>
            </v-card-title>
            <v-card-text>
              <v-text-field v-model="pipInstallPayload.package" :label="tm('pipInstall.packageLabel')" variant="outlined"></v-text-field>
              <v-text-field v-model="pipInstallPayload.mirror" :label="tm('pipInstall.mirrorLabel')" variant="outlined"></v-text-field>
              <small>{{ tm('pipInstall.mirrorHint') }}</small>
              <div>
                <small>{{ status }}</small>
              </div>
              
            </v-card-text>
            <v-card-actions>
              <v-spacer></v-spacer>
              <v-btn color="blue-darken-1" variant="text" @click="pipInstall" :loading="loading">
                {{ tm('pipInstall.installButton') }}
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>
      </div>
    </div>
    <ConsoleDisplayer ref="consoleDisplayer" style="height: calc(100vh - 220px); " />
  </div>
</template>
<script>
export default {
  name: 'ConsolePage',
  components: {
    ConsoleDisplayer
  },
  data() {
    return {
      autoScrollEnabled: true,
      logLangLocale: localStorage.getItem('logLangLocale') || 'zh-CN',
      logLanguageItems: [
        { value: 'zh-CN', title: '🇨🇳 简体中文' },
        { value: 'en-US', title: '🇺🇸 English' },
      ],
      pipDialog: false,
      pipInstallPayload: {
        package: '',
        mirror: ''
      },
      loading: false,
      status: ''
    }
  },
  watch: {
    autoScrollEnabled(val) {
      if (this.$refs.consoleDisplayer) {
        this.$refs.consoleDisplayer.autoScroll = val;
      }
    }
  },
  methods: {
    pipInstall() {
      this.loading = true;
      axios.post('/api/update/pip-install', this.pipInstallPayload)
        .then(res => {
          this.status = res.data.message;
          setTimeout(() => {
            this.status = '';
            this.pipDialog = false;
          }, 2000);
        })
        .catch(err => {
          this.status = err.response.data.message;
        }).finally(() => {
          this.loading = false;
        });
    },

    async setLogLanguage(langLocale) {
      if (!langLocale || langLocale === this.logLangLocale) return;

      const previousLocale = this.logLangLocale;
      this.logLangLocale = langLocale;

      try {
        const response = await axios.post('/api/setLang', { lang: langLocale });
        const ok =
          response?.data?.status ? response.data.status === 'ok' :
          response?.data?.code ? response.data.code === 200 :
          true;

        if (ok) {
          localStorage.setItem('logLangLocale', langLocale);
        } else {
          console.error('Failed to set language on server:', response?.data?.message);
          this.logLangLocale = previousLocale;
        }
      } catch (error) {
        console.error('Error setting language on server:', error);
        this.logLangLocale = previousLocale;
      }
    }
  }
}

</script>

<style>
@keyframes fadeIn {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}

.fade-in {
  animation: fadeIn 0.2s ease-in-out;
}
</style>
