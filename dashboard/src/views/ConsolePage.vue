<script setup>
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';
import axios from 'axios';

</script>

<template>
  <div style="height: 100%;">
    <div
      style="background-color: white; padding: 8px; padding-left: 16px; border-radius: 8px; margin-bottom: 16px; display: flex; flex-direction: row; align-items: center; justify-content: space-between;">
      <h4>控制台</h4>
      <div class="d-flex align-center">
        <v-switch
          v-model="autoScrollDisabled"
          :label="autoScrollDisabled ? '自动滚动已关闭' : '自动滚动已开启'"
          hide-details
          density="compact"
          style="margin-right: 16px;"
        ></v-switch>
        <v-dialog v-model="pipDialog" width="400">
          <template v-slot:activator="{ props }">
            <v-btn variant="plain" v-bind="props">安装 pip 库</v-btn>
          </template>
          <v-card>
            <v-card-title>
              <span class="text-h5">安装 Pip 库</span>
            </v-card-title>
            <v-card-text>
              <v-text-field v-model="pipInstallPayload.package" label="*库名，如 llmtuner" variant="outlined"></v-text-field>
              <v-text-field v-model="pipInstallPayload.mirror" label="强制 PyPI 软件仓库链接（可选）" variant="outlined"></v-text-field>
              <small>强制 PyPI 软件仓库链接 > 配置项 `PyPI 软件仓库地址`</small>
              <div>
                <small>{{ status }}</small>
              </div>
              
            </v-card-text>
            <v-card-actions>
              <v-spacer></v-spacer>
              <v-btn color="blue-darken-1" variant="text" @click="pipInstall" :loading="loading">
                安装
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