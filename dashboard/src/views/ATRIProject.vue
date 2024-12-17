<script setup>
</script>


<template>
  <v-alert style="margin-bottom: 16px"
    text="这是一个长期实验性功能，目标是实现更具人类机能的 LLM 对话。推荐使用 gpt-4o-mini 作为文本生成和视觉理解模型，成本很低。推荐使用 text-embedding-3-small 作为 Embedding 模型，成本忽略不计。"
    title="💡实验性功能" type="info" variant="tonal">
  </v-alert>
  <v-card>
    <v-card-text>
      <v-container fluid>
        <AstrBotConfig :metadata="project_atri_config_metadata" :iterable="project_atri_config?.project_atri"
          metadataKey="project_atri">
        </AstrBotConfig>
      </v-container>
    </v-card-text>
  </v-card>

  <v-btn icon="mdi-content-save" size="x-large" style="position: fixed; right: 52px; bottom: 52px;" color="darkprimary"
    @click="updateConfig">
  </v-btn>
  <v-snackbar :timeout="3000" elevation="24" :color="save_message_success" v-model="save_message_snack">
    {{ save_message }}
  </v-snackbar>
  <WaitingForRestart ref="wfr"></WaitingForRestart>
</template>

<script>
import axios from 'axios';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue';
export default {
  name: 'AtriProject',
  components: {
    AstrBotConfig,
    WaitingForRestart
  },
  data() {
    return {
      project_atri_config: {},
      fetched: false,
      project_atri_config_metadata: {},
      save_message_snack: false,
      save_message: "",
      save_message_success: "",
    }
  },
  mounted() {
    this.getConfig();
  },
  methods: {
    getConfig() {
      // 获取配置
      axios.get('/api/config/get').then((res) => {
        this.project_atri_config = res.data.data.config;
        this.fetched = true
        this.project_atri_config_metadata = res.data.data.metadata;
      }).catch((err) => {
        save_message = err;
        save_message_snack = true;
        save_message_success = "error";
      });
    },
    updateConfig() {
      if (!this.fetched) return;
      axios.post('/api/config/astrbot/update', this.project_atri_config).then((res) => {
        if (res.data.status === "ok") {
          this.save_message = res.data.message;
          this.save_message_snack = true;
          this.save_message_success = "success";
          this.$refs.wfr.check();
        } else {
          this.save_message = res.data.message;
          this.save_message_snack = true;
          this.save_message_success = "error";
        }
      }).catch((err) => {
        this.save_message = err;
        this.save_message_snack = true;
        this.save_message_success = "error";
      });
    },
  },
}

</script>