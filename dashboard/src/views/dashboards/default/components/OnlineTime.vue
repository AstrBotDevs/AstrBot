<template>
  <div class="stats-container">
    <v-card elevation="1" class="stat-card uptime-card mb-4">
      <v-card-text>
        <div class="d-flex align-center">
          <div class="icon-wrapper">
            <v-icon icon="mdi-clock-outline" size="24"></v-icon>
          </div>
          
          <div class="stat-content">
            <div class="stat-title">运行时间</div>
            <h3 class="uptime-value">{{ stat.running || '加载中...' }}</h3>
          </div>
          
          <v-spacer></v-spacer>
          
          <div class="uptime-status">
            <v-icon icon="mdi-circle" size="10" color="success" class="blink-animation"></v-icon>
            <span class="status-text">在线</span>
          </div>
        </div>
      </v-card-text>
    </v-card>

    <v-card elevation="1" class="stat-card memory-card">
      <v-card-text>
        <div class="d-flex align-center">
          <div class="icon-wrapper">
            <v-icon icon="mdi-memory" size="24"></v-icon>
          </div>
          
          <div class="stat-content">
            <div class="stat-title">内存占用</div>
            <div class="memory-values">
              <h3 class="memory-value">{{ stat.memory?.process || 0 }} <span class="memory-unit">MiB</span></h3>
              <span class="memory-separator">/</span>
              <h4 class="memory-total">{{ stat.memory?.system || 0 }} <span class="memory-unit">MiB</span></h4>
            </div>
            
            <v-progress-linear
              :model-value="memoryPercentage"
              color="warning"
              height="4"
              class="mt-2"
            ></v-progress-linear>
            
            <div class="memory-percentage">{{ memoryPercentage }}%</div>
          </div>
        </div>
      </v-card-text>
    </v-card>
  </div>
</template>

<script>
export default {
  name: 'OnlineTime',
  props: ['stat'],
  data: () => ({
    stat: {
      memory: { process: 0, system: 0 },
      running: "加载中...",
    },
  }),
  computed: {
    memoryPercentage() {
      if (!this.stat.memory || !this.stat.memory.process || !this.stat.memory.system) return 0;
      return Math.round((this.stat.memory.process / this.stat.memory.system) * 100);
    }
  }
};
</script>

<style scoped>
.stats-container {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.stat-card {
  border-radius: 8px;
  transition: transform 0.2s, box-shadow 0.2s;
  overflow: hidden;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08) !important;
}

.uptime-card {
  background-color: #4caf50;
  color: white;
  flex: 1;
}

.memory-card {
  background-color: #ff9800;
  color: white;
  flex: 1;
}

.icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
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

.uptime-value {
  font-size: 24px;
  font-weight: 600;
  line-height: 1.2;
}

.uptime-status {
  display: flex;
  align-items: center;
  background: rgba(255, 255, 255, 0.2);
  padding: 4px 10px;
  border-radius: 20px;
}

.status-text {
  margin-left: 6px;
  font-size: 12px;
  font-weight: 500;
}

.memory-values {
  display: flex;
  align-items: baseline;
}

.memory-value {
  font-size: 22px;
  font-weight: 600;
}

.memory-separator {
  margin: 0 6px;
  font-weight: 300;
  opacity: 0.7;
}

.memory-total {
  font-size: 18px;
  font-weight: 400;
  opacity: 0.8;
}

.memory-unit {
  font-size: 14px;
  font-weight: 400;
  opacity: 0.8;
}

.memory-percentage {
  font-size: 12px;
  margin-top: 4px;
  text-align: right;
  opacity: 0.9;
}

@keyframes blink {
  0% { opacity: 0.5; }
  50% { opacity: 1; }
  100% { opacity: 0.5; }
}

.blink-animation {
  animation: blink 1.5s infinite;
}
</style>