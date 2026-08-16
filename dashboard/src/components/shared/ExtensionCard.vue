<script setup lang="ts">
import { ref, computed, watch, useAttrs } from 'vue';
import { useDisplay } from 'vuetify';
import { useModuleI18n } from '@/i18n/composables';
import UninstallConfirmDialog from './UninstallConfirmDialog.vue';
import PluginPlatformChip from './PluginPlatformChip.vue';
import StyledMenu from './StyledMenu.vue';
import defaultPluginIcon from '/favicon.svg';
import { usePluginI18n } from '@/utils/pluginI18n';

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
  'configure',
  'update',
  'reload',
  'uninstall',
  'toggle-activation',
  'view-handlers',
  'view-readme',
  'view-changelog',
  'toggle-pin',
]);

const showUninstallDialog = ref(false);

const attrs = useAttrs();

// 国际化
const { tm } = useModuleI18n('features/extension');
const { pluginName, pluginDesc } = usePluginI18n();
const { xs } = useDisplay();

const supportPlatforms = computed(() => {
  const platforms = props.extension?.support_platforms;
  if (!Array.isArray(platforms)) {
    return [];
  }
  return platforms.filter((item) => typeof item === 'string');
});

const astrbotVersionRequirement = computed(() => {
  const versionSpec = props.extension?.astrbot_version;
  return typeof versionSpec === 'string' && versionSpec.trim().length
    ? versionSpec.trim()
    : '';
});

const logoLoadFailed = ref(false);

const logoSrc = computed(() => {
  const logo = props.extension?.logo;
  if (logoLoadFailed.value) {
    return defaultPluginIcon;
  }
  return typeof logo === 'string' && logo.trim().length
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
  emit('configure', props.extension);
};

const updateExtension = () => {
  emit('update', props.extension);
};

const reloadExtension = () => {
  emit('reload', props.extension);
};

const uninstallExtension = async () => {
  showUninstallDialog.value = true;
};

const handleUninstallConfirm = (options: {
  deleteConfig: boolean;
  deleteData: boolean;
}) => {
  emit('uninstall', props.extension, options);
};

const toggleActivation = () => {
  emit('toggle-activation', props.extension);
};

const viewHandlers = () => {
  emit('view-handlers', props.extension);
};

const viewReadme = () => {
  emit('view-readme', props.extension);
};

const togglePin = () => {
  emit('toggle-pin', props.extension);
};
</script>

<template>
  <v-card
    v-bind="attrs"
    class="extension-card surface mx-auto d-flex flex-column h-100"
    :class="{ 'extension-card--market': marketMode }"
    elevation="0"
    height="100%"
    :ripple="false"
    variant="outlined"
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
              class="extension-title"
              :class="{ 'extension-title--compact': xs }"
            >
              <v-tooltip
                location="top"
                :text="
                  localizedName?.length && localizedName !== extension.name
                    ? `${localizedName} (${extension.name})`
                    : extension.name
                "
              >
                <template #activator="{ props: titleTooltipProps }">
                  <span
                    v-bind="titleTooltipProps"
                    class="extension-title__text"
                    >{{ localizedName }}</span
                  >
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
                {{ tm('status.system') }}
              </v-chip>
              <v-tooltip
                v-if="extension?.has_update && !marketMode"
                location="top"
              >
                <template #activator="{ props: tooltipProps }">
                  <v-icon
                    v-bind="tooltipProps"
                    color="warning"
                    class="ml-2 extension-update-action"
                    icon="mdi-update"
                    size="small"
                    @click.stop="updateExtension"
                  ></v-icon>
                </template>
                <span
                  >{{ tm('card.status.hasUpdate') }}:
                  {{ extension.online_version }}</span
                >
              </v-tooltip>
            </p>

            <template v-if="!marketMode">
              <v-tooltip location="left">
                <template #activator="{ props: tooltipProps }">
                  <div class="extension-switch-wrap" @click.stop>
                    <div
                      v-bind="tooltipProps"
                      class="extension-switch-activator"
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
                  extension.activated
                    ? tm('buttons.disable')
                    : tm('buttons.enable')
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
              class="extension-update-chip"
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
              {{ tag === 'danger' ? tm('tags.danger') : tag }}
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

          <div class="extension-desc" :class="{ 'text-caption': xs }">
            {{ localizedDesc }}
          </div>
        </div>
      </div>
    </v-card-text>

    <v-card-actions class="extension-actions">
      <template v-if="!marketMode">
        <v-spacer></v-spacer>
        <v-tooltip location="top">
          <template #activator="{ props: pinTooltipProps }">
            <v-btn
              v-bind="pinTooltipProps"
              :aria-label="isPinned ? tm('buttons.unpin') : tm('buttons.pin')"
              :color="isPinned ? 'primary' : 'secondary'"
              :icon="isPinned ? 'mdi-pin' : 'mdi-pin-outline'"
              size="small"
              variant="tonal"
              class="extension-pin-btn"
              @click.stop="togglePin"
            ></v-btn>
          </template>
          <span>{{ isPinned ? tm('buttons.unpin') : tm('buttons.pin') }}</span>
        </v-tooltip>

        <v-tooltip location="top" :text="tm('buttons.viewDocs')">
          <template #activator="{ props: actionProps }">
            <v-btn
              v-bind="actionProps"
              :aria-label="tm('buttons.viewDocs')"
              icon="mdi-book-open-page-variant"
              size="small"
              variant="tonal"
              color="info"
              @click.stop="viewReadme"
            ></v-btn>
          </template>
        </v-tooltip>

        <v-tooltip location="top" :text="tm('card.actions.pluginConfig')">
          <template #activator="{ props: actionProps }">
            <v-btn
              v-bind="actionProps"
              :aria-label="tm('card.actions.pluginConfig')"
              icon="mdi-cog"
              size="small"
              variant="tonal"
              color="primary"
              @click.stop="configure"
            ></v-btn>
          </template>
        </v-tooltip>

        <v-tooltip location="top" :text="tm('card.actions.reloadPlugin')">
          <template #activator="{ props: actionProps }">
            <v-btn
              v-bind="actionProps"
              :aria-label="tm('card.actions.reloadPlugin')"
              icon="mdi-refresh"
              size="small"
              variant="tonal"
              color="primary"
              @click.stop="reloadExtension"
            ></v-btn>
          </template>
        </v-tooltip>

        <StyledMenu location="top end" offset="8">
          <template #activator="{ props: menuProps }">
            <v-btn
              v-bind="menuProps"
              :aria-label="tm('buttons.moreActions')"
              icon="mdi-dots-horizontal"
              size="small"
              variant="tonal"
              color="secondary"
              @click.stop
            ></v-btn>
          </template>

          <v-list-item
            class="styled-menu-item"
            prepend-icon="mdi-information"
            @click.stop="viewHandlers"
          >
            <v-list-item-title>{{ tm('buttons.viewInfo') }}</v-list-item-title>
          </v-list-item>

          <v-list-item
            class="styled-menu-item"
            prepend-icon="mdi-update"
            @click.stop="updateExtension"
          >
            <v-list-item-title>{{
              extension.has_update
                ? tm('card.actions.updateTo') + ' ' + extension.online_version
                : tm('card.actions.reinstall')
            }}</v-list-item-title>
          </v-list-item>

          <v-list-item
            class="styled-menu-item"
            prepend-icon="mdi-delete"
            @click.stop="uninstallExtension"
          >
            <v-list-item-title class="text-error">{{
              tm('card.actions.uninstallPlugin')
            }}</v-list-item-title>
          </v-list-item>
        </StyledMenu>
      </template>
      <template v-else>
        <v-btn color="primary" size="small" @click.stop="viewReadme">
          {{ tm('buttons.viewDocs') }}
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
  padding: 12px 16px 8px;
  width: 100%;
}

.extension-card {
  cursor: pointer;
  position: relative;
  color: rgb(var(--v-theme-on-surface));
  background: rgb(var(--v-theme-extension-surface));
}

.extension-card--market {
  background: rgb(var(--v-theme-surface-variant));
}

.extension-image-container {
  display: flex;
  align-items: flex-start;
  flex-shrink: 0;
}

.extension-logo {
  width: 64px;
  height: 64px;
  border-radius: 8px;
  object-fit: cover;
}

.extension-content-row {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.extension-meta-group {
  flex: 1;
  min-width: 0;
}

.extension-chip-group {
  gap: 4px;
}

.extension-desc {
  margin-top: 4px;
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 14px;
  line-height: 20px;
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
  color: rgb(var(--v-theme-on-surface));
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
}

.extension-title--compact {
  font-size: 14px;
  line-height: 20px;
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
  color: rgb(var(--v-theme-on-surface-variant));
  flex-shrink: 0;
  font-size: 0.875rem;
  font-weight: 500;
  margin-left: 8px;
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

.extension-switch-activator {
  display: inline-flex;
  align-items: center;
}

.extension-update-action,
.extension-update-chip {
  cursor: pointer;
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
