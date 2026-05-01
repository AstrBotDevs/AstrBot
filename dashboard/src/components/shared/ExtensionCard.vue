<script setup lang="ts">
import { ref, computed, watch, useAttrs } from "vue";
import { useCustomizerStore } from "@/stores/customizer";
import { useModuleI18n } from "@/i18n/composables";
import UninstallConfirmDialog from "./UninstallConfirmDialog.vue";
import PluginPlatformChip from "./PluginPlatformChip.vue";
import StyledMenu from "./StyledMenu.vue";
import defaultPluginIcon from "@/assets/images/plugin_icon.png";
import { usePluginI18n } from "@/utils/pluginI18n";

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
  isPinned: {
    type: Boolean,
    default: false,
  },
});

// 定义要发送到父组件的事件
const emit = defineEmits([
  "configure",
  "update",
  "reload",
  "uninstall",
  "toggle-activation",
  "view-handlers",
  "view-readme",
  "view-changelog",
  "toggle-pin",
]);

const showUninstallDialog = ref(false);

const attrs = useAttrs();

// 国际化
const { tm } = useModuleI18n("features/extension");
const { pluginName, pluginDesc } = usePluginI18n();

const supportPlatforms = computed(() => {
  const platforms = props.extension?.support_platforms;
  if (!Array.isArray(platforms)) {
    return [];
  }
  return platforms.filter((item) => typeof item === "string");
});

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

const localizedName = computed(() => pluginName(props.extension));

const localizedDesc = computed(() => pluginDesc(props.extension));

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

const togglePin = () => {
  emit("toggle-pin", props.extension);
};

</script>

<template>
  <v-card
    v-bind="attrs"
    class="extension-card mx-auto d-flex flex-column h-100"
    elevation="0"
    height="100%"
    :ripple="false"
    variant="outlined"
    :style="{
      position: 'relative',
      backgroundColor:
        useCustomizerStore().uiTheme === 'PurpleTheme'
          ? marketMode
            ? '#f8f0dd'
            : '#ffffff'
          : marketMode
            ? '#3a3425'
            : '#282833',
      color:
        useCustomizerStore().uiTheme === 'PurpleTheme'
          ? '#000000dd'
          : '#ffffffdd',
    }"
  >
    <v-card-text class="extension-card-text">
      <div class="extension-content-row">
        <div class="extension-image-container">
          <img
            :src="logoSrc"
            :alt="extension.name"
            class="extension-logo"
            @error="logoLoadFailed = true"
          />
        </div>

        <div class="extension-meta-group">
          <div class="extension-title-row">
            <p
              class="text-h3 font-weight-black extension-title"
              :class="{ 'text-h4': $vuetify.display.xs }"
            >
              <v-tooltip
                location="top"
                :text="
                  localizedName?.length &&
                  localizedName !== extension.name
                    ? `${localizedName} (${extension.name})`
                    : extension.name
                "
              >
                <template v-slot:activator="{ props: titleTooltipProps }">
                  <span v-bind="titleTooltipProps" class="extension-title__text">{{
                    localizedName
                  }}</span>
                </template>
              </v-tooltip>
              <span v-if="extension.version" class="extension-version">
                {{ extension.version }}
              </span>
              <v-chip
                v-if="extension.reserved"
                color="primary"
                size="x-small"
                class="extension-system-chip"
              >
                {{ tm("status.system") }}
              </v-chip>
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
                    style="cursor: pointer"
                    @click.stop="updateExtension"
                  ></v-icon>
                </template>
                <span
                  >{{ tm("card.status.hasUpdate") }}:
                  {{ extension.online_version }}</span
                >
              </v-tooltip>
            </p>

            <template v-if="!marketMode">
              <v-tooltip location="left">
                <template v-slot:activator="{ props: tooltipProps }">
                  <div class="extension-switch-wrap" @click.stop>
                    <div
                      v-bind="tooltipProps"
                      style="display: inline-flex; align-items: center"
                    >
                      <v-switch
                        :model-value="extension.activated"
                        color="success"
                        density="compact"
                        hide-details
                        inset
                        @update:model-value="toggleActivation"
                      ></v-switch>
                    </div>
                  </div>
                </template>
                <span>{{
                  extension.activated ? tm("buttons.disable") : tm("buttons.enable")
                }}</span>
              </v-tooltip>
            </template>
          </div>

          <div class="extension-chip-group d-flex flex-wrap">
            <v-chip
              v-if="extension?.has_update"
              color="warning"
              label
              size="small"
              style="cursor: pointer"
              @click.stop="updateExtension"
            >
              <v-icon icon="mdi-arrow-up-bold" start></v-icon>
              {{ extension.online_version }}
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
            {{ localizedDesc }}
          </div>
        </div>
      </div>
    </v-card-text>

    <v-card-actions class="extension-actions" @click.stop>
      <template v-if="!marketMode">
        <v-spacer></v-spacer>
        <v-tooltip location="top">
          <template v-slot:activator="{ props: pinTooltipProps }">
            <v-btn
              v-bind="pinTooltipProps"
              :aria-label="isPinned ? tm('buttons.unpin') : tm('buttons.pin')"
              :color="isPinned ? 'primary' : 'secondary'"
              :icon="isPinned ? 'mdi-pin' : 'mdi-pin-outline'"
              size="small"
              variant="tonal"
              class="extension-pin-btn"
              @click="togglePin"
            ></v-btn>
          </template>
          <span>{{ isPinned ? tm("buttons.unpin") : tm("buttons.pin") }}</span>
        </v-tooltip>

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
.extension-card-text {
  padding: 12px 14px 8px;
  width: 100%;
}

.extension-card {
  cursor: pointer;
}

.extension-image-container {
  display: flex;
  align-items: flex-start;
  flex-shrink: 0;
}

.extension-logo {
  width: 64px;
  height: 64px;
  border-radius: 10px;
  object-fit: cover;
}

.extension-content-row {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.extension-meta-group {
  flex: 1;
  min-width: 0;
}

.extension-chip-group {
  gap: 6px;
}

.extension-desc {
  margin-top: 6px;
  font-size: 90%;
  display: -webkit-box;
  line-clamp: 2;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
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

.extension-version {
  color: rgba(var(--v-theme-on-surface), 0.48);
  flex-shrink: 0;
  font-size: 0.875rem;
  font-weight: 500;
  margin-left: 10px;
  white-space: nowrap;
}

.extension-system-chip {
  flex-shrink: 0;
  margin-left: 8px;
}

.extension-switch-wrap {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.extension-pin-btn {
  flex-shrink: 0;
}

.extension-switch-wrap :deep(.v-switch) {
  margin: 0;
}

@media (max-width: 600px) {
  .extension-content-row {
    gap: 10px;
  }

  .extension-logo {
    width: 52px;
    height: 52px;
  }
}

.extension-actions {
  margin-top: auto;
  gap: 6px;
  justify-content: flex-end;
  min-height: 42px;
  padding: 0 12px 10px;
}
</style>
