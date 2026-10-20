<script setup lang="ts">
import { ref, computed } from "vue";
import { getPlatformDisplayName, getPlatformIcon } from "@/utils/platformUtils";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps({
  platforms: {
    type: Array,
    default: () => [],
  },
  size: {
    type: String,
    default: "small",
  },
  chipStyle: {
    type: Object,
    default: () => ({}),
  },
});

const { tm } = useModuleI18n("features/extension");

const showMenu = ref(false);

const platformDetails = computed(() => {
  if (!Array.isArray(props.platforms)) return [];
  return props.platforms
    .filter((item) => typeof item === "string")
    .map((platformId) => ({
      name: getPlatformDisplayName(platformId as string),
      icon: getPlatformIcon(platformId as string),
    }));
});
</script>

<template>
  <div class="d-inline-block">
    <v-chip
      v-if="platformDetails.length"
      color="info"
      variant="outlined"
      label
      :size="size"
      class="plugin-platform-chip"
      :style="{ cursor: 'pointer', ...chipStyle }"
      @click.stop="showMenu = !showMenu"
    >
      <div class="d-flex align-center" style="gap: 2px">
        <!-- 显示图标，最多 5 个 -->
        <div class="d-flex align-center mr-1" v-if="platformDetails.some(p => p.icon)">
          <v-avatar
            v-for="(platform, index) in platformDetails.slice(0, 5)"
            :key="index"
            :size="size === 'x-small' ? 12 : 14"
            class="platform-mini-icon"
            :style="{ marginLeft: index > 0 ? '-4px' : '0', zIndex: 10 - index }"
          >
            <v-img v-if="platform.icon" :src="platform.icon"></v-img>
            <v-icon v-else icon="mdi-circle-small" :size="size === 'x-small' ? 8 : 10"></v-icon>
          </v-avatar>
        </div>

        <span class="text-caption font-weight-bold">
          {{
            tm("card.status.supportPlatformsCount", {
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

      <v-menu
        v-model="showMenu"
        activator="parent"
        location="top"
        :close-on-content-click="false"
        transition="scale-transition"
        open-on-hover
      >
        <v-list density="compact" border elevation="12" class="rounded-lg pa-1">
          <v-list-item
            v-for="platform in platformDetails"
            :key="platform.name"
            min-height="24"
            class="px-2"
          >
            <template v-slot:prepend>
              <v-avatar size="14" class="mr-2" v-if="platform.icon">
                <v-img :src="platform.icon"></v-img>
              </v-avatar>
              <v-icon v-else icon="mdi-platform" size="12" class="mr-2"></v-icon>
            </template>
            <v-list-item-title class="text-caption font-weight-bold" style="font-size: 0.75rem !important">
              {{ platform.name }}
            </v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
    </v-chip>
  </div>
</template>

<style scoped>
.plugin-platform-chip {
  padding-left: 6px !important;
  padding-right: 4px !important;
  transition: all 0.2s ease;
}

.platform-mini-icon {
  border: 1px solid rgba(var(--v-theme-info), 0.3);
  background: rgba(var(--v-theme-surface));
}

.plugin-platform-chip:hover {
  background: rgba(var(--v-theme-info), 0.08);
}
</style>
