<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "@/i18n/composables";

const props = defineProps<{
  progress: AstrBotDesktopAppUpdateProgress | null;
}>();
const { t } = useI18n();
const downloaded = computed(() => {
  const bytes = props.progress?.downloadedBytes;
  return typeof bytes === "number" && Number.isFinite(bytes)
    ? Math.max(0, bytes)
    : 0;
});
const percentage = computed(() => {
  const total = props.progress?.totalBytes;
  if (
    props.progress?.phase !== "downloading" ||
    !total ||
    !Number.isFinite(total) ||
    total <= 0
  ) {
    return null;
  }
  return Math.min(100, Math.floor((downloaded.value / total) * 100));
});
const status = computed(() => {
  const phase = props.progress?.phase;
  const key =
    phase === "downloading" || phase === "verifying"
      ? phase
      : phase === "installing"
      ? "applying"
      : "installing";
  return t(`core.header.updateDialog.desktopApp.${key}`);
});
const transfer = computed(() => {
  const amount = (downloaded.value / 1024 / 1024).toFixed(1);
  const total = props.progress?.totalBytes;
  return percentage.value !== null && total
    ? `${amount} / ${(total / 1024 / 1024).toFixed(1)} MiB`
    : `${amount} MiB`;
});
</script>

<template>
  <div class="mt-3">
    <div class="text-caption mb-2" role="status">{{ status }}</div>
    <v-progress-linear
      :model-value="percentage ?? 0"
      :indeterminate="percentage === null"
      :aria-label="status"
      color="primary"
      height="6"
      rounded
    />
    <div
      v-if="progress?.phase === 'downloading'"
      class="d-flex justify-space-between text-caption mt-1"
    >
      <span>{{ transfer }}</span>
      <span v-if="percentage !== null">{{ percentage }}%</span>
    </div>
  </div>
</template>
