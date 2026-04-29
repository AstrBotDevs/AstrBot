<template>
  <v-card elevation="1" class="stat-card uptime-card">
    <v-card-text>
      <div class="d-flex align-start">
        <div class="icon-wrapper">
          <v-icon icon="mdi-clock-outline" size="24" />
        </div>

        <div class="stat-content">
          <div class="stat-title">
            {{ t("stats.runningTime.title") }}
          </div>
          <div class="stat-value-wrapper">
            <h2 class="stat-value">
              {{ formattedTime }}
            </h2>
          </div>
          <div class="stat-subtitle">
            {{ t("stats.runningTime.subtitle") }}
          </div>
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>

<script lang="ts">
import { useModuleI18n } from "@/i18n/composables";

export default {
  name: "RunningTime",
  props: ["stat"],
  setup() {
    const { tm: t } = useModuleI18n("features/dashboard");
    return { t };
  },
  computed: {
    formattedTime() {
      if (!this.stat?.running) {
        return this.t("status.loading");
      }

      const { hours, minutes, seconds } = this.stat.running;
      return this.t("stats.runningTime.format", {
        hours,
        minutes,
        seconds,
      });
    },
  },
};
</script>

<style scoped>
.stat-card {
  height: 100%;
  border-radius: 16px;
  overflow: hidden;
  position: relative;
  transition: transform 0.25s ease;
}

.stat-card:hover {
  transform: translateY(-3px);
}

.uptime-card {
  background: linear-gradient(145deg, #66bb6a 0%, #1b5e20 100%) !important;
  box-shadow: inset 0 2px 12px rgba(0, 0, 0, 0.35) !important;
}

.uptime-card:hover {
  box-shadow:
    inset 0 2px 12px rgba(0, 0, 0, 0.35),
    0 0 20px rgba(76, 175, 80, 0.4) !important;
}

.stat-card::before {
  content: "";
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
  content: "";
  position: absolute;
  top: 0;
  left: 12px;
  right: 12px;
  height: 1px;
  background: rgba(255, 255, 255, 0.35);
  border-radius: 0 0 1px 1px;
  pointer-events: none;
  z-index: 2;
}

.icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
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

.stat-value-wrapper {
  display: flex;
  align-items: baseline;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  line-height: 1.2;
}

.stat-subtitle {
  font-size: 12px;
  opacity: 0.7;
}
</style>
