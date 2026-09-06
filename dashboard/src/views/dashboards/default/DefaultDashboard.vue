<template>
  <div class="dashboard-container">
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
        />
      </v-row>
    </v-slide-y-transition>

    <!-- 主指标卡片行: 2x2 grid -->
    <v-row class="stats-row">
      <v-col cols="12" sm="6" lg="3">
        <v-slide-y-transition>
          <TotalMessage :stat="stat" />
        </v-slide-y-transition>
      </v-col>
      <v-col cols="12" sm="6" lg="3">
        <v-slide-y-transition>
          <OnlinePlatform :stat="stat" />
        </v-slide-y-transition>
      </v-col>
      <v-col cols="12" sm="6" lg="3">
        <v-slide-y-transition>
          <RunningTime :stat="stat" />
        </v-slide-y-transition>
      </v-col>
      <v-col cols="12" sm="6" lg="3">
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
      <v-chip
        size="small"
        color="primary"
        variant="flat"
        prepend-icon="mdi-refresh"
      >
        {{ t("lastUpdate") }}: {{ lastUpdated }}
      </v-chip>
      <v-btn
        icon="mdi-refresh"
        size="small"
        color="primary"
        variant="text"
        class="ml-2"
        :loading="isRefreshing"
        @click="fetchData"
      />
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent } from "vue";
import type { ApiEnvelope } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";
import axios from "@/utils/request";
import MemoryUsage from "./components/MemoryUsage.vue";
import MessageStat from "./components/MessageStat.vue";
import OnlinePlatform from "./components/OnlinePlatform.vue";
import PlatformStat, { type PlatformMessageStat } from "./components/PlatformStat.vue";
import RunningTime from "./components/RunningTime.vue";
import TotalMessage from "./components/TotalMessage.vue";

type NoticeType = "success" | "info" | "warning" | "error";

interface DashboardNotice {
  title: string;
  content: string;
  type?: string;
}

export default defineComponent({
  name: "DefaultDashboard",
  components: {
    TotalMessage,
    OnlinePlatform,
    RunningTime,
    MemoryUsage,
    MessageStat,
    PlatformStat,
  },
  setup() {
    const { tm: t } = useModuleI18n("features/dashboard");
    return { t };
  },
  data() {
    return {
      stat: {} as { platform?: PlatformMessageStat[] },
      noticeTitle: "",
      noticeContent: "",
      noticeType: "info" as NoticeType,
      lastUpdated: "",
      refreshInterval: null as ReturnType<typeof setInterval> | null,
      isRefreshing: false,
    };
  },

  mounted() {
    this.lastUpdated = this.t("status.loading");
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
        const res = await axios.get<ApiEnvelope<{ platform: PlatformMessageStat[] }>>("/api/stat/get");
        this.stat = res.data.data;
        this.lastUpdated = new Date().toLocaleTimeString();
        console.info("Dashboard data:", this.stat);
      } catch (error) {
        console.error(this.t("status.dataError"), error);
      } finally {
        this.isRefreshing = false;
      }
    },

    fetchNotice() {
      axios
        .get<{ data?: { "dashboard-notice"?: DashboardNotice } }>("https://api.soulter.top/astrbot-announcement")
        .then((res) => {
          const notice = res.data.data?.["dashboard-notice"];
          if (notice) {
            this.noticeTitle = notice.title;
            this.noticeContent = notice.content;
            const type = notice.type;
            this.noticeType = type === "success" || type === "warning" || type === "error" ? type : "info";
          }
        })
        .catch((error) => {
          console.error(this.t("status.noticeError"), error);
        });
    },
  },
});
</script>

<style scoped>
.dashboard-container {
  padding: 16px;
  background-color: var(--v-theme-background);
  min-height: calc(100vh - 64px);
  border-radius: 10px;
}

.notice-row {
  margin-bottom: 16px;
}

.dashboard-alert {
  width: 100%;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05) !important;
}

.stats-row,
.charts-row,
.plugin-row {
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
  transition:
    transform 0.2s,
    box-shadow 0.2s;
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
