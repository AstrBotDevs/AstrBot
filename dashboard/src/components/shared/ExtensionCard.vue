<script setup lang="ts">
import { ref, computed, inject } from 'vue';
import { useCustomizerStore } from "@/stores/customizer";
import { useModuleI18n } from '@/i18n/composables';

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
  'configure',
  'update',
  'reload',
  'install',
  'uninstall',
  'toggle-activation',
  'view-handlers',
  'view-readme'
]);

const reveal = ref(false);

// 国际化
const { tm } = useModuleI18n('features/extension');

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

const $confirm = inject("$confirm");

const installExtension = async () => {
  emit('install', props.extension);
};

const uninstallExtension = async () => {
  if (typeof $confirm !== "function") {
    console.error(tm("card.errors.confirmNotRegistered"));
    return;
  }

  const confirmed = await $confirm({
    title: tm("dialogs.uninstall.title"),
    message: tm("dialogs.uninstall.message"),
  });

  if (confirmed) {
    emit("uninstall", props.extension);
  }
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
</script>

<template>
  <v-card class="mx-auto d-flex flex-column" elevation="2" :style="{
    position: 'relative',
    backgroundColor: useCustomizerStore().uiTheme === 'PurpleTheme' ? marketMode ? '#f8f0dd' : '#ffffff' : '#282833',
    color: useCustomizerStore().uiTheme === 'PurpleTheme' ? '#000000dd' : '#ffffff'
  }">
    <v-card-text style="padding: 16px; padding-bottom: 0px; display: flex; gap: 16px; width: 100%;">

      <div v-if="extension?.icon">
        <v-avatar size="65">
          <v-img :src="extension.icon" :alt="extension.name" cover></v-img>
        </v-avatar>
      </div>

      <div style="width: 100%;">
        <!-- Top-right three-dot menu -->
        <div style="position: absolute; right: 8px; top: 8px; z-index: 5;">
          <v-menu offset-y>
            <template v-slot:activator="{ props: menuProps }">
              <v-btn icon variant="text" aria-label="more" v-if="extension?.repo" :href="extension?.repo"
                target="_blank">
                <v-icon icon="mdi-github"></v-icon>
              </v-btn>
              <v-btn v-bind="menuProps" icon variant="text" aria-label="more">
                <v-icon icon="mdi-dots-vertical"></v-icon>
              </v-btn>
            </template>

            <v-list>
              <v-list-item @click="viewReadme">
                <v-list-item-title>📄 {{ tm('buttons.viewDocs') }}</v-list-item-title>
              </v-list-item>

              <v-list-item v-if="marketMode && !extension?.installed" @click="installExtension">
                <v-list-item-title>
                  {{ tm('buttons.install') }}</v-list-item-title>
              </v-list-item>

              <v-list-item v-if="marketMode && extension?.installed">
                <v-list-item-title class="text--disabled">{{ tm('status.installed') }}</v-list-item-title>
              </v-list-item>

              <!-- Divider between market actions and plugin actions -->
              <v-divider v-if="!marketMode" />

              <template v-if="!marketMode">
                <v-list-item @click="configure">
                  <v-list-item-title>
                    {{ tm('card.actions.pluginConfig') }}</v-list-item-title>
                </v-list-item>

                <v-list-item @click="uninstallExtension">
                  <v-list-item-title class="text-error">{{ tm('card.actions.uninstallPlugin') }}</v-list-item-title>
                </v-list-item>

                <v-list-item @click="reloadExtension">
                  <v-list-item-title>{{ tm('card.actions.reloadPlugin') }}</v-list-item-title>
                </v-list-item>

                <v-list-item @click="toggleActivation">
                  <v-list-item-title>
                    {{ extension.activated ? tm('buttons.disable') : tm('buttons.enable') }}{{
                      tm('card.actions.togglePlugin') }}
                  </v-list-item-title>
                </v-list-item>

                <v-list-item @click="viewHandlers">
                  <v-list-item-title>{{ tm('card.actions.viewHandlers') }} ({{ extension.handlers.length
                  }})</v-list-item-title>
                </v-list-item>

                <v-list-item @click="updateExtension" :disabled="!extension?.has_update">
                  <v-list-item-title>
                    {{ tm('card.actions.updateTo') }} {{ extension.online_version || extension.version }}
                  </v-list-item-title>
                </v-list-item>
              </template>
            </v-list>
          </v-menu>
        </div>

        <div style="width: 100%; margin-bottom: 24px;">
          <!-- 最多一行 -->
          <div class="text-caption"
            style="color: gray; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-right: 84px;">
            {{ extension.author }} / {{ extension.name }}
          </div>
          <p class="text-h3 font-weight-black" :class="{ 'text-h4': $vuetify.display.xs }">
            {{ extension.name }}
            <v-tooltip location="top" v-if="extension?.has_update && !marketMode">
              <template v-slot:activator="{ props: tooltipProps }">
                <v-icon v-bind="tooltipProps" color="warning" class="ml-2" icon="mdi-update" size="small"></v-icon>
              </template>
              <span>{{ tm("card.status.hasUpdate") }}: {{ extension.online_version }}</span>
            </v-tooltip>
            <v-tooltip location="top" v-if="!extension.activated && !marketMode">
              <template v-slot:activator="{ props: tooltipProps }">
                <v-icon v-bind="tooltipProps" color="error" class="ml-2" icon="mdi-cancel" size="small"></v-icon>
              </template>
              <span>{{ tm("card.status.disabled") }}</span>
            </v-tooltip>
          </p>

          <div class="mt-1 d-flex flex-wrap">
            <v-chip color="primary" label size="small">
              <v-icon icon="mdi-source-branch" start></v-icon>
              {{ extension.version }}
            </v-chip>
            <v-chip v-if="extension?.has_update" color="warning" label size="small" class="ml-2">
              <v-icon icon="mdi-arrow-up-bold" start></v-icon>
              {{ extension.online_version }}
            </v-chip>
            <v-chip color="primary" label size="small" class="ml-2" v-if="extension.handlers?.length">
              <v-icon icon="mdi-cogs" start></v-icon>
              {{ extension.handlers?.length }}{{ tm("card.status.handlersCount") }}
            </v-chip>
            <v-chip v-for="tag in extension.tags" :key="tag" :color="tag === 'danger' ? 'error' : 'primary'" label
              size="small" class="ml-2">
              {{ tag === 'danger' ? tm('tags.danger') : tag }}
            </v-chip>
          </div>

          <div class="mt-2" :class="{ 'text-caption': $vuetify.display.xs }" style="overflow-y: auto; height: 60px;">
            {{ extension.desc }}
          </div>
        </div>
      </div>

    </v-card-text>
  </v-card>

</template>

<style scoped>
.extension-image-container {
  display: flex;
  align-items: center;
  margin-left: 12px;
}

@media (max-width: 600px) {
  .extension-image-container {
    margin-left: 8px;
  }
}
</style>
