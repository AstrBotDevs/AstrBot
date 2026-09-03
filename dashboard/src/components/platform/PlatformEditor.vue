<template>
  <div class="bot-editor">
    <div class="bot-editor__header">
      <div class="bot-editor__headline">
        <img :src="platformIcon" class="bot-editor__icon" alt="bot logo" />
        <div class="bot-editor__headline-copy">
          <div class="bot-editor__title">{{ draft.id || platform.id }}</div>
          <div class="bot-editor__subtitle">
            {{ draft.type || platform.type }}
            <template v-if="runtimeStat?.status">
              · {{ tm(`runtimeStatus.${runtimeStat.status}`) }}
            </template>
          </div>
        </div>
      </div>

      <div class="bot-editor__actions">
        <v-btn
          v-if="runtimeStat?.error_count > 0"
          color="error"
          prepend-icon="mdi-alert-circle-outline"
          variant="text"
          rounded="xl"
          @click="$emit('show-error')"
        >
          {{ runtimeStat.error_count }} {{ tm("runtimeStatus.errors") }}
        </v-btn>
        <v-btn
          v-if="hasQrPayload"
          prepend-icon="mdi-qrcode"
          variant="text"
          rounded="xl"
          @click="$emit('show-qr')"
        >
          {{ tm("platformQr.show") }}
        </v-btn>
        <v-btn
          v-if="runtimeStat?.unified_webhook && draft.webhook_uuid"
          prepend-icon="mdi-webhook"
          variant="text"
          rounded="xl"
          @click="$emit('show-webhook', draft.webhook_uuid)"
        >
          {{ tm("viewWebhook") }}
        </v-btn>
        <v-btn
          color="primary"
          prepend-icon="mdi-content-save-outline"
          variant="tonal"
          rounded="xl"
          :loading="saving"
          :disabled="!canSave"
          @click="save"
        >
          {{ tm("workspace.save") }}
        </v-btn>
      </div>
    </div>

    <v-divider />

    <div v-if="loading" class="bot-editor__loading">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <div v-else class="bot-editor__body">
      <section class="bot-editor__section">
        <div class="bot-editor__section-head">
          <div>
            <h3 class="bot-editor__section-title">
              {{ tm("workspace.configTitle") }}
            </h3>
            <p class="bot-editor__section-description">
              {{ tm("workspace.configDescription") }}
            </p>
          </div>
          <v-btn
            size="small"
            prepend-icon="mdi-book-open-variant"
            variant="text"
            @click="openTutorial"
          >
            {{ tm("dialog.viewTutorial") }}
          </v-btn>
        </div>

        <AstrBotConfig
          :iterable="draft"
          :metadata="metadata['platform_group']?.metadata"
          metadata-key="platform"
          :is-editing="true"
        />
      </section>

      <v-divider />

      <section class="bot-editor__section bot-editor__section--routes">
        <div class="bot-editor__section-head">
          <div>
            <h3 class="bot-editor__section-title">
              {{ tm("workspace.routes.title") }}
            </h3>
            <p class="bot-editor__section-description">
              {{ tm("workspace.routes.description") }}
            </p>
          </div>
        </div>

        <v-alert
          v-if="routeLoadFailed"
          type="error"
          variant="tonal"
          class="mb-4"
        >
          {{ tm("workspace.routes.loadFailed") }}
        </v-alert>

        <div class="route-default-card">
          <div class="route-default-card__copy">
            <v-icon size="22">mdi-robot-outline</v-icon>
            <div>
              <div class="route-default-card__title">
                {{ tm("workspace.routes.defaultTitle") }}
              </div>
              <div class="route-default-card__description">
                {{ tm("workspace.routes.defaultDescription") }}
              </div>
            </div>
          </div>
          <v-select
            v-model="fallbackConfigId"
            :items="defaultConfigOptions"
            item-title="name"
            item-value="id"
            density="compact"
            variant="outlined"
            hide-details
            :disabled="!routesReady"
            class="route-default-card__select"
          />
        </div>

        <div class="route-builder">
          <div class="route-builder__copy">
            <div class="route-builder__title">
              {{ tm("workspace.routes.bindTitle") }}
            </div>
            <div class="route-builder__description">
              {{ tm("workspace.routes.bindDescription") }}
            </div>
          </div>

          <div class="route-builder__controls">
            <v-autocomplete
              v-model="pendingSessionUmo"
              :items="availableSessionUmos"
              :loading="loadingSessions"
              :label="tm('workspace.routes.sessionLabel')"
              :no-data-text="tm('workspace.routes.noSessions')"
              density="compact"
              variant="outlined"
              hide-details
              clearable
              :disabled="!routesReady"
            >
              <template #item="{ props: itemProps, item }">
                <v-list-item v-bind="itemProps">
                  <template #title>
                    <UmoDisplay
                      v-bind="getSessionDisplayProps(item.raw)"
                      compact
                      :show-info="false"
                      :show-platform="false"
                      :show-meta="false"
                      :show-raw-title="false"
                    />
                  </template>
                </v-list-item>
              </template>
              <template #selection="{ item }">
                <UmoDisplay
                  v-if="item"
                  v-bind="getSessionDisplayProps(item.raw)"
                  compact
                  :show-info="false"
                  :show-platform="false"
                  :show-meta="false"
                  :show-raw-title="false"
                />
              </template>
            </v-autocomplete>

            <v-select
              v-model="pendingConfigId"
              :items="configProfiles"
              item-title="name"
              item-value="id"
              :label="tm('workspace.routes.configLabel')"
              density="compact"
              variant="outlined"
              hide-details
              :disabled="!routesReady"
            />

            <v-btn
              color="primary"
              variant="tonal"
              prepend-icon="mdi-link-variant-plus"
              :disabled="!pendingSessionUmo || !pendingConfigId || !routesReady"
              @click="addBinding"
            >
              {{ tm("workspace.routes.bind") }}
            </v-btn>
          </div>
        </div>

        <div v-if="simpleBindings.length" class="route-bindings">
          <div class="route-bindings__head">
            <span>{{ tm("workspace.routes.boundTitle") }}</span>
            <v-chip size="x-small" variant="tonal">
              {{
                tm("workspace.routes.boundCount", {
                  count: simpleBindings.length,
                })
              }}
            </v-chip>
          </div>

          <div
            v-for="(binding, index) in simpleBindings"
            :key="binding.key"
            class="route-binding"
          >
            <div class="route-binding__session">
              <UmoDisplay
                v-bind="getSessionDisplayProps(binding.umo)"
                :show-info="false"
                :show-platform="false"
                :show-meta="false"
                :show-raw-title="false"
              />
            </div>
            <v-icon class="route-binding__arrow" size="18">
              mdi-arrow-right
            </v-icon>
            <v-select
              v-model="binding.configId"
              :items="configProfiles"
              item-title="name"
              item-value="id"
              density="compact"
              variant="outlined"
              hide-details
              class="route-binding__config"
            />
            <v-btn
              icon="mdi-delete-outline"
              size="small"
              variant="text"
              :aria-label="tm('workspace.routes.remove')"
              :title="tm('workspace.routes.remove')"
              @click="simpleBindings.splice(index, 1)"
            />
          </div>
        </div>

        <div v-else class="route-bindings-empty">
          <v-icon size="28">mdi-routes</v-icon>
          <span>{{ tm("workspace.routes.noBindings") }}</span>
        </div>

        <v-expansion-panels variant="accordion" class="route-advanced">
          <v-expansion-panel elevation="0">
            <v-expansion-panel-title>
              <div class="route-advanced__title">
                <v-icon size="18">mdi-tune-variant</v-icon>
                <span>{{ tm("workspace.routes.advanced") }}</span>
                <v-chip
                  v-if="advancedRoutes.length"
                  size="x-small"
                  variant="tonal"
                >
                  {{ advancedRoutes.length }}
                </v-chip>
              </div>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <p class="route-advanced__description">
                {{ tm("workspace.routes.advancedDescription") }}
              </p>

              <div class="route-pattern-list">
                <div
                  v-for="(route, index) in advancedRoutes"
                  :key="route.key"
                  class="route-pattern"
                >
                  <v-text-field
                    v-model="route.pattern"
                    :label="tm('workspace.routes.patternLabel')"
                    :placeholder="tm('workspace.routes.patternPlaceholder')"
                    :error-messages="getPatternError(route.pattern)"
                    density="compact"
                    variant="outlined"
                    hide-details="auto"
                    class="route-pattern__input"
                  />
                  <v-select
                    v-model="route.configId"
                    :items="configProfiles"
                    item-title="name"
                    item-value="id"
                    :label="tm('workspace.routes.configLabel')"
                    density="compact"
                    variant="outlined"
                    hide-details
                    class="route-pattern__config"
                  />
                  <div class="route-pattern__actions">
                    <v-btn
                      icon="mdi-arrow-up"
                      size="x-small"
                      variant="text"
                      :disabled="index === 0"
                      @click="moveAdvancedRoute(index, -1)"
                    />
                    <v-btn
                      icon="mdi-arrow-down"
                      size="x-small"
                      variant="text"
                      :disabled="index === advancedRoutes.length - 1"
                      @click="moveAdvancedRoute(index, 1)"
                    />
                    <v-btn
                      icon="mdi-delete-outline"
                      size="x-small"
                      variant="text"
                      @click="advancedRoutes.splice(index, 1)"
                    />
                  </div>
                </div>
              </div>

              <v-btn
                prepend-icon="mdi-plus"
                size="small"
                variant="text"
                :disabled="!routesReady"
                @click="addAdvancedRoute"
              >
                {{ tm("workspace.routes.addPattern") }}
              </v-btn>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import {
  botApi,
  configProfileApi,
  configRouteApi,
  fileApi,
  sessionApi,
} from "@/api/v1";
import AstrBotConfig from "@/components/shared/AstrBotConfig.vue";
import UmoDisplay from "@/components/shared/UmoDisplay.vue";
import { useModuleI18n } from "@/i18n/composables";
import { getPlatformIcon, getTutorialLink } from "@/utils/platformUtils";

const SYSTEM_DEFAULT_CONFIG = "__astrbot_system_default__";

const props = defineProps({
  platform: {
    type: Object,
    required: true,
  },
  metadata: {
    type: Object,
    default: () => ({}),
  },
  runtimeStat: {
    type: Object,
    default: null,
  },
  hasQrPayload: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits([
  "saved",
  "show-toast",
  "show-error",
  "show-qr",
  "show-webhook",
]);

const { tm } = useModuleI18n("features/platform");

const draft = ref({});
const originalPlatformId = ref("");
const initialConfigSnapshot = ref("");
const initialRouteSnapshot = ref("");
const loading = ref(false);
const saving = ref(false);
const routesReady = ref(false);
const routeLoadFailed = ref(false);
const loadingSessions = ref(false);
const fullRoutingTable = ref({});
const configProfiles = ref([]);
const knownSessionUmos = ref([]);
const knownSessionInfo = ref({});
const simpleBindings = ref([]);
const advancedRoutes = ref([]);
const fallbackConfigId = ref(SYSTEM_DEFAULT_CONFIG);
const pendingSessionUmo = ref(null);
const pendingConfigId = ref("default");
let routeKey = 0;
let loadVersion = 0;

const platformTemplates = computed(
  () =>
    props.metadata["platform_group"]?.metadata?.platform?.config_template || {},
);

const platformIcon = computed(() => {
  const template = findPlatformTemplate(draft.value);
  if (template?.logo_token) {
    return fileApi.tokenUrl(template.logo_token);
  }
  return getPlatformIcon(
    draft.value.type || props.platform.type || props.platform.id,
  );
});

const defaultConfigOptions = computed(() => [
  {
    id: SYSTEM_DEFAULT_CONFIG,
    name: tm("workspace.routes.systemDefault"),
  },
  ...configProfiles.value,
]);

const boundSessionSet = computed(
  () => new Set(simpleBindings.value.map((binding) => binding.umo)),
);

const availableSessionUmos = computed(() =>
  knownSessionUmos.value.filter((umo) => !boundSessionSet.value.has(umo)),
);

const currentRouteSnapshot = computed(() =>
  JSON.stringify({
    fallbackConfigId: fallbackConfigId.value,
    simpleBindings: simpleBindings.value.map(({ umo, configId }) => ({
      umo,
      configId,
    })),
    advancedRoutes: advancedRoutes.value.map(({ pattern, configId }) => ({
      pattern,
      configId,
    })),
  }),
);

const isModified = computed(
  () =>
    JSON.stringify(draft.value) !== initialConfigSnapshot.value ||
    currentRouteSnapshot.value !== initialRouteSnapshot.value,
);

const hasInvalidAdvancedRoute = computed(() =>
  advancedRoutes.value.some(
    (route) => getPatternError(route.pattern) || !route.configId,
  ),
);

const canSave = computed(
  () =>
    isModified.value &&
    !loading.value &&
    !saving.value &&
    !hasInvalidAdvancedRoute.value,
);

watch(
  () => props.platform,
  (platform) => {
    initialize(platform);
  },
  { immediate: true },
);

watch(
  () => props.platform.enable,
  (enabled) => {
    if (!draft.value || draft.value.enable === enabled) return;
    draft.value.enable = enabled;
    if (!initialConfigSnapshot.value) return;
    const initialConfig = JSON.parse(initialConfigSnapshot.value);
    initialConfig.enable = enabled;
    initialConfigSnapshot.value = JSON.stringify(initialConfig);
  },
);

function findPlatformTemplate(platform) {
  if (platform?.type && platformTemplates.value[platform.type]) {
    return platformTemplates.value[platform.type];
  }
  if (platform?.id && platformTemplates.value[platform.id]) {
    return platformTemplates.value[platform.id];
  }
  return Object.values(platformTemplates.value).find(
    (template) => template?.type === platform?.type,
  );
}

function mergeConfigWithTemplate(sourceConfig, templateConfig) {
  const clone = (value) =>
    value === undefined ? undefined : JSON.parse(JSON.stringify(value));
  const merge = (source, reference) => {
    const target = {};
    const sourceObject =
      source && typeof source === "object" && !Array.isArray(source)
        ? source
        : {};
    const referenceObject =
      reference && typeof reference === "object" && !Array.isArray(reference)
        ? reference
        : null;

    if (!referenceObject) {
      return clone(sourceObject);
    }

    for (const [key, referenceValue] of Object.entries(referenceObject)) {
      const sourceValue = sourceObject[key];
      if (
        referenceValue &&
        typeof referenceValue === "object" &&
        !Array.isArray(referenceValue)
      ) {
        target[key] = merge(sourceValue, referenceValue);
      } else if (Object.prototype.hasOwnProperty.call(sourceObject, key)) {
        target[key] = clone(sourceValue);
      } else {
        target[key] = clone(referenceValue);
      }
    }

    for (const [key, value] of Object.entries(sourceObject)) {
      if (!Object.prototype.hasOwnProperty.call(referenceObject, key)) {
        target[key] = clone(value);
      }
    }
    return target;
  };

  return merge(sourceConfig, templateConfig);
}

async function initialize(platform) {
  const version = ++loadVersion;
  loading.value = true;
  routesReady.value = false;
  routeLoadFailed.value = false;
  originalPlatformId.value = platform?.id || "";
  const platformCopy = JSON.parse(JSON.stringify(platform || {}));
  const template = findPlatformTemplate(platformCopy);
  draft.value = template
    ? mergeConfigWithTemplate(platformCopy, template)
    : platformCopy;
  simpleBindings.value = [];
  advancedRoutes.value = [];
  fallbackConfigId.value = SYSTEM_DEFAULT_CONFIG;
  pendingSessionUmo.value = null;

  const [profilesResult, routesResult] = await Promise.allSettled([
    configProfileApi.list(),
    configRouteApi.list(),
  ]);
  if (version !== loadVersion) return;

  if (profilesResult.status === "fulfilled") {
    configProfiles.value = profilesResult.value.data.data.info_list || [];
    if (
      !configProfiles.value.some(
        (profile) => profile.id === pendingConfigId.value,
      )
    ) {
      pendingConfigId.value = configProfiles.value[0]?.id || "";
    }
  } else {
    configProfiles.value = [];
    showError(profilesResult.reason);
  }

  if (routesResult.status === "fulfilled") {
    fullRoutingTable.value = routesResult.value.data.data.routing || {};
    loadBotRoutes(originalPlatformId.value);
    routesReady.value = true;
  } else {
    fullRoutingTable.value = {};
    routeLoadFailed.value = true;
  }

  loadingSessions.value = true;
  try {
    const sessionsResponse = await sessionApi.activeUmos();
    if (version === loadVersion && sessionsResponse.data.status === "ok") {
      knownSessionUmos.value = (sessionsResponse.data.data?.umos || []).filter(
        (umo) => parseUmo(umo)?.platform === originalPlatformId.value,
      );
      knownSessionInfo.value = Object.fromEntries(
        (sessionsResponse.data.data?.umo_infos || [])
          .filter((info) => info?.umo)
          .map((info) => [info.umo, info]),
      );
    }
  } catch (error) {
    if (version === loadVersion) {
      knownSessionUmos.value = [];
      knownSessionInfo.value = {};
    }
  } finally {
    if (version === loadVersion) {
      loadingSessions.value = false;
    }
  }

  if (version !== loadVersion) return;
  initialConfigSnapshot.value = JSON.stringify(draft.value);
  initialRouteSnapshot.value = currentRouteSnapshot.value;
  loading.value = false;
}

function loadBotRoutes(platformId) {
  let fallbackFound = false;
  for (const [pattern, configId] of Object.entries(fullRoutingTable.value)) {
    const parsed = parseUmo(pattern);
    if (!parsed || parsed.platform !== platformId) continue;

    if (!fallbackFound && isBotFallbackPattern(parsed)) {
      fallbackConfigId.value = configId;
      fallbackFound = true;
      continue;
    }

    if (isExactSessionPattern(parsed)) {
      simpleBindings.value.push({
        key: `session-${routeKey++}`,
        umo: pattern,
        configId,
      });
      continue;
    }

    advancedRoutes.value.push({
      key: `pattern-${routeKey++}`,
      pattern,
      configId,
    });
  }
}

function parseUmo(umo) {
  if (typeof umo !== "string") return null;
  const firstSeparator = umo.indexOf(":");
  if (firstSeparator === -1) return null;
  const secondSeparator = umo.indexOf(":", firstSeparator + 1);
  if (secondSeparator === -1) return null;
  return {
    platform: umo.slice(0, firstSeparator),
    messageType: umo.slice(firstSeparator + 1, secondSeparator),
    sessionId: umo.slice(secondSeparator + 1),
  };
}

function hasGlob(value) {
  return value.includes("*") || value.includes("?") || value.includes("[");
}

function isBotFallbackPattern(parsed) {
  return (
    ["", "*"].includes(parsed.messageType) &&
    ["", "*"].includes(parsed.sessionId)
  );
}

function isExactSessionPattern(parsed) {
  return !hasGlob(parsed.messageType) && !hasGlob(parsed.sessionId);
}

function getSessionDisplayProps(umo) {
  const parsed = parseUmo(umo) || {};
  const info = knownSessionInfo.value[umo] || {};
  const messageType = info.message_type || parsed.messageType || "";
  const sessionId = info.session_id || parsed.sessionId || umo;
  let sessionType = tm("workspace.routes.sessionTypes.other");
  if (["GroupMessage", "group"].includes(messageType)) {
    sessionType = tm("workspace.routes.sessionTypes.group");
  } else if (
    ["FriendMessage", "PrivateMessage", "friend", "private"].includes(
      messageType,
    )
  ) {
    sessionType = tm("workspace.routes.sessionTypes.friend");
  }
  return {
    umo,
    platform: info.platform || parsed.platform || "",
    messageType,
    sessionId,
    autoName: info.auto_name || "",
    userAlias: info.user_alias || "",
    customName:
      info.auto_name || info.user_alias ? "" : `${sessionType} · ${sessionId}`,
  };
}

function addBinding() {
  if (!pendingSessionUmo.value || !pendingConfigId.value) return;
  simpleBindings.value.push({
    key: `session-${routeKey++}`,
    umo: pendingSessionUmo.value,
    configId: pendingConfigId.value,
  });
  pendingSessionUmo.value = null;
}

function addAdvancedRoute() {
  const platformId = draft.value.id || originalPlatformId.value;
  advancedRoutes.value.push({
    key: `pattern-${routeKey++}`,
    pattern: `${platformId}:GroupMessage:*`,
    configId:
      configProfiles.value.find((profile) => profile.id === "default")?.id ||
      configProfiles.value[0]?.id ||
      "",
  });
}

function moveAdvancedRoute(index, offset) {
  const targetIndex = index + offset;
  if (targetIndex < 0 || targetIndex >= advancedRoutes.value.length) return;
  const routes = [...advancedRoutes.value];
  [routes[index], routes[targetIndex]] = [routes[targetIndex], routes[index]];
  advancedRoutes.value = routes;
}

function getPatternError(pattern) {
  if (!pattern) return tm("workspace.routes.patternRequired");
  const parsed = parseUmo(pattern);
  if (!parsed) return tm("workspace.routes.patternInvalid");
  const validPlatformIds = new Set([
    originalPlatformId.value,
    draft.value.id || originalPlatformId.value,
  ]);
  if (!validPlatformIds.has(parsed.platform)) {
    return tm("workspace.routes.patternPlatformMismatch");
  }
  return "";
}

function rewritePatternPlatform(pattern, targetPlatformId) {
  const parsed = parseUmo(pattern);
  if (!parsed) return pattern;
  return `${targetPlatformId}:${parsed.messageType}:${parsed.sessionId}`;
}

async function save() {
  if (!canSave.value) return;
  saving.value = true;
  try {
    const oldPlatformId = originalPlatformId.value;
    const newPlatformId = draft.value.id || oldPlatformId;
    let nextRoutingTable = null;
    if (routesReady.value) {
      const retainedEntries = Object.entries(fullRoutingTable.value).filter(
        ([pattern]) => {
          const parsed = parseUmo(pattern);
          return (
            !parsed || ![oldPlatformId, newPlatformId].includes(parsed.platform)
          );
        },
      );
      const botEntries = [];
      const routePatterns = new Set();

      for (const binding of simpleBindings.value) {
        if (!binding.configId) continue;
        const pattern = rewritePatternPlatform(binding.umo, newPlatformId);
        if (routePatterns.has(pattern)) {
          throw new Error(tm("workspace.routes.duplicatePattern"));
        }
        routePatterns.add(pattern);
        botEntries.push([pattern, binding.configId]);
      }

      for (const route of advancedRoutes.value) {
        const pattern = rewritePatternPlatform(route.pattern, newPlatformId);
        if (routePatterns.has(pattern)) {
          throw new Error(tm("workspace.routes.duplicatePattern"));
        }
        routePatterns.add(pattern);
        botEntries.push([pattern, route.configId]);
      }

      if (fallbackConfigId.value !== SYSTEM_DEFAULT_CONFIG) {
        const pattern = `${newPlatformId}:*:*`;
        if (routePatterns.has(pattern)) {
          throw new Error(tm("workspace.routes.duplicatePattern"));
        }
        botEntries.push([pattern, fallbackConfigId.value]);
      }

      nextRoutingTable = Object.fromEntries([
        ...botEntries,
        ...retainedEntries,
      ]);
    }

    const response = await botApi.update(oldPlatformId, draft.value);
    if (response.data.status === "error") {
      throw new Error(
        response.data.message || tm("messages.platformUpdateFailed"),
      );
    }

    if (nextRoutingTable) {
      await configRouteApi.replace({ routing: nextRoutingTable });
      fullRoutingTable.value = nextRoutingTable;
    }

    initialConfigSnapshot.value = JSON.stringify(draft.value);
    initialRouteSnapshot.value = currentRouteSnapshot.value;
    showSuccess(response.data.message || tm("messages.updateSuccess"));
    emit("saved", newPlatformId);
  } catch (error) {
    showError(error);
  } finally {
    saving.value = false;
  }
}

function openTutorial() {
  window.open(getTutorialLink(draft.value.type), "_blank");
}

function showSuccess(message) {
  emit("show-toast", { message, type: "success" });
}

function showError(error) {
  const message =
    error?.response?.data?.message || error?.message || String(error);
  emit("show-toast", { message, type: "error" });
}
</script>

<style scoped>
.bot-editor {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.bot-editor__header {
  align-items: flex-start;
  background: rgb(var(--v-theme-surface));
  display: flex;
  flex: 0 0 auto;
  gap: 16px;
  justify-content: space-between;
  padding: 18px 22px 14px;
  position: relative;
  z-index: 1;
}

.bot-editor__headline {
  align-items: center;
  display: flex;
  gap: 12px;
  min-width: 0;
}

.bot-editor__icon {
  flex: 0 0 auto;
  height: 40px;
  object-fit: contain;
  width: 40px;
}

.bot-editor__headline-copy {
  min-width: 0;
}

.bot-editor__title {
  font-size: 21px;
  font-weight: 680;
  letter-spacing: -0.03em;
  line-height: 1.15;
  overflow-wrap: anywhere;
}

.bot-editor__subtitle {
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-size: 13px;
  line-height: 1.5;
  margin-top: 5px;
  overflow-wrap: anywhere;
}

.bot-editor__actions {
  align-items: center;
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: flex-end;
}

.bot-editor__loading {
  align-items: center;
  display: flex;
  flex: 1;
  justify-content: center;
}

.bot-editor__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.bot-editor__section {
  padding: 20px 22px;
}

.bot-editor__section-head {
  align-items: flex-start;
  display: flex;
  gap: 16px;
  justify-content: space-between;
  margin-bottom: 16px;
}

.bot-editor__section-title {
  font-size: 16px;
  font-weight: 650;
  line-height: 1.4;
  margin: 0;
}

.bot-editor__section-description {
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-size: 13px;
  line-height: 1.5;
  margin: 4px 0 0;
}

.route-default-card {
  align-items: center;
  background: rgba(var(--v-theme-on-surface), 0.035);
  border-radius: 12px;
  display: flex;
  gap: 20px;
  justify-content: space-between;
  padding: 14px 16px;
}

.route-default-card__copy {
  align-items: center;
  display: flex;
  gap: 12px;
  min-width: 0;
}

.route-default-card__title,
.route-builder__title {
  font-size: 14px;
  font-weight: 600;
}

.route-default-card__description,
.route-builder__description {
  color: rgba(var(--v-theme-on-surface), 0.56);
  font-size: 12px;
  line-height: 1.5;
  margin-top: 3px;
}

.route-default-card__select {
  flex: 0 1 280px;
  min-width: 220px;
}

.route-builder {
  margin-top: 22px;
}

.route-builder__controls {
  align-items: center;
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(220px, 1fr) minmax(180px, 260px) auto;
  margin-top: 12px;
}

.route-bindings {
  margin-top: 22px;
}

.route-bindings__head {
  align-items: center;
  display: flex;
  font-size: 13px;
  font-weight: 600;
  gap: 8px;
  margin-bottom: 8px;
}

.route-binding {
  align-items: center;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.07);
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(180px, 1fr) auto minmax(180px, 240px) auto;
  min-height: 62px;
  padding: 9px 4px;
}

.route-binding__session {
  min-width: 0;
}

.route-binding__arrow {
  color: rgba(var(--v-theme-on-surface), 0.38);
}

.route-binding__config {
  min-width: 0;
}

.route-bindings-empty {
  align-items: center;
  color: rgba(var(--v-theme-on-surface), 0.52);
  display: flex;
  font-size: 13px;
  gap: 10px;
  justify-content: center;
  margin-top: 18px;
  min-height: 82px;
  padding: 16px;
  text-align: center;
}

.route-advanced {
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.07);
  margin-top: 18px;
}

.route-advanced :deep(.v-expansion-panel) {
  background: transparent;
}

.route-advanced :deep(.v-expansion-panel-title) {
  min-height: 52px;
  padding-inline: 4px;
}

.route-advanced :deep(.v-expansion-panel-text__wrapper) {
  padding: 0 4px 12px;
}

.route-advanced__title {
  align-items: center;
  display: flex;
  font-size: 13px;
  font-weight: 600;
  gap: 8px;
}

.route-advanced__description {
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-size: 12px;
  line-height: 1.6;
  margin: 0 0 14px;
}

.route-pattern-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 8px;
}

.route-pattern {
  align-items: flex-start;
  display: grid;
  gap: 8px;
  grid-template-columns: minmax(220px, 1fr) minmax(180px, 240px) auto;
}

.route-pattern__actions {
  align-items: center;
  display: flex;
  min-height: 40px;
}

@media (max-width: 960px) {
  .bot-editor__header {
    align-items: stretch;
    flex-direction: column;
    padding: 16px;
  }

  .bot-editor__actions {
    justify-content: flex-start;
  }

  .bot-editor__section {
    padding: 18px 16px;
  }

  .route-builder__controls {
    grid-template-columns: 1fr;
  }

  .route-builder__controls :deep(.v-btn) {
    width: 100%;
  }
}

@media (max-width: 600px) {
  .bot-editor__actions {
    align-items: stretch;
    flex-direction: column;
  }

  .bot-editor__actions :deep(.v-btn) {
    width: 100%;
  }

  .bot-editor__section-head,
  .route-default-card {
    align-items: stretch;
    flex-direction: column;
  }

  .route-default-card__select {
    flex-basis: auto;
    min-width: 0;
  }

  .route-binding,
  .route-pattern {
    grid-template-columns: 1fr;
  }

  .route-binding__arrow {
    display: none;
  }

  .route-pattern__actions {
    justify-content: flex-end;
  }
}
</style>
