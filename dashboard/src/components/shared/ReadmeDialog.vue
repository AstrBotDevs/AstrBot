<script setup>
import { ref, watch, computed } from "vue";
import { useTheme } from "vuetify";
import { pluginApi, statsApi } from "@/api/v1";
import { useI18n } from "@/i18n/composables";
import MarkdownView from "@/components/shared/MarkdownView.vue";

const props = defineProps({
  show: { type: Boolean, default: false },
  pluginName: { type: String, default: "" },
  repoUrl: { type: String, default: null },
  mode: {
    type: String,
    default: "readme",
    validator: (value) => ["readme", "changelog", "first-notice"].includes(value),
  },
});

const emit = defineEmits(["update:show"]);
const { t, locale } = useI18n();
const theme = useTheme();

const content = ref(null);
const error = ref(null);
const loading = ref(false);
const isEmpty = ref(false);
const lastRequestId = ref(0);
const isDark = computed(() => theme.global.current.value.dark);

const modeConfig = computed(() => {
  if (props.mode === "changelog") {
    return {
      title: t("core.common.changelog.title"),
      loading: t("core.common.changelog.loading"),
      emptyTitle: t("core.common.changelog.empty.title"),
      emptySubtitle: t("core.common.changelog.empty.subtitle"),
      showGithubButton: false,
      showRefreshButton: true,
      refreshLabel: t("core.common.readme.buttons.refresh"),
    };
  }

  if (props.mode === "first-notice") {
    return {
      title: t("core.common.firstNotice.title"),
      loading: t("core.common.firstNotice.loading"),
      emptyTitle: t("core.common.firstNotice.empty.title"),
      emptySubtitle: t("core.common.firstNotice.empty.subtitle"),
      showGithubButton: false,
      showRefreshButton: false,
      refreshLabel: "",
    };
  }

  return {
    title: t("core.common.readme.title"),
    loading: t("core.common.readme.loading"),
    emptyTitle: t("core.common.readme.empty.title"),
    emptySubtitle: t("core.common.readme.empty.subtitle"),
    showGithubButton: true,
    showRefreshButton: true,
    refreshLabel: t("core.common.readme.buttons.refresh"),
  };
});

const requiresPluginName = computed(
  () => props.mode === "readme" || props.mode === "changelog",
);

async function fetchContent() {
  if (requiresPluginName.value && !props.pluginName) return;
  const requestId = ++lastRequestId.value;
  loading.value = true;
  content.value = null;
  error.value = null;
  isEmpty.value = false;

  try {
    let res;
    if (props.mode === "changelog") {
      res = await pluginApi.changelog(props.pluginName);
    } else if (props.mode === "readme") {
      res = await pluginApi.readme(props.pluginName);
    } else if (props.mode === "first-notice") {
      res = await statsApi.firstNotice(locale.value);
    }
    if (requestId !== lastRequestId.value) return;

    if (res.data.status === "ok") {
      if (res.data.data.content) content.value = res.data.data.content;
      else isEmpty.value = true;
    } else {
      error.value = res.data.message;
    }
  } catch (err) {
    if (requestId === lastRequestId.value) error.value = err.message;
  } finally {
    if (requestId === lastRequestId.value) loading.value = false;
  }
}

watch(
  [() => props.show, () => props.pluginName, () => props.mode],
  ([show, name]) => {
    if (!show) return;
    if (requiresPluginName.value && !name) return;
    fetchContent();
  },
  { immediate: true },
);

const _show = computed({
  get: () => props.show,
  set: (val) => emit("update:show", val),
});

// 安全打开外部链接
function openExternalLink(url) {
  if (!url) return;
  window.open(url, "_blank", "noopener,noreferrer");
}

const showActionArea = computed(() => {
  const hasGithub = modeConfig.value.showGithubButton && !!props.repoUrl;
  return hasGithub || modeConfig.value.showRefreshButton;
});
</script>

<template>
  <v-dialog v-model="_show" width="800">
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex justify-space-between align-center">
        <span>{{ modeConfig.title }}</span>
        <v-btn icon @click="_show = false" variant="text">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-card-title>
      <v-card-text style="overflow-y: auto">
        <div v-if="showActionArea" class="d-flex justify-space-between mb-4">
          <v-btn
            v-if="modeConfig.showGithubButton && repoUrl"
            color="primary"
            variant="tonal"
            prepend-icon="mdi-github"
            @click="openExternalLink(repoUrl)"
          >
            {{ t("core.common.readme.buttons.viewOnGithub") }}
          </v-btn>
          <v-btn
            v-if="modeConfig.showRefreshButton"
            color="secondary"
            variant="tonal"
            prepend-icon="mdi-refresh"
            @click="fetchContent"
          >
            {{ modeConfig.refreshLabel }}
          </v-btn>
        </div>

        <div
          v-if="loading"
          class="d-flex flex-column align-center justify-center"
          style="height: 100%"
        >
          <v-progress-circular
            indeterminate
            color="primary"
            size="64"
            class="mb-4"
          ></v-progress-circular>
          <p class="text-body-1 text-center">{{ modeConfig.loading }}</p>
        </div>

        <MarkdownView
          v-else-if="content"
          :source="content"
          :is-dark="isDark"
        />

        <div
          v-else-if="error"
          class="d-flex flex-column align-center justify-center"
          style="height: 100%"
        >
          <v-icon size="64" color="error" class="mb-4"
            >mdi-alert-circle-outline</v-icon
          >
          <p class="text-body-1 text-center mb-2">
            {{ t("core.common.error") }}
          </p>
          <p class="text-body-2 text-center text-medium-emphasis">
            {{ error }}
          </p>
        </div>

        <div
          v-else-if="isEmpty"
          class="d-flex flex-column align-center justify-center"
          style="height: 100%"
        >
          <v-icon size="64" color="warning" class="mb-4"
            >mdi-file-question-outline</v-icon
          >
          <p class="text-body-1 text-center mb-2">
            {{ modeConfig.emptyTitle }}
          </p>
          <p class="text-body-2 text-center text-medium-emphasis">
            {{ modeConfig.emptySubtitle }}
          </p>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="primary" variant="tonal" @click="_show = false">
          {{ t("core.common.close") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<!--
  2026-07-13: Markdown rendering delegated to <MarkdownView>, which
  itself delegates to markstream-vue's <MarkdownRender> — the same
  component ChatUI uses. This drops the self-built createMarkdownRenderer
  pipeline + ~370 lines of hand-rolled CSS, and the readme modal now
  renders identically to the chat message view. MarkdownView handles
  the copy-code button click and in-document anchor jumps itself, so
  the previously bespoke click handler + copy feedback code in this
  file is no longer needed.
-->
