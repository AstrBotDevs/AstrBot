<script setup lang="ts">
import { ref, computed, inject } from 'vue';
import {useCustomizerStore} from "@/stores/customizer";
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
  <v-card class="mx-auto d-flex flex-column" :elevation="highlight ? 0 : 1"
    :style="{ height: $vuetify.display.xs ? '250px' : '220px',
     backgroundColor: useCustomizerStore().uiTheme==='PurpleTheme' ? marketMode ? '#f8f0dd' : '#ffffff' : '#282833',
     color: useCustomizerStore().uiTheme==='PurpleTheme' ? '#000000dd' : '#ffffff'}">
    <v-card-text style="padding: 16px; padding-bottom: 0px; display: flex; justify-content: space-between;">

      <div class="flex-grow-1">
        <div>{{ extension.author }} /</div>

        <p class="text-h4 font-weight-black" :class="{ 'text-h4': $vuetify.display.xs }">
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
          <v-chip v-if="extension?.has_update " color="warning" label size="small" class="ml-2">
            <v-icon icon="mdi-arrow-up-bold" start></v-icon>
            {{ extension.online_version }}
          </v-chip>
          <v-chip color="primary" label size="small" class="ml-2" v-if="extension.handlers?.length">
            <v-icon icon="mdi-cogs" start></v-icon>
            {{ extension.handlers?.length }}{{ tm("card.status.handlersCount") }}
          </v-chip>
        </div>

        <div class="mt-2" :class="{ 'text-caption': $vuetify.display.xs }" style="max-height: 65px; overflow-y: auto;">
          {{ extension.desc }}
        </div>
      </div>

      <div class="extension-image-container" v-if="extension.logo">
        <img :src="extension.logo" :style="{
          height: $vuetify.display.xs ? '75px' : '100px',
          width: $vuetify.display.xs ? '75px' : '100px',
          borderRadius: '8px',
          objectFit: 'cover',
          objectPosition: 'center'
        }" :alt="tm('card.alt.logo')" />
      </div>
    </v-card-text>

    <v-card-actions style="margin-left: 0px; gap: 2px;">
      <v-btn color="teal-accent-4" :text="tm('buttons.viewDocs')" variant="text" @click="viewReadme"></v-btn>
      <v-btn v-if="!marketMode" color="teal-accent-4" :text="tm('buttons.actions')" variant="text" @click="reveal = true"></v-btn>
      <v-btn v-if="marketMode && !extension?.installed" color="teal-accent-4" :text="tm('buttons.install')" variant="text"
        @click="emit('install', extension)"></v-btn>
      <v-btn v-if="marketMode && extension?.installed" color="teal-accent-4" :text="tm('status.installed')" variant="text" disabled></v-btn>
    </v-card-actions>

    <v-expand-transition v-if="!marketMode">
      <v-card v-if="reveal" class="position-absolute w-100" height="100%"
        style="bottom: 0; display: flex; flex-direction: column;">
        <v-card-text style="overflow-y: auto;">
          <div class="d-flex align-center mb-4">
            <img v-if="extension.logo" :src="extension.logo"
              style="height: 50px; width: 50px; border-radius: 8px; margin-right: 16px;" :alt="tm('card.alt.extensionIcon')" />
            <h3>{{ extension.name }}</h3>
          </div>

          <div class="mt-4" :style="{
            justifyContent: 'center',
            display: 'flex',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '8px',
            flexDirection: $vuetify.display.xs ? 'column' : 'row'
          }">
            <v-btn prepend-icon="mdi-cog" color="primary" variant="tonal" @click="configure"
              :block="$vuetify.display.xs">
              {{ tm("card.actions.pluginConfig") }}
            </v-btn>

            <v-btn prepend-icon="mdi-delete" color="error" variant="tonal" @click="uninstallExtension"
              :block="$vuetify.display.xs">
              {{ tm("card.actions.uninstallPlugin") }}
            </v-btn>

            <v-btn prepend-icon="mdi-reload" color="primary" variant="tonal" @click="reloadExtension"
              :block="$vuetify.display.xs">
              {{ tm("card.actions.reloadPlugin") }}
            </v-btn>

            <v-btn :prepend-icon="extension.activated ? 'mdi-cancel' : 'mdi-check-circle'"
              :color="extension.activated ? 'error' : 'success'" variant="tonal" @click="toggleActivation"
              :block="$vuetify.display.xs">
              {{ extension.activated ? tm('buttons.disable') : tm('buttons.enable') }}{{ tm("card.actions.togglePlugin") }}
            </v-btn>

            <v-btn prepend-icon="mdi-cogs" color="info" variant="tonal" @click="viewHandlers"
              :block="$vuetify.display.xs">
              {{ tm("card.actions.viewHandlers") }} ({{ extension.handlers.length }})
            </v-btn>

            <v-btn prepend-icon="mdi-update" color="primary" variant="tonal" :disabled="!extension?.has_update "
              @click="updateExtension" :block="$vuetify.display.xs">
              {{ tm("card.actions.updateTo") }} {{ extension.online_version || extension.version }}
            </v-btn>
          </div>
        </v-card-text>

        <v-card-actions class="pt-0 d-flex justify-center">
          <v-btn color="teal-accent-4" :text="tm('buttons.back')" variant="text" @click="reveal = false"></v-btn>
        </v-card-actions>
      </v-card>
    </v-expand-transition>
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
