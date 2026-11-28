<script setup lang="ts">
import { computed, onMounted, onUnmounted, provide, ref, shallowReactive } from "vue";
import {
  createMemoryHistory,
  createRouter,
  RouterView,
  routeLocationKey,
  routerKey,
  routerViewLocationKey,
  viewDepthKey,
  type RouteLocationNormalizedLoaded,
} from "vue-router";
import { useDisplay } from "vuetify";
import { X } from "@lucide/vue";
import { useI18n } from "@/i18n/composables";
import MainRoutes from "@/router/MainRoutes";
import type { menu } from "./vertical-sidebar/sidebarItem";

const props = defineProps<{ item: menu }>();
const emit = defineEmits<{ close: [] }>();
const { t } = useI18n();
const { smAndDown } = useDisplay();
const open = ref(false);
const error = ref(false);
const title = computed(() => props.item.isRawTitle ? props.item.title : t(props.item.title || ""));

// Reuse the existing views and their nested tabs without changing browser history
// or the chat route. Only the dialog's descendants receive this local router.
const history = createMemoryHistory();
const dialogRouter = createRouter({
  history,
  routes: [
    ...MainRoutes.children,
    { path: "/__close_navigation_dialog__", name: "CloseNavigationDialog", component: {} },
  ],
});
const dialogRoute = {} as RouteLocationNormalizedLoaded;
for (const key of Object.keys(dialogRouter.currentRoute.value) as (keyof RouteLocationNormalizedLoaded)[]) {
  Object.defineProperty(dialogRoute, key, {
    enumerable: true,
    get: () => dialogRouter.currentRoute.value[key],
  });
}
provide(routerKey, dialogRouter);
provide(routeLocationKey, shallowReactive(dialogRoute));
provide(routerViewLocationKey, dialogRouter.currentRoute);
provide(viewDepthKey, 0);

// Run the current view's unsaved-change guards before closing, but retain the
// view until the fade finishes instead of replacing it with an empty page.
dialogRouter.beforeResolve((to) => {
  if (to.name === "CloseNavigationDialog") {
    open.value = false;
    return false;
  }
});

const locked = computed(() => {
  const path = dialogRouter.currentRoute.value.path;
  return ["/platforms", "/providers", "/config", "/settings"].includes(path)
    || path.startsWith("/plugin-view/");
});

onMounted(async () => {
  try {
    await dialogRouter.replace(props.item.to || "/welcome");
  } catch (cause) {
    console.error("Failed to load navigation dialog:", cause);
    error.value = true;
  }
  open.value = true;
});
onUnmounted(() => history.destroy());
</script>

<template>
  <v-dialog
    :model-value="open"
    width="calc(100vw - 48px)"
    max-width="1120"
    height="88dvh"
    :fullscreen="smAndDown"
    transition="fade-transition"
    content-class="chat-navigation-dialog-overlay"
    aria-labelledby="chat-navigation-dialog-title"
    @update:model-value="!$event && dialogRouter.push({ name: 'CloseNavigationDialog' })"
    @after-leave="emit('close')"
  >
    <v-card class="chat-navigation-dialog">
      <v-card-title id="chat-navigation-dialog-title" class="text-h3 pa-4 pb-0 pl-6 d-flex align-center">
        {{ title }}
        <v-spacer />
        <v-btn variant="text" icon :aria-label="t('core.actions.close')"
          @click="dialogRouter.push({ name: 'CloseNavigationDialog' })">
          <X :size="20" />
        </v-btn>
      </v-card-title>
      <div class="chat-navigation-dialog-content" :class="{ 'chat-navigation-dialog-content--locked': locked }">
        <v-alert v-if="error" type="error" variant="tonal" class="ma-4">
          {{ t('core.common.error') }}
        </v-alert>
        <RouterView v-else />
      </div>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.chat-navigation-dialog {
  height: 100%;
  min-height: 0;
  overflow: hidden;
  /* Keep fixed page actions inside the dialog, including configuration buttons. */
  transform: translateZ(0);
}
.chat-navigation-dialog > .v-card-title { flex: 0 0 auto; }
.chat-navigation-dialog-content {
  flex: 1 1 0;
  min-height: 0;
  height: 0;
  padding: 8px;
  position: relative;
  overflow: auto;
  --v-layout-left: 0px;
  --v-layout-top: 0px;
}
.chat-navigation-dialog-content--locked { overflow: hidden; }
@media (prefers-reduced-motion: reduce) {
  :global(.chat-navigation-dialog-overlay) { transition: none !important; }
}
</style>
