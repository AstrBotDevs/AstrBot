<template>
  <div class="stats-container">
    <v-card elevation="1" class="stat-card uptime-card mb-4">
      <v-card-text>
        <div class="d-flex align-center">
          <div class="icon-wrapper">
            <v-icon icon="mdi-clock-outline" size="24" />
          </div>

          <div class="stat-content">
            <div class="stat-title">
              {{ tm("features.dashboard.status.uptime") }}
            </div>
            <h3 class="uptime-value">
              {{ stat.running || tm("features.dashboard.status.loading") }}
            </h3>
          </div>

          <v-spacer />

          <div class="uptime-status">
            <v-icon
              icon="mdi-circle"
              size="10"
              color="success"
              class="blink-animation"
            />
            <span class="status-text">{{
              tm("features.dashboard.status.online")
            }}</span>
          </div>
        </div>
      </v-card-text>
    </v-card>

    <v-card elevation="1" class="stat-card memory-card">
      <v-card-text>
        <div class="d-flex align-center">
          <div class="icon-wrapper">
            <v-icon icon="mdi-memory" size="24" />
          </div>

          <div class="stat-content">
            <div class="stat-title">
              {{ tm("features.dashboard.status.memoryUsage") }}
            </div>
            <div class="memory-values">
              <h3 class="memory-value">
                {{ stat.memory?.process || 0 }}
                <span class="memory-unit">MiB</span>
              </h3>
              <span class="memory-separator">/</span>
              <h4 class="memory-total">
                {{ stat.memory?.system || 0 }}
                <span class="memory-unit">MiB</span>
              </h4>
            </div>

            <v-progress-linear
              :model-value="memoryPercentage"
              color="warning"
              height="4"
              class="mt-2"
            />

            <div class="memory-percentage">{{ memoryPercentage }}%</div>
          </div>
        </div>
      </v-card-text>
    </v-card>
  </div>
</template>

<script lang="ts">
import { useModuleI18n } from "@/i18n/composables";

export default {
  name: "OnlineTime",
  props: ["stat"],
  setup() {
    const { tm } = useModuleI18n("features/dashboard");
    return { tm };
  },
  computed: {
    memoryPercentage() {
      if (
        !this.stat.memory ||
        !this.stat.memory.process ||
        !this.stat.memory.system
      )
        return 0;
      return Math.round(
        (this.stat.memory.process / this.stat.memory.system) * 100,
      );
    },
  },
};
</script>

<style scoped>
.stats-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.stat-card {
  border-radius: 16px;
  overflow: hidden;
  position: relative;
  transition: transform 0.25s ease;
  flex: 1;
}

.stat-card:hover {
  transform: translateY(-2px);
}

.uptime-card {
  background: linear-gradient(145deg, #66bb6a 0%, #1b5e20 100%) !important;
  box-shadow: inset 0 2px 12px rgba(0, 0, 0, 0.35) !important;
}

.uptime-card:hover {
  box-shadow: inset 0 2px 12px rgba(0, 0, 0, 0.35), 0 0 16px rgba(76, 175, 80, 0.35) !important;
}

.memory-card {
  background: linear-gradient(145deg, #ffa726 0%, #e65100 100%) !important;
  box-shadow: inset 0 2px 12px rgba(0, 0, 0, 0.35) !important;
}

.memory-card:hover {
  box-shadow: inset 0 2px 12px rgba(0, 0, 0, 0.35), 0 0 16px rgba(255, 152, 0, 0.35) !important;
}

.stat-card::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px);
  background-size: 20px 20px;
  pointer-events: none;
  z-index: 1;
}

.stat-card::after {
  content: '';
  position: absolute;
  top: 0;
  left: 12px;
  right: 12px;
  height: 1px;
  background: rgba(255, 255, 255, 0.3);
  border-radius: 0 0 1px 1px;
  pointer-events: none;
  z-index: 2;
}

.icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 8px;
  margin-right: 16px;
  background: rgba(255, 255, 255, 0.18);
  flex-shrink: 0;
  position: relative;
  z-index: 3;
}

.stat-content {
  flex: 1;
  position: relative;
  z-index: 3;
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
  0% {
    opacity: 0.5;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0.5;
  }
}

.blink-animation {
  animation: blink 1.5s infinite;
}
</style>
