<script setup lang="ts">
import { ref, computed } from 'vue';
import { getPlatformDisplayName, getPlatformIcon } from '@/utils/platformUtils';
import { useModuleI18n } from '@/i18n/composables';

const props = defineProps({
  platforms: {
    type: Array,
    default: () => [],
  },
  size: {
    type: String,
    default: 'small',
  },
});

const { tm } = useModuleI18n('features/extension');

const showMenu = ref(false);

const platformDetails = computed(() => {
  if (!Array.isArray(props.platforms)) return [];
  return props.platforms
    .filter((item) => typeof item === 'string')
    .map((platformId) => ({
      name: getPlatformDisplayName(platformId),
      icon: getPlatformIcon(platformId),
    }));
});
</script>

<template>
  <div class="d-inline-block">
    <v-menu
      v-model="showMenu"
      location="top"
      :close-on-content-click="false"
      transition="scale-transition"
      open-on-hover
      elevation="4"
    >
      <template #activator="{ props: menuProps }">
        <v-chip
          v-if="platformDetails.length"
          v-bind="menuProps"
          color="info"
          variant="outlined"
          label
          :size="size"
          class="plugin-platform-chip"
        >
          <div class="plugin-platform-chip__content d-flex align-center">
            <!-- 显示图标，最多 5 个 -->
            <div
              v-if="platformDetails.some((p) => p.icon)"
              class="d-flex align-center mr-1"
            >
              <v-avatar
                v-for="(platform, index) in platformDetails.slice(0, 5)"
                :key="index"
                :size="size === 'x-small' ? 12 : 14"
                class="platform-mini-icon"
                :style="{
                  marginLeft: index > 0 ? '-4px' : '0',
                  zIndex: 10 - index,
                }"
              >
                <v-img v-if="platform.icon" :src="platform.icon"></v-img>
                <v-icon
                  v-else
                  icon="mdi-circle-small"
                  :size="size === 'x-small' ? 8 : 10"
                ></v-icon>
              </v-avatar>
            </div>

            <span class="text-caption font-weight-bold">
              {{
                tm('card.status.supportPlatformsCount', {
                  count: platformDetails.length,
                })
              }}
            </span>

            <v-icon
              :icon="showMenu ? 'mdi-chevron-up' : 'mdi-chevron-down'"
              :size="size === 'x-small' ? 14 : 16"
              class="ml-n1"
            ></v-icon>
          </div>
        </v-chip>
      </template>
      <v-list density="compact" border class="plugin-platform-menu pa-1">
        <v-list-item
          v-for="platform in platformDetails"
          :key="platform.name"
          min-height="24"
          class="px-2"
        >
          <template #prepend>
            <v-avatar v-if="platform.icon" size="14" class="mr-2">
              <v-img :src="platform.icon"></v-img>
            </v-avatar>
            <v-icon v-else icon="mdi-apps" size="12" class="mr-2"></v-icon>
          </template>
          <v-list-item-title class="plugin-platform-menu__title">
            {{ platform.name }}
          </v-list-item-title>
        </v-list-item>
      </v-list>
    </v-menu>
  </div>
</template>

<style scoped>
.plugin-platform-chip {
  padding-left: var(--astrbot-space-2);
  padding-right: var(--astrbot-space-1);
  cursor: pointer;
}

.plugin-platform-chip__content {
  gap: 2px;
}

.platform-mini-icon {
  border: 1px solid rgba(var(--v-theme-info), 0.3);
  background: rgba(var(--v-theme-surface));
}

.plugin-platform-chip:hover {
  background: rgb(var(--v-theme-surface-variant));
}

.plugin-platform-menu {
  border-radius: 8px;
}

.plugin-platform-menu__title {
  font-size: 12px;
  font-weight: 600;
}
</style>
