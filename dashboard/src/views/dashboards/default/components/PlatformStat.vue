<template>
  <v-card elevation="1" class="platform-stat-card">
    <v-card-text>
      <div class="platform-header">
        <div>
          <div class="platform-title">{{ t('charts.platformStat.title') }}</div>
          <div class="platform-subtitle">{{ t('charts.platformStat.subtitle') }}</div>
        </div>
      </div>
      
      <v-divider class="my-3"></v-divider>
      
      <div v-if="platforms.length > 0" class="platform-list-container">
        <v-list class="platform-list" density="compact">
          <v-list-item
            v-for="(platform, i) in sortedPlatforms"
            :key="i"
            :value="platform"
            class="platform-item"
          >
            <template v-slot:prepend>
              <div class="platform-rank" :class="{'top-rank': i < 3}">{{ i + 1 }}</div>
            </template>
            
            <v-list-item-title class="platform-name">{{ platform.name }}</v-list-item-title>
            
            <template v-slot:append>
              <div class="platform-count">
                <span class="count-value">{{ platform.count }}</span>
                <span class="count-label">{{ t('charts.platformStat.messageUnit') }}</span>
              </div>
            </template>
          </v-list-item>
        </v-list>
        
        <div class="platform-stats-summary">
          <div class="platform-stat-item">
            <div class="stat-label">{{ t('charts.platformStat.platformCount') }}</div>
            <div class="stat-value">{{ platforms.length }}</div>
          </div>
          <v-divider vertical></v-divider>
          <div class="platform-stat-item">
            <div class="stat-label">{{ t('charts.platformStat.mostActive') }}</div>
            <div class="stat-value">{{ mostActivePlatform }}</div>
          </div>
          <v-divider vertical></v-divider>
          <div class="platform-stat-item">
            <div class="stat-label">{{ t('charts.platformStat.totalPercentage') }}</div>
            <div class="stat-value">{{ topPlatformPercentage }}%</div>
          </div>
        </div>
        
        <div class="platform-chart">
          <v-progress-linear
            v-for="(platform, i) in sortedPlatforms.slice(0, 5)"
            :key="i"
            :model-value="getPercentage(platform.count)"
            height="8"
            rounded
            class="platform-progress"
            :color="i === 0 ? 'primary' : i === 1 ? 'info' : i === 2 ? 'success' : 'grey-lighten-1'"
          ></v-progress-linear>
        </div>
      </div>
      
      <div v-else class="no-data">
        <v-icon icon="mdi-information-outline" size="40" color="grey-lighten-1"></v-icon>
        <div class="no-data-text">{{ t('charts.platformStat.noData') }}</div>
      </div>
    </v-card-text>
  </v-card>
</template>

<script>
import { useModuleI18n } from '@/i18n/composables';

export default {
  name: 'PlatformStat',
  props: ['stat'],
  setup() {
    const { tm: t } = useModuleI18n('features/dashboard');
    return { t };
  },
  data() {
    return {
      platforms: []
    };
  },
  computed: {
    sortedPlatforms() {
      return [...this.platforms].sort((a, b) => b.count - a.count);
    },
    totalCount() {
      return this.platforms.reduce((sum, platform) => sum + platform.count, 0);
    },
    mostActivePlatform() {
      return this.sortedPlatforms.length > 0 ? this.sortedPlatforms[0].name : '-';
    },
    topPlatformPercentage() {
      if (this.totalCount === 0 || this.sortedPlatforms.length === 0) return 0;
      return Math.round((this.sortedPlatforms[0].count / this.totalCount) * 100);
    }
  },
  watch: {
    stat: {
      handler: function (val) {
        if (val && val.platform) {
          this.platforms = val.platform;
        }
      },
      deep: true,
    }
  },
  methods: {
    getPercentage(count) {
      return this.totalCount ? (count / this.totalCount) * 100 : 0;
    }
  }
};
</script>

<style scoped>
.platform-stat-card {
  height: 100%;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05) !important;
  transition: transform 0.2s;
}

.platform-stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08) !important;
}

.platform-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.platform-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--v-theme-primaryText);
}

.platform-subtitle {
  font-size: 12px;
  color: var(--v-theme-secondaryText);
  margin-top: 4px;
}

.platform-list-container {
  display: flex;
  flex-direction: column;
}

.platform-list {
  max-height: 180px;
  overflow-y: auto;
  padding: 0;
  margin-bottom: 16px;
}

.platform-item {
  padding: 8px 16px;
  margin-bottom: 4px;
  border-radius: 8px;
  transition: background-color 0.2s;
}

.platform-item:hover {
  background-color: #f5f5f5;
}

.platform-rank {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background-color: var(--v-theme-surface);
  color: var(--v-theme-primaryText);
  font-weight: 600;
  font-size: 14px;
  margin-right: 12px;
}

.top-rank {
  background-color: var(--v-theme-secondary);
  color: var(--v-theme-surface);
}

.platform-name {
  font-weight: 500;
}

.platform-count {
  display: flex;
  align-items: center;
}

.count-value {
  font-weight: 600;
  font-size: 14px;
  color: var(--v-theme-secondary);
  margin-right: 4px;
}

.count-label {
  font-size: 12px;
  color: var(--v-theme-secondaryText);
}

.platform-stats-summary {
  display: flex;
  justify-content: space-between;
  background-color: var(--v-theme-containerBg);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 16px;
}

.platform-stat-item {
  flex: 1;
  text-align: center;
}

.stat-label {
  font-size: 12px;
  color: var(--v-theme-secondaryText);
  margin-bottom: 4px;
}

.stat-value {
  font-weight: 600;
  color: var(--v-theme-primaryText);
}

.platform-chart {
  margin-top: 8px;
}

.platform-progress {
  margin-bottom: 12px;
}

.no-data {
  height: 250px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.no-data-text {
  color: var(--v-theme-secondaryText);
  margin-top: 16px;
  font-size: 14px;
}
</style>