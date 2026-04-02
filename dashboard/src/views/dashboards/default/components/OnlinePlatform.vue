<template>
  <v-card elevation="1" class="stat-card platform-card">
    <v-card-text>
      <div class="d-flex align-start">
        <div class="icon-wrapper">
          <v-icon icon="mdi-server-network" size="24" />
        </div>

        <div class="stat-content">
          <div class="stat-title">
            {{ t("stats.onlinePlatform.title") }}
          </div>
          <div class="stat-value-wrapper">
            <h2 class="stat-value">
              {{ stat.platform_count || 0 }}
            </h2>
          </div>
          <div class="stat-subtitle">
            {{ t("stats.onlinePlatform.subtitle") }}
          </div>
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>

<script lang="ts">
import { useModuleI18n } from "@/i18n/composables";

export default {
  name: "OnlinePlatform",
  props: ["stat"],
  setup() {
    const { tm: t } = useModuleI18n("features/dashboard");
    return { t };
  },
};
</script>

<style scoped>
/* === LATTICE FLUX: Deep Glow Energy Cards === */
/* Each card = high-pressure reaction pool. Color bleeds from within. */

.stat-card {
  height: 100%;
  border-radius: 16px;
  overflow: hidden;
  position: relative;
  /* Base: flat, will be overridden per card type */
  transition: transform 0.25s ease;
}

.stat-card:hover {
  transform: translateY(-3px);
}

/* Per-card deep glow gradient */
.platform-card {
  background: linear-gradient(145deg, #1e88e5 0%, #0d47a1 100%) !important;
  box-shadow: inset 0 2px 12px rgba(0, 0, 0, 0.35) !important;
}

.message-card {
  background: linear-gradient(145deg, #7e57c2 0%, #311b92 100%) !important;
  box-shadow: inset 0 2px 12px rgba(0, 0, 0, 0.35) !important;
}

.memory-card {
  background: linear-gradient(145deg, #ffa726 0%, #e65100 100%) !important;
  box-shadow: inset 0 2px 12px rgba(0, 0, 0, 0.35) !important;
}

.uptime-card {
  background: linear-gradient(145deg, #66bb6a 0%, #1b5e20 100%) !important;
  box-shadow: inset 0 2px 12px rgba(0, 0, 0, 0.35) !important;
}

/* Grid overlay — lattice constraint texture */
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

/* Bright seam: magnetic containment at top edge only */
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

/* Hover: color bleeds outward */
.platform-card:hover {
  box-shadow:
    inset 0 2px 12px rgba(0, 0, 0, 0.35),
    0 0 20px rgba(33, 150, 243, 0.4) !important;
  transition: box-shadow 0.25s ease;
}

.message-card:hover {
  box-shadow:
    inset 0 2px 12px rgba(0, 0, 0, 0.35),
    0 0 20px rgba(94, 53, 177, 0.4) !important;
}

.memory-card:hover {
  box-shadow:
    inset 0 2px 12px rgba(0, 0, 0, 0.35),
    0 0 20px rgba(255, 152, 0, 0.4) !important;
}

.uptime-card:hover {
  box-shadow:
    inset 0 2px 12px rgba(0, 0, 0, 0.35),
    0 0 20px rgba(76, 175, 80, 0.4) !important;
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
  gap: 6px;
}

.stat-value {
  font-size: 32px;
  font-weight: 600;
  line-height: 1.2;
}

.stat-subtitle {
  font-size: 12px;
  opacity: 0.7;
}

.trend-chip {
  font-weight: 600;
}
</style>
