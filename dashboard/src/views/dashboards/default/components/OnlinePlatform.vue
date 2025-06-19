<template>
  <v-card elevation="1" class="stat-card platform-card">
    <v-card-text>
      <div class="d-flex align-start">
        <div class="icon-wrapper">
          <v-icon icon="mdi-server-network" size="24"></v-icon>
        </div>
        
        <div class="stat-content">
          <div class="stat-title">{{ t('stats.onlinePlatform.title') }}</div>
          <div class="stat-value-wrapper">
            <h2 class="stat-value">{{ stat.platform_count || 0 }}</h2>
          </div>
          <div class="stat-subtitle">{{ t('stats.onlinePlatform.subtitle') }}</div>
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>

<script>
import { useModuleI18n } from '@/i18n/composables';

export default {
  name: 'OnlinePlatform',
  props: ['stat'],
  setup() {
    const { tm: t } = useModuleI18n('features/dashboard');
    return { t };
  }
};
</script>

<style scoped>
.stat-card {
  height: 100%;
  transition: transform 0.2s, box-shadow 0.2s;
  overflow: hidden;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08) !important;
}

.platform-card {
  background-color: #2196f3;
  color: white;
}

.icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 8px;
  margin-right: 16px;
  background: rgba(255, 255, 255, 0.2);
}

.stat-content {
  flex: 1;
}

.stat-title {
  font-size: 14px;
  font-weight: 500;
  opacity: 0.9;
  margin-bottom: 4px;
}

.stat-value-wrapper {
  display: flex;
  align-items: baseline;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 32px;
  font-weight: 600;
  line-height: 1.2;
  margin-right: 8px;
}

.stat-subtitle {
  font-size: 12px;
  opacity: 0.7;
}
</style>