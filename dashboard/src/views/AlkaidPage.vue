<template>
  <v-card style="height: 100%; width: 100%;">
    <v-card-text class="pa-4" style="height: 100%;">
      <v-container fluid class="d-flex flex-column" style="height: 100%;">
        <div style="margin-bottom: 32px;">
          <h1 class="gradient-text">{{ t('alkaid.title') }}</h1>
          <small style="color: #a3a3a3;">{{ t('alkaid.subtitle') }}</small>
        </div>

        <div style="display: flex; gap: 8px; margin-bottom: 16px;">
          <v-btn size="large" :variant="isActive('knowledge-base') ? 'flat' : 'tonal'"
            :color="isActive('knowledge-base') ? '#9b72cb' : ''" rounded="lg" 
            @click="navigateTo('knowledge-base')">
            <v-icon start>mdi-text-box-search</v-icon>
            {{ t('alkaid.tabs.knowledgeBase') }}
          </v-btn>
          <v-btn size="large" :variant="isActive('long-term-memory') ? 'flat' : 'tonal'"
            :color="isActive('long-term-memory') ? '#9b72cb' : ''" rounded="lg"
            @click="navigateTo('long-term-memory')">
            <v-icon start>mdi-dots-hexagon</v-icon>
            {{ t('alkaid.tabs.longTermMemory') }}
          </v-btn>
          <v-btn size="large" :variant="isActive('other') ? 'flat' : 'tonal'"
            :color="isActive('other') ? '#9b72cb' : ''" rounded="lg" 
            @click="navigateTo('other')">
            <v-icon start>mdi-tools</v-icon>
            {{ t('alkaid.tabs.other') }}
          </v-btn>
        </div>

        <div id="sub-view" class="flex-grow-1" style="max-height: 100%;">
          <router-view></router-view>
        </div>
      </v-container>
    </v-card-text>
  </v-card>
</template>

<script>
import { useI18n } from 'vue-i18n';

export default {
  name: 'AlkaidPage',
  components: {},
  setup() {
    const { t } = useI18n();
    return { t };
  },
  data() {
    return {}
  },
  methods: {
    navigateTo(tab) {
      this.$router.push(`/alkaid/${tab}`);
    },
    isActive(tab) {
      return this.$route.path.includes(`/alkaid/${tab}`);
    }
  },
  mounted() {
    // 如果在根路径 /alkaid，默认跳转到知识库页面
    if (this.$route.path === '/alkaid') {
      this.navigateTo('knowledge-base');
    }
  }
}
</script>

<style scoped>
.gradient-text {
  background: linear-gradient(74deg, #2abfe1 0, #9b72cb 25%, #b55908 50%, #d93025 100%);

  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  font-weight: bold;
}

#subview {
  display: flex;
  flex-direction: column;
  flex-grow: 1;
  width: 100%;
  height: 100%;
}
</style>