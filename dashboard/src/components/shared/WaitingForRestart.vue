<template>
  <v-dialog v-model="visible" persistent max-width="400">
    <v-card>
      <v-card-title>{{ t("core.common.restart.waiting") }}</v-card-title>
      <v-card-text>
        <v-progress-linear indeterminate color="primary" />
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script lang="ts">
import axios from "@/utils/request";
import { useCommonStore } from "@/stores/common";
import { useI18n } from "@/i18n/composables";

export default {
  name: "WaitingForRestart",
  setup() {
    const { t } = useI18n();
    return { t };
  },
  data() {
    return {
      visible: false,
      startTime: -1,
      newStartTime: -1,
      status: "",
      cnt: 0,
    };
  },
  methods: {
    async check(initialStartTime = null) {
      this.newStartTime = -1;
      this.cnt = 0;
      this.visible = true;
      this.status = "";
      if (
        typeof initialStartTime === "number" &&
        Number.isFinite(initialStartTime)
      ) {
        this.startTime = initialStartTime;
      } else {
        const commonStore = useCommonStore();
        try {
          this.startTime = await commonStore.fetchStartTime();
        } catch (_error) {
          this.startTime = commonStore.getStartTime();
        }
      }
      console.info("start wfr");
      setTimeout(() => {
        this.timeoutInternal();
      }, 1000);
    },
    stop() {
      this.visible = false;
      this.cnt = 0;
      this.newStartTime = -1;
    },
    timeoutInternal() {
      console.info("wfr: timeoutInternal", this.newStartTime, this.startTime);
      if (this.newStartTime === -1 && this.cnt < 60 && this.visible) {
        this.checkStartTime();
        this.cnt++;
        setTimeout(() => {
          this.timeoutInternal();
        }, 1000);
      } else {
        if (this.cnt >= 60) {
          this.status = this.t("core.common.restart.maxRetriesReached");
        }
        this.cnt = 0;
        setTimeout(() => {
          this.visible = false;
        }, 1000);
      }
    },
    async checkStartTime() {
      try {
        const res = await axios.get("/api/stat/start-time", { timeout: 3000 });
        const newStartTime = res.data.data.start_time;
        console.info("wfr: checkStartTime", newStartTime, this.startTime);
        if (this.startTime !== -1 && newStartTime !== this.startTime) {
          this.newStartTime = newStartTime;
          console.info("wfr: restarted");
          this.visible = false;
          // reload
          window.location.reload();
        }
      } catch (_error) {
        // backend may be unavailable during restart window
      }
      return this.newStartTime;
    },
  },
};
</script>
