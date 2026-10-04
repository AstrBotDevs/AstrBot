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
const isPluginPageRoute = computed(
  () => route.path.startsWith("/plugin-view/") || route.path.startsWith("/plugin-page/"),
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
            class="page-content"
            :style="{
              height: '100%',
              width: '100%',
              overflow: isViewportLockedRoute ? 'hidden' : undefined,
              overflowY:
                !isViewportLockedRoute && !isPluginPageRoute
                  ? 'auto'
                  : undefined,
              padding:
                !isViewportLockedRoute && !isPluginPageRoute
                  ? '8px'
                  : undefined,
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
  overflow: hidden !important;
}

.viewport-locked-container {
  min-height: unset !important;
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
  /* Scrolling happens inside the card, so v-main itself must not clip: the
     card's shadow is meant to spill softly onto the header and sidebar. */
  overflow: visible !important;
  /* The document no longer scrolls; the content area does. Sticky offsets that were
     written for the document layout must be measured from the content area's own top. */
  --v-layout-top: 0px !important;
}

/* The content area is the opaque card floating between the sidebar, the
   header, and the window edges. No hairlines: rounded corners plus a faint
   ambient shadow separate it from the chrome; the sidebar tint painted behind
   v-main fills the corner notches. */
:global(.page-wrapper) {
  border-radius: 12px;
  /* No drawn hairlines: the card separates from the chrome through a faint,
     wide ambient shadow alone (Linear/Notion-style elevation). */
  box-shadow:
    0 1px 3px rgba(0, 0, 0, 0.04),
    0 4px 24px rgba(0, 0, 0, 0.035);
  /* Above the sidebar/header chrome (z-index ~1004) so the shadow can fall on
     them; still far below teleported overlays (2400+). */
  position: relative;
  z-index: 1010;
}

/* On the dark surface the same faint lift needs a deeper shadow to stay
   visible; keep it soft rather than turning into a glow. */
:global(.v-application.v-theme--PurpleThemeDark .page-wrapper) {
  box-shadow:
    0 1px 3px rgba(0, 0, 0, 0.12),
    0 4px 24px rgba(0, 0, 0, 0.1);
}

/* On small screens there is no permanent sidebar to separate from, so the
   card's edge treatments would only read as stray lines. */
@media (max-width: 959.98px) {
  :global(.page-wrapper) {
    border-radius: 0;
    box-shadow: none;
    /* The temporary drawer must slide over the content on small screens. */
    position: static;
    z-index: auto;
  }
}

/* Normal pages are pinned to the viewport as well: the card frame (borders and
   rounded corners) never moves, and the page content scrolls inside the card
   via .page-content instead of scrolling the whole main area. */
:global(.page-wrapper:not(.viewport-locked-container):not(.chat-mode-container):not(.fullscreen-container)) {
  height: calc(100vh - var(--astrbot-toolbar-height, 40px) - 6px) !important;
  width: calc(100% - 6px) !important;
  margin-left: 0 !important;
  overflow: hidden;
  /* The frame itself carries no inset: the historical 8px padding lives on
     .page-content so it scrolls away together with the page content. */
  padding: 0;
}

/* Keep the in-card scroller's scrollbar hidden, matching the main area's
   established look. */
:global(.page-content) {
  /* overflow-y: auto (set inline) would silently turn the other axis into
     auto as well; pin overflow-x so nothing inside the card can scroll
     sideways. */
  overflow-x: hidden;
  scrollbar-width: none;
}
:global(.page-content::-webkit-scrollbar) {
  width: 0;
  background: transparent;
}

/* Viewport-locked and full-screen pages keep a fixed height and scroll internally.
   Clipping them keeps full-bleed children from painting outside the rounded corner. */
:global(.viewport-locked-container),
:global(.chat-mode-container),
:global(.fullscreen-container) {
  /* The extra 6px lifts the card off the window's bottom edge and right edge
     so the dividers get the same breathing room the rounded corners enjoy. */
  height: calc(100vh - var(--astrbot-toolbar-height, 40px) - 6px) !important;
  width: calc(100% - 6px) !important;
  margin-left: 0 !important;
  overflow: hidden !important;
}

/* macOS desktop vibrancy: the window material shows through wherever the UI stays
   transparent. Only the content area keeps an opaque background. */
:global(html) {
  /* Shared chrome background for the top toolbar and the sidebars, so the
     header and sidebar always read as one surface in both themes. A small
     dose of the theme's primary color is mixed in, so the whole chrome
     follows when the user recolors the theme. */
  /* Foreground colors (primary/secondary) accent the content. The chrome
     background is an independent "background" pick, always softened into the
     neutral surface so it reads as a quiet tint instead of a solid paint.
     Unset means the plain neutral surface. chrome-surface shares the same
     value so the header and the sidebar are pixel-identical. */
  --astrbot-chrome-bg: color-mix(in srgb, var(--astrbot-chrome-color-light, rgb(var(--v-theme-surface))) 10%, rgb(var(--v-theme-surface)));
  --astrbot-chrome-surface: color-mix(in srgb, var(--astrbot-chrome-color-light, rgb(var(--v-theme-surface))) 10%, rgb(var(--v-theme-surface)));
}

:global(html .v-application.v-theme--PurpleThemeDark) {
  --astrbot-chrome-bg: color-mix(in srgb, var(--astrbot-chrome-color-dark, rgb(var(--v-theme-surface))) 12%, rgb(var(--v-theme-surface)));
  --astrbot-chrome-surface: color-mix(in srgb, var(--astrbot-chrome-color-dark, rgb(var(--v-theme-surface))) 12%, rgb(var(--v-theme-surface)));
}

:global(html[data-astrbot-desktop-platform='macos']) {
  /* Bias the native window material toward white in light mode, black in dark mode.
     Mostly opaque so the chrome reads as light even when the material behind is dark.
     The primary infusion keeps the translucent chrome on-theme as well. */
  --astrbot-vibrancy-tint: color-mix(in srgb, var(--astrbot-chrome-color-light, rgb(253, 252, 252)) 10%, rgba(253, 252, 252, 0.92));
}

:global(html[data-astrbot-desktop-platform='macos'] .v-application.v-theme--PurpleThemeDark) {
  --astrbot-vibrancy-tint: color-mix(in srgb, var(--astrbot-chrome-color-dark, rgb(26, 26, 26)) 12%, rgba(26, 26, 26, 0.92));
}

/* Off macOS the chrome is opaque; paint the whole main background with the
   sidebar's surface color so the corner notches and the 6px gaps under and
   right of the floating card read as the same surface as the sidebar. The
   card's own background still covers the content area on top of it. */
:global(html:not([data-astrbot-desktop-platform='macos']) .v-main) {
  background: var(--astrbot-chrome-surface, rgb(var(--v-theme-surface))) !important;
}

:global(html[data-astrbot-desktop-platform='macos']),
:global(html[data-astrbot-desktop-platform='macos'] body),
:global(html[data-astrbot-desktop-platform='macos'] .v-application),
:global(html[data-astrbot-desktop-platform='macos'] .v-application__wrap) {
  background: transparent !important;
}

/* The sidebar tint lives on the main area's own background (behind everything).
   Cover the whole width, not just the sidebar column, so the card's breathing
   gaps read as the same light chrome instead of showing the raw (darker)
   window material straight through. */
:global(html[data-astrbot-desktop-platform='macos'] .v-main) {
  background: var(--astrbot-vibrancy-tint, transparent) !important;
}

/* Vuetify paints its own surface behind every list, which would sit on top of
   the sidebar's (primary-infused) chrome background, so keep the navigation
   lists transparent on every platform. */
:global(.leftSidebar .v-list),
:global(.chat-sidebar .v-list) {
  background: transparent !important;
}
</style>
