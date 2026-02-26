<script setup lang="ts">
import { ref, computed, inject, watch } from "vue";
import { useCustomizerStore } from "@/stores/customizer";
import { useModuleI18n } from "@/i18n/composables";
import { getPlatformDisplayName, getPlatformIcon } from "@/utils/platformUtils";
import UninstallConfirmDialog from "./UninstallConfirmDialog.vue";
import PluginPlatformChip from "./PluginPlatformChip.vue";
import StyledMenu from "./StyledMenu.vue";
import defaultPluginIcon from "@/assets/images/plugin_icon.png";

const props = defineProps({
  extension: {
    type: Object,
    required: true,
  },
  marketMode: {
    type: Boolean,
    default: false,
  },
  highlight: {
    type: Boolean,
    default: false,
  },
});

// 定义要发送到父组件的事件
const emit = defineEmits([
  "configure",
  "update",
  "reload",
  "install",
  "uninstall",
  "toggle-activation",
  "view-handlers",
  "view-readme",
  "view-changelog",
]);

const reveal = ref(false);
const showUninstallDialog = ref(false);

// 国际化
const { tm } = useModuleI18n("features/extension");

const supportPlatforms = computed(() => {
  const platforms = props.extension?.support_platforms;
  if (!Array.isArray(platforms)) {
    return [];
  }
  return platforms.filter((item) => typeof item === "string");
});

const supportPlatformDisplayNames = computed(() =>
  supportPlatforms.value.map((platformId) => getPlatformDisplayName(platformId)),
);

const astrbotVersionRequirement = computed(() => {
  const versionSpec = props.extension?.astrbot_version;
  return typeof versionSpec === "string" && versionSpec.trim().length
    ? versionSpec.trim()
    : "";
});

const logoLoadFailed = ref(false);

const logoSrc = computed(() => {
  const logo = props.extension?.logo;
  if (logoLoadFailed.value) {
    return defaultPluginIcon;
  }
  return typeof logo === "string" && logo.trim().length
    ? logo
    : defaultPluginIcon;
});

watch(
  () => props.extension?.logo,
  () => {
    logoLoadFailed.value = false;
  },
);

// 操作函数
const configure = () => {
  emit("configure", props.extension);
};

const updateExtension = () => {
  emit("update", props.extension);
};

const reloadExtension = () => {
  emit("reload", props.extension);
};

const $confirm = inject("$confirm");

const installExtension = async () => {
  emit("install", props.extension);
};

const uninstallExtension = async () => {
  showUninstallDialog.value = true;
};

const handleUninstallConfirm = (options: {
  deleteConfig: boolean;
  deleteData: boolean;
}) => {
  emit("uninstall", props.extension, options);
};

const toggleActivation = () => {
  emit("toggle-activation", props.extension);
};

const viewHandlers = () => {
  emit("view-handlers", props.extension);
};

const viewReadme = () => {
  emit("view-readme", props.extension);
};

const viewChangelog = () => {
  emit("view-changelog", props.extension);
};

</script>

<template>
  <v-card
    class="mx-auto d-flex flex-column h-100"
    elevation="0"
    height="100%"
    :style="{
      position: 'relative',
      backgroundColor:
        useCustomizerStore().uiTheme === 'PurpleTheme'
          ? marketMode
            ? '#f8f0dd'
            : '#ffffff'
          : '#282833',
      color:
        useCustomizerStore().uiTheme === 'PurpleTheme'
          ? '#000000dd'
          : '#ffffff',
    }"
  >
    <v-card-text
      style="
        padding: 16px;
        padding-bottom: 0px;
        width: 100%;
      "
    >
      <div style="overflow-x: auto; width: 100%">
        <div style="width: 100%; margin-bottom: 24px">
          <div class="extension-title-row">
            <p
              class="text-h3 font-weight-black extension-title"
              :class="{ 'text-h4': $vuetify.display.xs }"
            >
              <v-tooltip
                location="top"
                :text="
                  extension.display_name?.length &&
                  extension.display_name !== extension.name
                    ? `${extension.display_name} (${extension.name})`
                    : extension.name
                "
              >
                <template v-slot:activator="{ props: titleTooltipProps }">
                  <span v-bind="titleTooltipProps" class="extension-title__text">{{
                    extension.display_name?.length
                      ? extension.display_name
                      : extension.name
                  }}</span>
                </template>
              </v-tooltip>
              <v-tooltip
                location="top"
                v-if="extension?.has_update && !marketMode"
              >
                <template v-slot:activator="{ props: tooltipProps }">
                  <v-icon
                    v-bind="tooltipProps"
                    color="warning"
                    class="ml-2"
                    icon="mdi-update"
                    size="small"
                  ></v-icon>
                </template>
                <span
                  >{{ tm("card.status.hasUpdate") }}:
                  {{ extension.online_version }}</span
                >
              </v-tooltip>
              <v-tooltip
                location="top"
                v-if="!extension.activated && !marketMode"
              >
                <template v-slot:activator="{ props: tooltipProps }">
                  <v-icon
                    v-bind="tooltipProps"
                    color="error"
                    class="ml-2"
                    icon="mdi-cancel"
                    size="small"
                  ></v-icon>
                </template>
                <span>{{ tm("card.status.disabled") }}</span>
              </v-tooltip>
            </p>

            <template v-if="!marketMode">
              <v-tooltip location="left">
                <template v-slot:activator="{ props: tooltipProps }">
                  <div v-bind="tooltipProps" class="extension-switch-wrap" @click.stop>
                    <v-switch
                      :model-value="extension.activated"
                      color="success"
                      density="compact"
                      hide-details
                      inset
                      @update:model-value="toggleActivation"
                    ></v-switch>
                  </div>
                </template>
                <span>{{
                  extension.activated ? tm("buttons.disable") : tm("buttons.enable")
                }}</span>
              </v-tooltip>
            </template>
            <template v-else>
              <div class="extension-market-menu-wrap">
                <v-menu offset-y>
                  <template v-slot:activator="{ props: menuProps }">
                    <v-btn
                      icon
                      variant="text"
                      aria-label="more"
                      v-if="extension?.repo"
                      :href="extension?.repo"
                      target="_blank"
                    >
                      <v-icon icon="mdi-github"></v-icon>
                    </v-btn>
                    <v-btn v-bind="menuProps" icon variant="text" aria-label="more">
                      <v-icon icon="mdi-dots-vertical"></v-icon>
                    </v-btn>
                  </template>

                  <v-list>
                    <v-list-item @click="viewReadme">
                      <v-list-item-title
                        >📄 {{ tm("buttons.viewDocs") }}</v-list-item-title
                      >
                    </v-list-item>

                    <v-list-item
                      v-if="marketMode && !extension?.installed"
                      @click="installExtension"
                    >
                      <v-list-item-title>
                        {{ tm("buttons.install") }}</v-list-item-title
                      >
                    </v-list-item>

                    <v-list-item v-if="marketMode && extension?.installed">
                      <v-list-item-title class="text--disabled">{{
                        tm("status.installed")
                      }}</v-list-item-title>
                    </v-list-item>
                  </v-list>
                </v-menu>
              </div>
            </template>
          </div>

          <div class="extension-content-row mt-2">
            <div class="extension-image-container">
              <img
                :src="logoSrc"
                :alt="extension.name"
                class="extension-logo"
                @error="logoLoadFailed = true"
              />
            </div>

            <div class="extension-meta-group">
              <div class="extension-chip-group d-flex flex-wrap">
                <v-chip color="primary" label size="small">
                  <v-icon icon="mdi-source-branch" start></v-icon>
                  {{ extension.version }}
                </v-chip>
                <v-chip
                  v-if="extension?.has_update"
                  color="warning"
                  label
                  size="small"
                >
                  <v-icon icon="mdi-arrow-up-bold" start></v-icon>
                  {{ extension.online_version }}
                </v-chip>
                <v-chip
                  v-if="extension.handlers?.length"
                  color="primary"
                  label
                  size="small"
                  @click="viewHandlers"
                  style="cursor: pointer"
                >
                  <v-icon icon="mdi-cogs" start></v-icon>
                  {{ extension.handlers?.length
                  }}{{ tm("card.status.handlersCount") }}
                </v-chip>
                <v-chip
                  v-for="tag in extension.tags"
                  :key="tag"
                  :color="tag === 'danger' ? 'error' : 'primary'"
                  label
                  size="small"
                >
                  {{ tag === "danger" ? tm("tags.danger") : tag }}
                </v-chip>
                <PluginPlatformChip :platforms="supportPlatforms" />
                <v-chip
                  v-if="astrbotVersionRequirement"
                  color="secondary"
                  variant="outlined"
                  label
                  size="small"
                >
                  AstrBot: {{ astrbotVersionRequirement }}
                </v-chip>
              </div>

              <div
                class="extension-desc"
                :class="{ 'text-caption': $vuetify.display.xs }"
              >
                {{ extension.desc }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </v-card-text>

    <v-card-actions class="extension-actions" @click.stop>
      <template v-if="!marketMode">
        <v-spacer></v-spacer>
        <v-tooltip location="top" :text="tm('buttons.viewDocs')">
          <template v-slot:activator="{ props: actionProps }">
            <v-btn
              v-bind="actionProps"
              icon="mdi-book-open-page-variant"
              size="small"
              variant="tonal"
              color="info"
              @click="viewReadme"
            ></v-btn>
          </template>
        </v-tooltip>

        <v-tooltip location="top" :text="tm('card.actions.pluginConfig')">
          <template v-slot:activator="{ props: actionProps }">
            <v-btn
              v-bind="actionProps"
              icon="mdi-cog"
              size="small"
              variant="tonal"
              color="primary"
              @click="configure"
            ></v-btn>
          </template>
        </v-tooltip>

        <v-tooltip v-if="extension?.repo" location="top" :text="tm('buttons.viewRepo')">
          <template v-slot:activator="{ props: actionProps }">
            <v-btn
              v-bind="actionProps"
              icon="mdi-github"
              size="small"
              variant="tonal"
              color="secondary"
              :href="extension.repo"
              target="_blank"
            ></v-btn>
          </template>
        </v-tooltip>

        <v-tooltip location="top" :text="tm('card.actions.reloadPlugin')">
          <template v-slot:activator="{ props: actionProps }">
            <v-btn
              v-bind="actionProps"
              icon="mdi-refresh"
              size="small"
              variant="tonal"
              color="primary"
              @click="reloadExtension"
            ></v-btn>
          </template>
        </v-tooltip>

        <StyledMenu location="top end" offset="8">
          <template #activator="{ props: menuProps }">
            <v-btn
              v-bind="menuProps"
              icon="mdi-dots-horizontal"
              size="small"
              variant="tonal"
              color="secondary"
            ></v-btn>
          </template>

          <v-list-item class="styled-menu-item" prepend-icon="mdi-information" @click="viewHandlers">
            <v-list-item-title>{{ tm("buttons.viewInfo") }}</v-list-item-title>
          </v-list-item>

          <v-list-item class="styled-menu-item" prepend-icon="mdi-update" @click="updateExtension">
            <v-list-item-title>{{
              extension.has_update
                ? tm("card.actions.updateTo") + " " + extension.online_version
                : tm("card.actions.reinstall")
            }}</v-list-item-title>
          </v-list-item>

          <v-list-item class="styled-menu-item" prepend-icon="mdi-delete" @click="uninstallExtension">
            <v-list-item-title class="text-error">{{ tm("card.actions.uninstallPlugin") }}</v-list-item-title>
          </v-list-item>
        </StyledMenu>
      </template>
      <template v-else>
        <v-btn color="primary" size="small" @click="viewReadme">
          {{ tm("buttons.viewDocs") }}
        </v-btn>
      </template>
    </v-card-actions>
  </v-card>

  <!-- 卸载确认对话框 -->
  <UninstallConfirmDialog
    v-model="showUninstallDialog"
    @confirm="handleUninstallConfirm"
  />
</template>

<style scoped>
.extension-image-container {
  display: flex;
  align-items: flex-start;
  flex-shrink: 0;
}

.extension-logo {
  width: 72px;
  height: 72px;
  border-radius: 12px;
  object-fit: cover;
}

.extension-content-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.extension-meta-group {
  flex: 1;
  min-width: 0;
}

.extension-chip-group {
  gap: 8px;
}

.extension-desc {
  margin-top: 8px;
  font-size: 90%;
  overflow-y: auto;
  height: 70px;
}

.extension-title {
  display: flex;
  align-items: center;
  min-width: 0;
  flex: 1;
  margin: 0;
}

.extension-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.extension-title__text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.extension-switch-wrap {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.extension-switch-wrap :deep(.v-switch) {
  margin: 0;
}

.extension-market-menu-wrap {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

@media (max-width: 600px) {
  .extension-content-row {
    flex-direction: column;
  }

  .extension-logo {
    width: 64px;
    height: 64px;
  }
}

.extension-actions {
  margin-top: auto;
  gap: 8px;
  justify-content: flex-end;
}
</style>
