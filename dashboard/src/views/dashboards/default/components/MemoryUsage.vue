<template>
  <v-card elevation="1" class="stat-card memory-card">
    <v-card-text>
      <div class="d-flex align-start">
        <div class="icon-wrapper">
          <v-icon icon="mdi-memory" size="24"></v-icon>
        </div>
        
        <div class="stat-content">
          <div class="stat-title">{{ t('stats.memoryUsage.title') }}</div>
          <div class="stat-value-wrapper">
            <h2 class="stat-value">{{ stat.memory?.process || 0 }} <span class="memory-unit">MiB / {{ stat.memory?.system || 0 }} MiB</span></h2>
            <v-chip :color="memoryStatus.color" size="x-small" class="status-chip">
              {{ memoryStatus.label }}
            </v-chip>
          </div>
        </div>
      </div>
      
      <div class="metrics-container">
        <div class="metric-item">
          <div class="metric-label">{{ t('stats.memoryUsage.cpuLoad') }}</div>
          <div class="metric-value">{{ stat.cpu_percent || '0' }}%</div>
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>

<script>
import { useModuleI18n } from '@/i18n/composables';

export default {
  name: 'MemoryUsage',
  props: ['stat'],
  setup() {
    const { tm: t } = useModuleI18n('features/dashboard');
    return { t };
  },
  computed: {
    memoryPercentage() {
      if (!this.stat.memory || !this.stat.memory.process || !this.stat.memory.system) return 0;
      return Math.round((this.stat.memory.process / this.stat.memory.system) * 100);
    },
    memoryStatus() {
      const percentage = this.memoryPercentage;
      if (percentage < 30) {
        return { color: 'success', label: this.t('stats.memoryUsage.status.good') };
      } else if (percentage < 70) {
        return { color: 'warning', label: this.t('stats.memoryUsage.status.normal') };
      } else {
        return { color: 'error', label: this.t('stats.memoryUsage.status.high') };
      }
    }
  }
};
</script>

<style scoped>
.stat-card {
  height: 100%;
  border-radius: 8px;
  transition: transform 0.2s, box-shadow 0.2s;
  overflow: hidden;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08) !important;
}

.memory-card {
  background-color: #ff9800;
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
  justify-content: space-between;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  line-height: 1.2;
}

.memory-unit {
  font-size: 14px;
  font-weight: 400;
  opacity: 0.8;
}

.status-chip {
  font-weight: 500;
}

.metrics-container {
  display: flex;
  background-color: rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  padding: 4px;
  margin-top: 4px;
  justify-content: center;
}

.metric-item {
  flex: 1;
  text-align: center;
}

.metric-label {
  font-size: 12px;
  opacity: 0.7;
  margin-bottom: 4px;
}

.metric-value {
  font-size: 14px;
  font-weight: 600;
}
</style>
