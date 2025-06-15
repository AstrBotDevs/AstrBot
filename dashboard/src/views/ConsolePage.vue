<script setup>
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';
import axios from 'axios';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
</script>

<template>
  <div style="height: 100%;">
    <div
      style="background-color: var(--v-theme-surface); padding: 8px; padding-left: 16px; border-radius: 8px; margin-bottom: 16px; display: flex; flex-direction: row; align-items: center; justify-content: space-between;">
      <h4>{{ t('console.title') }}</h4>
      <div class="d-flex align-center">
        <v-switch
          v-model="autoScrollDisabled"
          :label="autoScrollDisabled ? t('console.autoScroll.disabled') : t('console.autoScroll.enabled')"
          hide-details
          density="compact"
          style="margin-right: 16px;"
        ></v-switch>
        <v-dialog v-model="pipDialog" width="400">
          <template v-slot:activator="{ props }">
            <v-btn variant="plain" v-bind="props">{{ t('console.pip.install') }}</v-btn>
          </template>
          <v-card>
            <v-card-title>
              <span class="text-h5">{{ t('console.pip.install') }}</span>
            </v-card-title>
            <v-card-text>
              <v-text-field v-model="pipInstallPayload.package" :label="t('console.pip.packageName')" variant="outlined"></v-text-field>
              <v-text-field v-model="pipInstallPayload.mirror" :label="t('console.pip.mirror')" variant="outlined"></v-text-field>
              <small>{{ t('console.pip.mirrorHint') }}</small>
              <div>
                <small>{{ status }}</small>
              </div>
              
            </v-card-text>
            <v-card-actions>
              <v-spacer></v-spacer>
              <v-btn color="blue-darken-1" variant="text" @click="pipInstall" :loading="loading">
                {{ t('console.pip.installButton') }}
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
      autoScrollDisabled: false,
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
    autoScrollDisabled(val) {
      if (this.$refs.consoleDisplayer) {
        this.$refs.consoleDisplayer.autoScroll = !val;
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