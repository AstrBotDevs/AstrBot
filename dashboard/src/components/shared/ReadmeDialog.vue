<script setup>
import { ref, watch, computed } from "vue";
import axios from "axios";
import { enableKatex, enableMermaid } from "markstream-vue";
import "markstream-vue/index.css";
import "katex/dist/katex.min.css";
import "highlight.js/styles/github.css";
import { useI18n } from "@/i18n/composables";
import GitHubMarkdownViewer from "@/components/shared/GitHubMarkdownViewer.vue";
import { preprocessPluginMarkdown } from "@/utils/preprocessPluginMarkdown";

const props = defineProps({
  show: { type: Boolean, default: false },
  pluginName: { type: String, default: "" },
  repoUrl: { type: String, default: null },
  mode: {
    type: String,
    default: "readme",
    validator: (value) => ["readme", "changelog"].includes(value),
  },
});

const emit = defineEmits(["update:show"]);
const { t, locale } = useI18n();

const content = ref(null);
const error = ref(null);
const loading = ref(false);
const isEmpty = ref(false);
const lastRequestId = ref(0);

const modeConfig = computed(() => {
  const isChangelog = props.mode === "changelog";
  const keyBase = `core.common.${isChangelog ? "changelog" : "readme"}`;
  return {
    title: t(`${keyBase}.title`),
    loading: t(`${keyBase}.loading`),
    emptyTitle: t(`${keyBase}.empty.title`),
    emptySubtitle: t(`${keyBase}.empty.subtitle`),
    apiPath: `/api/plugin/${isChangelog ? "changelog" : "readme"}`,
  };
});

async function fetchContent() {
  if (!props.pluginName) return;
  const requestId = ++lastRequestId.value;
  loading.value = true;
  content.value = null;
  error.value = null;
  isEmpty.value = false;

  try {
    const res = await axios.get(
      `${modeConfig.value.apiPath}?name=${props.pluginName}`,
    );
    if (requestId !== lastRequestId.value) return;

    if (res.data.status === "ok") {
      if (res.data.data.content) {
        content.value = preprocessPluginMarkdown(res.data.data.content);
      } else {
        // 请求成功但无内容
        isEmpty.value = true;
      }
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
    if (show && name) fetchContent();
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
</script>

<template>
  <v-dialog v-model="_show" width="800">
    <v-card>
      <v-card-title class="d-flex justify-space-between align-center">
        <span class="text-h5">{{ modeConfig.title }}</span>
        <v-btn icon @click="_show = false" variant="text">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-card-title>
      <v-divider></v-divider>
      <v-card-text style="height: 70vh; overflow-y: auto">
        <div class="d-flex justify-space-between mb-4">
          <v-btn
            v-if="repoUrl"
            color="primary"
            prepend-icon="mdi-github"
            @click="openExternalLink(repoUrl)"
          >
            {{ t("core.common.readme.buttons.viewOnGithub") }}
          </v-btn>
          <v-btn
            color="secondary"
            prepend-icon="mdi-refresh"
            @click="fetchContent"
          >
            {{ t("core.common.readme.buttons.refresh") }}
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

        <!-- 内容显示 -->
        <div v-else-if="content" class="readme-dialog__content">
          <div class="readme-dialog__container">
            <GitHubMarkdownViewer
              :content="content"
              :header-icon="mode === 'changelog' ? 'mdi-history' : 'mdi-book-open-outline'"
              :header-label="mode === 'changelog' ? 'CHANGELOG.md' : 'README.md'"
            />
          </div>
        </div>

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
      <v-divider></v-divider>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="primary" variant="tonal" @click="_show = false">
          {{ t("core.common.close") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.readme-dialog__container {
  max-width: 1012px;
  margin: 0 auto;
  padding: 32px;
}

.readme-dialog__content {
  min-height: 100%;
}

@media (max-width: 767px) {
  .readme-dialog__container {
    padding: 16px;
  }
  .github-style-content {
    padding: 24px;
  }
}
</style>
