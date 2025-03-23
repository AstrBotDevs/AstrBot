<template>
  <v-card elevation="1" class="chart-card">
    <v-card-text>
      <div class="chart-header">
        <div>
          <div class="chart-title">消息趋势分析</div>
          <div class="chart-subtitle">跟踪消息数量随时间的变化</div>
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
          <div class="stat-label">总消息数</div>
          <div class="stat-number">{{ totalMessages }}</div>
        </div>
        
        <div class="stat-box">
          <div class="stat-label">平均每天</div>
          <div class="stat-number">{{ dailyAverage }}</div>
        </div>
        
        <div class="stat-box" :class="{'trend-up': growthRate > 0, 'trend-down': growthRate < 0}">
          <div class="stat-label">增长率</div>
          <div class="stat-number">
            <v-icon size="small" :icon="growthRate > 0 ? 'mdi-arrow-up' : 'mdi-arrow-down'"></v-icon>
            {{ Math.abs(growthRate) }}%
          </div>
        </div>
      </div>
      
      <div class="chart-container">
        <div v-if="loading" class="loading-overlay">
          <v-progress-circular indeterminate color="primary"></v-progress-circular>
          <div class="loading-text">加载中...</div>
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

export default {
  name: 'MessageStat',
  props: ['stat'],
  data: () => ({
    totalMessages: '0',
    dailyAverage: '0',
    growthRate: 0,
    loading: false,
    selectedTimeRange: { label: '过去 1 天', value: 86400 },
    timeRanges: [
      { label: '过去 1 天', value: 86400 },
      { label: '过去 3 天', value: 259200 },
      { label: '过去 7 天', value: 604800 },
      { label: '过去 30 天', value: 2592000 },
    ],
    
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
        theme: 'light',
        x: {
          format: 'yyyy-MM-dd HH:mm'
        },
        y: {
          title: {
            formatter: () => '消息条数 '
          }
        },
      },
      xaxis: {
        type: 'datetime',
        title: {
          text: '时间'
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
          text: '消息条数'
        },
        min: function(min) {
          return min < 10 ? 0 : Math.floor(min * 0.8);
        },
      },
      grid: {
        borderColor: '#f1f1f1',
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
        name: '消息条数',
        data: []
      }
    ],
    
    messageTimeSeries: []
  }),

  mounted() {
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
        console.error('获取消息趋势数据失败:', error);
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
  color: #333;
}

.chart-subtitle {
  font-size: 12px;
  color: #666;
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
  background: #f5f5f5;
  border-radius: 8px;
  flex: 1;
}

.stat-label {
  font-size: 12px;
  color: #666;
  margin-bottom: 4px;
}

.stat-number {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  display: flex;
  align-items: center;
}

.trend-up .stat-number {
  color: #4caf50;
}

.trend-down .stat-number {
  color: #f44336;
}

.chart-container {
  border-top: 1px solid #f0f0f0;
  padding-top: 20px;
  position: relative;
}

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(255, 255, 255, 0.8);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  z-index: 10;
}

.loading-text {
  margin-top: 12px;
  font-size: 14px;
  color: #666;
}
</style>