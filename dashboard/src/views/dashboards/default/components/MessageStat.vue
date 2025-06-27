<template>
  <v-card elevation="1" class="chart-card">
    <v-card-text>
      <div class="chart-header">
        <div>
          <div class="chart-title">{{ t('charts.messageTrend.title') }}</div>
          <div class="chart-subtitle">{{ t('charts.messageTrend.subtitle') }}</div>
        </div>
        
        <v-select 
          color="primary" 
          variant="outlined"
          density="compact"
          hide-details 
          v-model="selectedTimeRange" 
          :items="timeRanges" 
          item-title="label" 
          item-value="value" 
          class="time-select"
          @update:model-value="fetchMessageSeries"
          return-object 
          single-line
        >
          <template v-slot:selection="{ item }">
            <div class="d-flex align-center">
              <v-icon start size="small">mdi-calendar-range</v-icon>
              {{ item.raw.label }}
            </div>
          </template>
        </v-select>
      </div>
      
      <div class="chart-stats">
        <div class="stat-box">
          <div class="stat-label">{{ t('charts.messageTrend.totalMessages') }}</div>
          <div class="stat-number">{{ totalMessages }}</div>
        </div>
        
        <div class="stat-box">
          <div class="stat-label">{{ t('charts.messageTrend.dailyAverage') }}</div>
          <div class="stat-number">{{ dailyAverage }}</div>
        </div>
        
        <div class="stat-box" :class="{'trend-up': growthRate > 0, 'trend-down': growthRate < 0}">
          <div class="stat-label">{{ t('charts.messageTrend.growthRate') }}</div>
          <div class="stat-number">
            <v-icon size="small" :icon="growthRate > 0 ? 'mdi-arrow-up' : 'mdi-arrow-down'"></v-icon>
            {{ Math.abs(growthRate) }}%
          </div>
        </div>
      </div>
      
      <div class="chart-container">
        <div v-if="loading" class="loading-overlay">
          <v-progress-circular indeterminate color="primary"></v-progress-circular>
          <div class="loading-text">{{ t('status.loading') }}</div>
        </div>
        <apexchart 
          type="area" 
          height="280" 
          :options="chartOptions" 
          :series="chartSeries" 
          ref="chart"
        ></apexchart>
      </div>
    </v-card-text>
  </v-card>
</template>

<script>
import axios from 'axios';
import {useCustomizerStore} from "@/stores/customizer";
import { useModuleI18n } from '@/i18n/composables';

export default {
  name: 'MessageStat',
  props: ['stat'],
  setup() {
    const { tm: t } = useModuleI18n('features/dashboard');
    return { t };
  },
  data() {
    return {
    totalMessages: '0',
    dailyAverage: '0',
    growthRate: 0,
    loading: false,
    selectedTimeRange: null,
    timeRanges: [],
    
    chartOptions: {
      chart: {
        type: 'area',
        height: 400,
        fontFamily: `inherit`,
        foreColor: '#a1aab2',
        toolbar: {
          show: true,
          tools: {
            download: true,
            selection: false,
            zoom: true,
            zoomin: true,
            zoomout: true,
            pan: true,
          },
        },
        animations: {
          enabled: true,
          easing: 'easeinout',
          speed: 800,
        },
      },
      colors: ['#5e35b1'],
      fill: {
        type: 'solid',
        opacity: 0.3,
      },
      dataLabels: {
        enabled: false
      },
      stroke: {
        curve: 'smooth',
        width: 2
      },
      markers: {
        size: 3,
        strokeWidth: 2,
        hover: {
          size: 5,
        }
      },
      tooltip: {
        theme: useCustomizerStore().uiTheme==='PurpleTheme' ? 'light' : 'dark',
        x: {
          format: 'yyyy-MM-dd HH:mm'
        },
        y: {
          title: {
            formatter: () => ''
          }
        },
      },
      xaxis: {
        type: 'datetime',
        title: {
          text: ''
        },
        labels: {
          formatter: function (value) {
            return new Date(value).toLocaleString('zh-CN', {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit'
            });
          }
        },
        tooltip: {
          enabled: false
        }
      },
      yaxis: {
        title: {
          text: ''
        },
        min: function(min) {
          return min < 10 ? 0 : Math.floor(min * 0.8);
        },
      },
      grid: {
        borderColor: "gray100",
        row: {
          colors: ['transparent', 'transparent'],
          opacity: 0.2
        },
        column: {
          colors: ['transparent', 'transparent'],
        },
        padding: {
          left: 0,
          right: 0
        }
      }
    },
    
    chartSeries: [
      {
        name: '',
        data: []
      }
    ],
    
    messageTimeSeries: []
    };
  },

  mounted() {
    // 初始化时间范围选项
    this.timeRanges = [
      { label: this.t('charts.messageTrend.timeRanges.1day'), value: 86400 },
      { label: this.t('charts.messageTrend.timeRanges.3days'), value: 259200 },
      { label: this.t('charts.messageTrend.timeRanges.1week'), value: 604800 },
      { label: this.t('charts.messageTrend.timeRanges.1month'), value: 2592000 },
    ];
    this.selectedTimeRange = this.timeRanges[0];
    
    // 设置图表翻译文本
    this.chartOptions.tooltip.y.title.formatter = () => this.t('charts.messageTrend.messageCount') + ' ';
    this.chartOptions.xaxis.title.text = this.t('charts.messageTrend.timeLabel');
    this.chartOptions.yaxis.title.text = this.t('charts.messageTrend.messageCount');
    this.chartSeries[0].name = this.t('charts.messageTrend.messageCount');
    
    // 初始加载
    this.fetchMessageSeries();
  },

  methods: {
    formatNumber(num) {
      return new Intl.NumberFormat('zh-CN').format(num);
    },
    
    async fetchMessageSeries() {
      this.loading = true;
      
      try {
        const response = await axios.get(`/api/stat/get?offset_sec=${this.selectedTimeRange.value}`);
        const data = response.data.data;
        
        if (data && data.message_time_series) {
          this.messageTimeSeries = data.message_time_series;
          this.processTimeSeriesData();
        }
      } catch (error) {
        console.error(this.t('status.dataError'), error);
      } finally {
        this.loading = false;
      }
    },
    
    processTimeSeriesData() {
      // 转换数据为图表格式
      this.chartSeries[0].data = this.messageTimeSeries.map((item) => {
        return [new Date(item[0]*1000).getTime(), item[1]];
      });
      
      // 计算总消息数
      let total = 0;
      this.messageTimeSeries.forEach(item => {
        total += item[1];
      });
      this.totalMessages = this.formatNumber(total);
      
      // 计算日平均
      if (this.messageTimeSeries.length > 0) {
        const daysSpan = this.selectedTimeRange.value / 86400; // 将秒转换为天数
        this.dailyAverage = this.formatNumber(Math.round(total / daysSpan));
      }
      
      // 计算增长率
      this.calculateGrowthRate();
    },
    
    calculateGrowthRate() {
      if (this.messageTimeSeries.length < 4) {
        this.growthRate = 0;
        return;
      }
      
      // 计算前半部分和后半部分的消息总数
      const halfIndex = Math.floor(this.messageTimeSeries.length / 2);
      
      const firstHalf = this.messageTimeSeries
        .slice(0, halfIndex)
        .reduce((sum, item) => sum + item[1], 0);
        
      const secondHalf = this.messageTimeSeries
        .slice(halfIndex)
        .reduce((sum, item) => sum + item[1], 0);
      
      // 计算增长率
      if (firstHalf > 0) {
        this.growthRate = Math.round(((secondHalf - firstHalf) / firstHalf) * 100);
      } else {
        this.growthRate = secondHalf > 0 ? 100 : 0;
      }
    }
  }
};
</script>

<style scoped>
.chart-card {
  height: 100%;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05) !important;
  transition: transform 0.2s;
}

.chart-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08) !important;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}

.chart-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--v-theme-primaryText);
}

.chart-subtitle {
  font-size: 12px;
  color: var(--v-theme-secondaryText);
  margin-top: 4px;
}

.time-select {
  max-width: 150px;
  font-size: 14px;
}

.chart-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
}

.stat-box {
  padding: 12px 16px;
  background: var(--v-theme-surface);
  border-radius: 8px;
  flex: 1;
}

.stat-label {
  font-size: 12px;
  color: var(--v-theme-secondaryText);
  margin-bottom: 4px;
}

.stat-number {
  font-size: 18px;
  font-weight: 600;
  color: var(--v-theme-primaryText);
  display: flex;
  align-items: center;
}

.trend-up .stat-number {
  color: var(--v-theme-success);
}

.trend-down .stat-number {
  color: var(--v-theme-error);
}

.chart-container {
  border-top: 1px solid var(--v-theme-border);
  padding-top: 20px;
  position: relative;
}

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: var(--v-theme-overlay);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  z-index: 10;
}

.loading-text {
  margin-top: 12px;
  font-size: 14px;
  color: var(--v-theme-secondaryText);
}
</style>