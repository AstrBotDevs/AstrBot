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

enableKatex();
enableMermaid();

const props = defineProps({
  show: {
    type: Boolean,
    default: false,
  },
  pluginName: {
    type: String,
    default: "",
  },
  repoUrl: {
    type: String,
    default: null,
  },
  // 模式: 'readme' 或 'changelog'
  mode: {
    type: String,
    default: "readme",
    validator: (value) => ["readme", "changelog"].includes(value),
  },
});

const emit = defineEmits(["update:show"]);

// 国际化
const { t } = useI18n();

const content = ref(null);
const error = ref(null);
const loading = ref(false);
const isEmpty = ref(false);

const modeConfig = computed(() => {
  if (props.mode === "changelog") {
    return {
      title: t("core.common.changelog.title"),
      loading: t("core.common.changelog.loading"),
      emptyTitle: t("core.common.changelog.empty.title"),
      emptySubtitle: t("core.common.changelog.empty.subtitle"),
      apiPath: "/api/plugin/changelog",
    };
  }
  return {
    title: t("core.common.readme.title"),
    loading: t("core.common.readme.loading"),
    emptyTitle: t("core.common.readme.empty.title"),
    emptySubtitle: t("core.common.readme.empty.subtitle"),
    apiPath: "/api/plugin/readme",
  };
});

// 获取内容
async function fetchContent() {
  if (!props.pluginName) return;

  loading.value = true;
  content.value = null;
  error.value = null;
  isEmpty.value = false;

  try {
    const res = await axios.get(
      `${modeConfig.value.apiPath}?name=${props.pluginName}`,
    );
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
    error.value = err.message;
  } finally {
    loading.value = false;
  }
}

watch(
  [() => props.show, () => props.pluginName, () => props.mode],
  ([show, name]) => {
    if (show && name) fetchContent();
  },
  { immediate: true },
);

// 打开GitHub中的仓库
function openRepoInNewTab() {
  if (props.repoUrl) {
    window.open(props.repoUrl, "_blank");
  }
}

// 刷新内容
function refreshContent() {
  fetchContent();
}

const _show = computed({
  get() {
    return props.show;
  },
  set(value) {
    emit("update:show", value);
  },
});
</script>

<template>
  <v-dialog v-model="_show" width="800">
    <v-card>
      <v-card-title class="d-flex justify-space-between align-center">
        <span class="text-h5">{{ modeConfig.title }}</span>
        <v-btn icon @click="$emit('update:show', false)" variant="text">
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
            @click="openRepoInNewTab()"
          >
            {{ t("core.common.readme.buttons.viewOnGithub") }}
          </v-btn>
          <v-btn
            color="secondary"
            prepend-icon="mdi-refresh"
            @click="refreshContent()"
          >
            {{ t("core.common.readme.buttons.refresh") }}
          </v-btn>
        </div>

        <!-- 加载中 -->
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
              :show-header="false"
            />
          </div>
        </div>

        <!-- 错误提示 -->
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

        <!-- 无内容提示 -->
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
        <v-btn
          color="primary"
          variant="tonal"
          @click="$emit('update:show', false)"
        >
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

