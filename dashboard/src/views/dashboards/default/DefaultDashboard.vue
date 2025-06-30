<template>
  <div class="dashboard-container">
    <div class="dashboard-header">
      <h1 class="dashboard-title">{{ t('title') }}</h1>
      <div class="dashboard-subtitle">{{ t('subtitle') }}</div>
    </div>
    
    <v-slide-y-transition>
      <v-row v-if="noticeTitle && noticeContent" class="notice-row">
        <v-alert
          :type="noticeType"
          :text="noticeContent"
          :title="noticeTitle"
          closable
          class="dashboard-alert"
          variant="tonal"
          border="start"
        ></v-alert>
      </v-row>
    </v-slide-y-transition>
    
    <!-- 主指标卡片行 -->
    <v-row class="stats-row">
      <v-col cols="12" md="3">
        <v-slide-y-transition>
          <TotalMessage :stat="stat" />
        </v-slide-y-transition>
      </v-col>
      <v-col cols="12" md="3">
        <v-slide-y-transition>
          <OnlinePlatform :stat="stat" />
        </v-slide-y-transition>
      </v-col>
      <v-col cols="12" md="3">
        <v-slide-y-transition>
          <RunningTime :stat="stat" />
        </v-slide-y-transition>
      </v-col>
      <v-col cols="12" md="3">
        <v-slide-y-transition>
          <MemoryUsage :stat="stat" />
        </v-slide-y-transition>
      </v-col>
    </v-row>
    
    <!-- 图表行 -->
    <v-row class="charts-row">
      <v-col cols="12" lg="8">
        <v-slide-y-transition>
          <MessageStat />
        </v-slide-y-transition>
      </v-col>
      <v-col cols="12" lg="4">
        <v-slide-y-transition>
          <PlatformStat :stat="stat" />
        </v-slide-y-transition>
      </v-col>
    </v-row>
    <div class="dashboard-footer">
      <v-chip size="small" color="primary" variant="flat" prepend-icon="mdi-refresh">
        {{ t('lastUpdate') }}: {{ lastUpdated }}
      </v-chip>
      <v-btn 
        icon="mdi-refresh" 
        size="small" 
        color="primary" 
        variant="text" 
        class="ml-2" 
        @click="fetchData"
        :loading="isRefreshing"
      ></v-btn>
    </div>
  </div>
</template>


<script>
import TotalMessage from './components/TotalMessage.vue';
import OnlinePlatform from './components/OnlinePlatform.vue';
import RunningTime from './components/RunningTime.vue';
import MemoryUsage from './components/MemoryUsage.vue';
import MessageStat from './components/MessageStat.vue';
import PlatformStat from './components/PlatformStat.vue';
import axios from 'axios';
import { useModuleI18n } from '@/i18n/composables';

export default {
  name: 'DefaultDashboard',
  components: {
    TotalMessage,
    OnlinePlatform,
    RunningTime,
    MemoryUsage,
    MessageStat,
    PlatformStat,
  },
  setup() {
    const { tm: t } = useModuleI18n('features/dashboard');
    return { t };
  },
  data() {
    return {
      stat: {},
      noticeTitle: '',
      noticeContent: '',
      noticeType: '',
      lastUpdated: '',
      refreshInterval: null,
      isRefreshing: false
    };
  },

  mounted() {
    this.lastUpdated = this.t('status.loading');
    this.fetchData();
    this.fetchNotice();
    
    // 设置自动刷新（每60秒）
    this.refreshInterval = setInterval(() => {
      this.fetchData();
    }, 60000);
  },
  
  beforeUnmount() {
    // 清除定时器
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
  },
  
  methods: {
    async fetchData() {
      this.isRefreshing = true;
      try {
        const res = await axios.get('/api/stat/get');
        this.stat = res.data.data;
        this.lastUpdated = new Date().toLocaleTimeString();
        console.log('Dashboard data:', this.stat);
      } catch (error) {
        console.error(this.t('status.dataError'), error);
      } finally {
        this.isRefreshing = false;
      }
    },
    
    fetchNotice() {
      axios.get('https://api.soulter.top/astrbot-announcement').then((res) => {
        let data = res.data.data;
        // 如果 dashboard-notice 在其中
        if (data['dashboard-notice']) {
          this.noticeTitle = data['dashboard-notice'].title;
          this.noticeContent = data['dashboard-notice'].content;
          this.noticeType = data['dashboard-notice'].type;
        }
      }).catch(error => {
        console.error(this.t('status.noticeError'), error);
      });
    }
  }
};
</script>

<style scoped>
.dashboard-container {
  padding: 16px;
  background-color: var(--v-theme-background);
  min-height: calc(100vh - 64px);
  border-radius: 10px;
  
}

.dashboard-header {
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.dashboard-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--v-theme-primaryText);
  margin-bottom: 4px;
}

.dashboard-subtitle {
  font-size: 14px;
  color: var(--v-theme-secondaryText);
}

.notice-row {
  margin-bottom: 20px;
}

.dashboard-alert {
  width: 100%;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05) !important;
}

.stats-row, .charts-row, .plugin-row {
  margin-bottom: 24px;
}

.plugin-card {
  border-radius: 8px;
  background-color: var(--v-theme-surface);
}

.plugin-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--v-theme-primaryText);
}

.plugin-subtitle {
  font-size: 12px;
  color: var(--v-theme-secondaryText);
  margin-top: 4px;
}

.plugin-item {
  transition: transform 0.2s, box-shadow 0.2s;
}

.plugin-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05) !important;
}

.plugin-name {
  font-size: 14px;
  font-weight: 500;
}

.plugin-version {
  font-size: 12px;
  color: var(--v-theme-secondaryText, #666);
}

.dashboard-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}
</style>
