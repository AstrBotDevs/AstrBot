<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { RouterView, useRoute } from "vue-router";
import Chat from "@/components/chat/Chat.vue";
// biome-ignore lint/style/useImportType: Vue template components require runtime imports.
import MigrationDialog from "@/components/shared/MigrationDialog.vue";
import ReadmeDialog from "@/components/shared/ReadmeDialog.vue";
import { useI18n } from "@/i18n/composables";
import { useCommonStore } from "@/stores/common";
import { useCustomizerStore } from "@/stores/customizer";
import { useRouterLoadingStore } from "@/stores/routerLoading";
import axios from "@/utils/request";
import VerticalHeaderVue from "./vertical-header/VerticalHeader.vue";
import VerticalSidebarVue from "./vertical-sidebar/VerticalSidebar.vue";

const FIRST_NOTICE_SEEN_KEY = "astrbot:first_notice_seen:v1";

const customizer = useCustomizerStore();
const commonStore = useCommonStore();
const { locale } = useI18n();
const route = useRoute();
const routerLoadingStore = useRouterLoadingStore();
const isCurrentChatRoute = computed(() => route.path === "/chat" || route.path.startsWith("/chat/"));
const isPluginPageRoute = computed(() => route.path.startsWith("/plugin-page/"));
const isFullScreenRoute = computed(() => isCurrentChatRoute.value || isPluginPageRoute.value);
const shouldMountChat = ref(isCurrentChatRoute.value);

const showSidebar = computed(() => !isCurrentChatRoute.value);

const migrationDialog = ref<InstanceType<typeof MigrationDialog> | null>(null);
const showFirstNoticeDialog = ref(false);

watch(isCurrentChatRoute, (isChatRoute) => {
  if (isChatRoute) {
    shouldMountChat.value = true;
  }
});

const checkMigration = async (): Promise<boolean> => {
  try {
    const response = await axios.get("/api/stat/version");
    if (response.data.status === "ok") {
      commonStore.setAstrBotVersion(response.data.data?.version, response.data.data?.dashboard_version);
    }
    if (response.data.status === "ok" && response.data.data.need_migration) {
      if (migrationDialog.value && typeof migrationDialog.value.open === "function") {
        const result = await migrationDialog.value.open();
        if (result.success) {
          console.log("Migration completed successfully:", result.message);
          window.location.reload();
        }
      }
      return true;
    }
  } catch (error) {
    console.error("Failed to check migration status:", error);
  }
  return false;
};

const maybeShowFirstNotice = async () => {
  if (localStorage.getItem(FIRST_NOTICE_SEEN_KEY) === "1") {
    return;
  }

  try {
    const response = await axios.get("/api/stat/first-notice", {
      params: { locale: locale.value },
    });
    if (response.data.status !== "ok") {
      return;
    }

    const content = response.data?.data?.content;
    if (typeof content === "string" && content.trim().length > 0) {
      showFirstNoticeDialog.value = true;
      return;
    }

    localStorage.setItem(FIRST_NOTICE_SEEN_KEY, "1");
  } catch (error) {
    console.error("Failed to load first notice:", error);
  }
};

const onFirstNoticeDialogUpdate = (visible: boolean) => {
  showFirstNoticeDialog.value = visible;
  if (!visible) {
    localStorage.setItem(FIRST_NOTICE_SEEN_KEY, "1");
  }
};

onMounted(() => {
  setTimeout(async () => {
    const migrationPending = await checkMigration();
    if (!migrationPending) {
      await maybeShowFirstNotice();
    }
  }, 1000);
});
</script>

<template>
  <v-locale-provider>
    <v-app
      :theme="useCustomizerStore().uiTheme"
      :class="[
        customizer.fontTheme,
        customizer.mini_sidebar ? 'mini-sidebar' : '',
        customizer.inputBg ? 'inputWithbg' : '',
      ]"
    >
      <v-progress-linear
        v-if="routerLoadingStore.isLoading"
        :model-value="routerLoadingStore.progress"
        color="primary"
        height="2"
        fixed
        top
        style="z-index: 9999; position: absolute; opacity: 0.3"
      />
      <VerticalHeaderVue />
      <VerticalSidebarVue v-if="showSidebar" />
      <v-main
        :class="{ 'chat-main': isCurrentChatRoute }"
        :style="{
          height: isCurrentChatRoute ? '100vh' : undefined,
          overflow: isCurrentChatRoute ? 'hidden' : undefined,
        }"
      >
        <v-container
          fluid
          class="page-wrapper"
          :class="{ 'chat-mode-container': isCurrentChatRoute }"
          :style="{
            height: isFullScreenRoute ? '100%' : 'calc(100% - 8px)',
            padding: isFullScreenRoute ? '0' : undefined,
            minHeight: isFullScreenRoute ? 'unset' : undefined,
          }"
        >
          <div
            :style="{
              height: '100%',
              width: '100%',
              overflow: isCurrentChatRoute ? 'hidden' : undefined,
              position: isPluginPageRoute ? 'relative' : undefined,
            }"
          >
            <div
              v-if="shouldMountChat"
              v-show="isCurrentChatRoute"
              style="height: 100%; width: 100%; overflow: hidden"
            >
              <Chat :active="isCurrentChatRoute" />
            </div>
            <RouterView v-if="!isCurrentChatRoute" />
          </div>
        </v-container>
      </v-main>

      <MigrationDialog ref="migrationDialog" />
      <ReadmeDialog
        :show="showFirstNoticeDialog"
        mode="first-notice"
        @update:show="onFirstNoticeDialogUpdate"
      />
    </v-app>
  </v-locale-provider>
</template>

<style scoped>
.chat-mode-container {
  min-height: unset !important;
  height: 100% !important;
  overflow: hidden !important;
}

.chat-main {
  padding-top: 0 !important;
}
</style>
