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
import { useMobileDrawerStore } from "@/stores/mobileDrawer";
import { statsApi } from "@/api/v1";
import { useI18n } from "@/i18n/composables";

const FIRST_NOTICE_SEEN_KEY = "astrbot:first_notice_seen:v1";

const customizer = useCustomizerStore();
const commonStore = useCommonStore();
const mobileDrawer = useMobileDrawerStore();
const { locale } = useI18n();
const route = useRoute();
const routerLoadingStore = useRouterLoadingStore();
const isCurrentChatRoute = computed(
  () => route.path === "/chat" || route.path.startsWith("/chat/"),
);
const isPluginViewRoute = computed(
  () => route.path.startsWith("/plugin-view/") || route.path.startsWith("/plugin-page/"),
);
const isProviderPageRoute = computed(() => route.path === "/providers");
const isPlatformPageRoute = computed(() => route.path === "/platforms");
const isViewportLockedRoute = computed(
  () =>
    isCurrentChatRoute.value ||
    isProviderPageRoute.value ||
    isPlatformPageRoute.value ||
    route.path === "/config" ||
    route.path === "/settings",
);
const isFullScreenRoute = computed(
  () => isCurrentChatRoute.value || isPluginViewRoute.value,
);
const shouldMountChat = ref(isCurrentChatRoute.value);

const showSidebar = computed(() => !isCurrentChatRoute.value);

const showFirstNoticeDialog = ref(false);

watch(isCurrentChatRoute, (isChatRoute) => {
  if (isChatRoute) {
    shouldMountChat.value = true;
  }
});

// Temporary mobile drawers must never survive a route transition. Chat stays
// mounted with v-show, so resetting the shared store here also covers Chat/Bot
// switches and navigation initiated from inside ChatUI.
watch(
  () => route.fullPath,
  () => mobileDrawer.SET(false),
  { immediate: true },
);

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
      <v-main :class="{ 'chat-main': isCurrentChatRoute }">
        <v-container
          fluid
          class="page-wrapper"
          :class="{
            'chat-mode-container': isCurrentChatRoute,
            'viewport-locked-container':
              isProviderPageRoute || isPlatformPageRoute,
            'fullscreen-container': isFullScreenRoute,
          }"
        >
          <div
            class="page-content"
            :class="{
              'page-content--locked': isViewportLockedRoute || isPluginViewRoute,
            }"
            :style="{
              padding: isFullScreenRoute ? '0' : undefined,
              position: isPluginViewRoute ? 'relative' : undefined,
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

/* The shell is sized with dynamic viewport units: the mobile browsers' URL/toolbar
   area is excluded, so the bottom of the shell is never painted underneath it. */
:global(.v-application),
:global(.v-application__wrap) {
  height: 100dvh;
  min-height: 0;
  overflow: hidden;
}

:global(.v-main) {
  height: calc(100dvh - var(--astrbot-toolbar-height, 42px)) !important;
  padding-top: 0 !important;
  overflow: hidden !important;
  /* The document no longer scrolls; the content area does. Sticky offsets that were
     written for the document layout must be measured from the content area's own top. */
  --v-layout-top: 0px !important;
}

/* Keep the card frame fixed while its content scrolls inside the rounded edges. */
:global(.page-wrapper) {
  --astrbot-content-gap: 6px;
  height: calc(100dvh - var(--astrbot-toolbar-height, 42px) - var(--astrbot-content-gap)) !important;
  width: calc(100% - var(--astrbot-content-gap));
  min-height: 0;
  margin: 0;
  padding: 0 !important;
  overflow: hidden;
  border: 0;
  border-radius: 16px;
}

/* Let the content fill the available width on small screens. */
@media (max-width: 959.98px) {
  :global(.page-wrapper) {
    --astrbot-content-gap: 0px;
    border-radius: 0;
  }
}

.page-content {
  height: 100%;
  width: 100%;
  padding: 8px;
  overflow-x: hidden;
  overflow-y: auto;
  scrollbar-width: none;
}

.page-content::-webkit-scrollbar {
  width: 0;
  background: transparent;
}

/* Chat, workspace and plugin pages manage their own internal scrolling. */
.page-content--locked {
  overflow: hidden;
}

/* macOS desktop vibrancy: the window material shows through wherever the UI stays
   transparent. Only the content area keeps an opaque background. */
:global(html) {
  /* Shared chrome background for the top toolbar and the sidebars, so the
     header and sidebar always read as one surface in both themes. */
  --astrbot-chrome-bg: #f2f2f7;
}

:global(html .v-application.v-theme--PurpleThemeDark) {
  --astrbot-chrome-bg: rgb(var(--v-theme-background));
}

:global(html[data-astrbot-desktop-platform='macos']) {
  /* Preserve the shell's gray tint while letting the native window material show through. */
  --astrbot-vibrancy-tint: rgba(242, 242, 247, 0.6);
}

:global(html[data-astrbot-desktop-platform='macos'] .v-application.v-theme--PurpleThemeDark) {
  --astrbot-vibrancy-tint: rgba(26, 26, 26, 0.92);
}

/* Extend the sidebar surface behind every corner and the right/bottom gaps. */
:global(html:not([data-astrbot-desktop-platform='macos']) .v-main) {
  background: var(--astrbot-chrome-bg) !important;
}

:global(html[data-astrbot-desktop-platform='macos']),
:global(html[data-astrbot-desktop-platform='macos'] body),
:global(html[data-astrbot-desktop-platform='macos'] .v-application),
:global(html[data-astrbot-desktop-platform='macos'] .v-application__wrap) {
  background: transparent !important;
}

/* Keep the macOS tint continuous behind the sidebar and the card gaps. */
:global(html[data-astrbot-desktop-platform='macos'] .v-main) {
  background: var(--astrbot-vibrancy-tint, transparent) !important;
}

/* Navigation lists inherit the shared shell background. */
:global(.leftSidebar .v-list),
:global(.chat-sidebar .v-list) {
  background: transparent !important;
}
</style>
