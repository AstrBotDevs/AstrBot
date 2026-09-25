<script setup lang="ts">
import { RouterView, useRoute } from "vue-router";
import { ref, onMounted, computed, watch } from "vue";
import VerticalSidebarVue from "./vertical-sidebar/VerticalSidebar.vue";
import VerticalHeaderVue from "./vertical-header/VerticalHeader.vue";
import ReadmeDialog from "@/components/shared/ReadmeDialog.vue";
import Chat from "@/components/chat/Chat.vue";
import { useCustomizerStore } from "@/stores/customizer";
import { useRouterLoadingStore } from "@/stores/routerLoading";
import { useCommonStore } from "@/stores/common";
import { statsApi } from "@/api/v1";
import { useI18n } from "@/i18n/composables";

const FIRST_NOTICE_SEEN_KEY = "astrbot:first_notice_seen:v1";

const customizer = useCustomizerStore();
const commonStore = useCommonStore();
const { locale } = useI18n();
const route = useRoute();
const routerLoadingStore = useRouterLoadingStore();
const isCurrentChatRoute = computed(
  () => route.path === "/chat" || route.path.startsWith("/chat/"),
);
const isPluginPageRoute = computed(
  () => route.path.startsWith("/plugin-page/"),
);
const isProviderPageRoute = computed(() => route.path === "/providers");
const isPlatformPageRoute = computed(() => route.path === "/platforms");
const isViewportLockedRoute = computed(
  () =>
    isCurrentChatRoute.value ||
    isProviderPageRoute.value ||
    isPlatformPageRoute.value,
);
const isFullScreenRoute = computed(
  () => isCurrentChatRoute.value || isPluginPageRoute.value,
);
const shouldMountChat = ref(isCurrentChatRoute.value);

const showSidebar = computed(() => !isCurrentChatRoute.value);

const showFirstNoticeDialog = ref(false);

watch(isCurrentChatRoute, (isChatRoute) => {
  if (isChatRoute) {
    shouldMountChat.value = true;
  }
});

const maybeShowFirstNotice = async () => {
  if (localStorage.getItem(FIRST_NOTICE_SEEN_KEY) === "1") {
    return;
  }

  try {
    const response = await statsApi.firstNotice(locale.value);
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
    try {
      const response = await statsApi.version();
      if (response.data.status === "ok") {
        commonStore.setAstrBotVersion(
          response.data.data?.version,
          response.data.data?.dashboard_version,
        );
      }
    } catch (error) {
      console.error("Failed to load version info:", error);
    }
    await maybeShowFirstNotice();
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
      <VerticalSidebarVue v-if="showSidebar" />
      <VerticalHeaderVue />
      <v-main
        :class="{ 'chat-main': isCurrentChatRoute }"
        :style="{
          height: isViewportLockedRoute ? '100vh' : undefined,
          overflow: isViewportLockedRoute ? 'hidden' : undefined,
        }"
      >
        <v-container
          fluid
          class="page-wrapper"
          :class="{
            'chat-mode-container': isCurrentChatRoute,
            'viewport-locked-container':
              isProviderPageRoute || isPlatformPageRoute,
            'fullscreen-container': isFullScreenRoute,
          }"
          :style="{
            height:
              isFullScreenRoute || isProviderPageRoute || isPlatformPageRoute
                ? '100%'
                : 'calc(100% - 8px)',
            padding: isFullScreenRoute ? '0' : undefined,
            minHeight:
              isFullScreenRoute || isProviderPageRoute || isPlatformPageRoute
                ? 'unset'
                : undefined,
          }"
        >
          <div
            :style="{
              height: '100%',
              width: '100%',
              overflow: isViewportLockedRoute ? 'hidden' : undefined,
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

.viewport-locked-container {
  min-height: unset !important;
  height: 100% !important;
  overflow: hidden !important;
}

.chat-main {
  padding-top: 0 !important;
}

/* The header takes its own row in the flow, so the content area owns the remaining
   height and scrolls on its own instead of sliding under the header. */
:global(html),
:global(body) {
  height: 100%;
  overflow: hidden;
}

:global(.v-application),
:global(.v-application__wrap) {
  height: 100vh;
  min-height: 0;
  overflow: hidden;
}

:global(.v-main) {
  height: calc(100vh - var(--astrbot-toolbar-height, 40px)) !important;
  padding-top: 0 !important;
  overflow-x: hidden !important;
  overflow-y: auto !important;
  scrollbar-width: none;
  /* The document no longer scrolls; the content area does. Sticky offsets that were
     written for the document layout must be measured from the content area's own top. */
  --v-layout-top: 0px !important;
}

:global(.v-main::-webkit-scrollbar) {
  width: 0;
  background: transparent;
}

/* The content area is the opaque card next to the sidebar. */
:global(.page-wrapper) {
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-top-left-radius: 12px;
}

/* Normal pages grow with their content so the main area has something to scroll. */
:global(.page-wrapper:not(.viewport-locked-container):not(.chat-mode-container):not(.fullscreen-container)) {
  height: auto !important;
  min-height: calc(100vh - var(--astrbot-toolbar-height, 40px));
}

/* Viewport-locked and full-screen pages keep a fixed height and scroll internally.
   Clipping them keeps full-bleed children from painting outside the rounded corner. */
:global(.viewport-locked-container),
:global(.chat-mode-container),
:global(.fullscreen-container) {
  height: calc(100vh - var(--astrbot-toolbar-height, 40px)) !important;
  overflow: hidden !important;
}

/* macOS desktop vibrancy: the window material shows through wherever the UI stays
   transparent. Only the content area keeps an opaque background. */
:global(html[data-astrbot-desktop-platform='macos']) {
  /* Bias the native window material toward white in light mode, black in dark mode. */
  --astrbot-vibrancy-tint: rgba(255, 255, 255, 0.55);
}

:global(html[data-astrbot-desktop-platform='macos'] .v-application.v-theme--PurpleThemeDark) {
  --astrbot-vibrancy-tint: rgba(0, 0, 0, 0.3);
}

:global(html[data-astrbot-desktop-platform='macos']),
:global(html[data-astrbot-desktop-platform='macos'] body),
:global(html[data-astrbot-desktop-platform='macos'] .v-application),
:global(html[data-astrbot-desktop-platform='macos'] .v-application__wrap) {
  background: transparent !important;
}

/* The sidebar tint lives on the main area's own background (behind everything), covering
   the sidebar column plus a small overhang that reaches the content corner. */
:global(html[data-astrbot-desktop-platform='macos'] .v-main) {
  background: linear-gradient(
    to right,
    var(--astrbot-vibrancy-tint, transparent) 0 calc(var(--v-layout-left) + 12px),
    transparent calc(var(--v-layout-left) + 12px) 100%
  ) !important;
}

/* Vuetify paints its own surface behind every list, which would sit on top of the
   translucent sidebar, so keep the navigation lists transparent on macOS. */
:global(html[data-astrbot-desktop-platform='macos'] .leftSidebar .v-list),
:global(html[data-astrbot-desktop-platform='macos'] .chat-sidebar .v-list) {
  background: transparent !important;
}
</style>
