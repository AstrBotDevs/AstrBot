<script setup>
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import PluginPlatformChip from "@/components/shared/PluginPlatformChip.vue";
import { usePluginI18n } from "@/utils/pluginI18n";

const { tm } = useModuleI18n("features/extension");
const { pluginShortDesc } = usePluginI18n();

const props = defineProps({
  plugin: {
    type: Object,
    required: true,
  },
  defaultPluginIcon: {
    type: String,
    required: true,
  },
  showPluginFullName: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["install", "open"]);

const normalizePlatformList = (platforms) => {
  if (!Array.isArray(platforms)) return [];
  return platforms.filter((item) => typeof item === "string");
};

const platformDisplayList = computed(() =>
  normalizePlatformList(props.plugin?.support_platforms),
);

const cardDescription = computed(() =>
  pluginShortDesc(props.plugin, props.plugin?.short_desc || props.plugin?.desc || ""),
);

const handleInstall = (plugin) => {
  emit("install", plugin);
};

const handleOpen = () => {
  emit("open", props.plugin);
};

</script>

<template>
  <v-card
    class="rounded-lg d-flex flex-column plugin-card"
    variant="outlined"
    elevation="0"
    :ripple="false"
    @click="handleOpen"
  >

    <v-card-text
      class="plugin-card-content"
    >
      <div class="plugin-cover">
        <img
          :src="plugin?.logo || defaultPluginIcon"
          :alt="plugin.name"
          class="plugin-cover__image"
        />
      </div>

      <div class="plugin-info">
        <div class="d-flex align-center plugin-title-row">
          <div class="font-weight-bold plugin-title">
            {{
              plugin.display_name?.length
                ? plugin.display_name
                : showPluginFullName
                ? plugin.name
                : plugin.trimmedName
            }}
          </div>
          <v-chip
            v-if="plugin?.pinned"
            color="warning"
            size="x-small"
            label
            class="market-recommended-chip"
          >
            {{ tm("market.recommended") }}
          </v-chip>
          <v-chip
            v-if="plugin?.astrbot_compatible === false"
            color="error"
            size="x-small"
            label
            class="market-incompatible-chip"
          >
            {{ tm("status.incompatible") }}
          </v-chip>
        </div>

        <div class="d-flex align-center plugin-meta">
          <v-icon
            icon="mdi-account"
            size="x-small"
            style="color: rgba(var(--v-theme-on-surface), 0.5)"
          ></v-icon>
          <a
            v-if="plugin?.social_link"
            :href="plugin.social_link"
            target="_blank"
            @click.stop
            class="text-subtitle-2 font-weight-medium"
            style="
              text-decoration: none;
              color: rgb(var(--v-theme-primary));
              white-space: nowrap;
              overflow: hidden;
              text-overflow: ellipsis;
            "
          >
            {{ plugin.author }}
          </a>
          <span
            v-else
            class="text-subtitle-2 font-weight-medium"
            style="
              color: rgb(var(--v-theme-primary));
              white-space: nowrap;
              overflow: hidden;
              text-overflow: ellipsis;
            "
          >
            {{ plugin.author }}
          </span>
          <div
            v-if="plugin.stars !== undefined"
            class="d-flex align-center text-subtitle-2 ml-2"
            style="color: rgba(var(--v-theme-on-surface), 0.7)"
          >
            <v-icon
              icon="mdi-star"
              size="x-small"
              style="margin-right: 2px"
            ></v-icon>
            <span>{{ plugin.stars }}</span>
          </div>
        </div>

        <div class="text-caption plugin-description">
          {{ cardDescription }}
        </div>

        <div class="plugin-stats"></div>
      </div>
    </v-card-text>

    <v-card-actions
      style="gap: 6px; padding: 8px 12px; padding-top: 0"
      @click.stop
    >
      <div
        v-if="platformDisplayList.length"
        class="plugin-badges"
      >
        <PluginPlatformChip
          :platforms="plugin.support_platforms"
          size="x-small"
          :chip-style="{ height: '20px' }"
        />
      </div>
      <v-spacer></v-spacer>
      <v-btn
        v-if="plugin?.repo"
        color="secondary"
        size="small"
        variant="tonal"
        class="market-action-btn"
        :href="plugin.repo"
        target="_blank"
        style="height: 32px"
      >
        <v-icon icon="mdi-github" start size="small"></v-icon>
        {{ tm("buttons.viewRepo") }}
      </v-btn>
      <v-btn
        v-if="!plugin?.installed"
        color="primary"
        size="small"
        @click="handleInstall(plugin)"
        variant="flat"
        class="market-action-btn"
        style="height: 32px"
      >
        {{ tm("buttons.install") }}
      </v-btn>
      <v-btn
        v-else
        color="success"
        size="small"
        variant="flat"
        disabled
        class="market-action-btn"
        style="height: 32px"
      >
        ✓ {{ tm("status.installed") }}
      </v-btn>
    </v-card-actions>
  </v-card>
</template>

<style scoped>
.plugin-card {
  background: rgb(var(--v-theme-surface));
  cursor: pointer;
  transition: background-color 0.16s ease;
}

.plugin-card:hover,
.plugin-card:focus-within {
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.plugin-card :deep(.v-card__overlay),
.plugin-card :deep(.v-ripple__container) {
  display: none;
}

.plugin-card-content {
  padding: 12px;
  padding-bottom: 8px;
  display: flex;
  flex-direction: row;
  gap: 12px;
  width: 100%;
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

.plugin-cover {
  flex-shrink: 0;
  width: 76px;
  height: 76px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: transparent;
}

.plugin-cover__image {
  width: 76px;
  height: 76px;
  border-radius: 8px;
  object-fit: cover;
}

.plugin-info {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.plugin-title-row {
  margin-bottom: 4px;
  gap: 8px;
}

.market-recommended-chip {
  flex-shrink: 0;
  font-weight: bold;
  height: 20px;
}

.market-incompatible-chip {
  flex-shrink: 0;
  font-weight: 700;
  height: 20px;
}

.plugin-title {
  line-height: 1.3;
  font-size: 1rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.plugin-meta {
  gap: 4px;
  margin-bottom: 6px;
  flex-wrap: nowrap;
}

.plugin-description {
  color: rgba(var(--v-theme-on-surface), 0.6);
  line-height: 1.3;
  margin-bottom: 6px;
  flex: 1;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  min-height: calc(1.3em * 2);
  max-height: calc(1.3em * 2);
}

.plugin-badges {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
  margin-bottom: 4px;
}

.plugin-stats {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: auto;
}

.plugin-description::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.plugin-description::-webkit-scrollbar-track {
  background: transparent;
}

.plugin-description::-webkit-scrollbar-thumb {
  background-color: rgba(var(--v-theme-primary-rgb), 0.4);
  border-radius: 4px;
  border: 2px solid transparent;
  background-clip: content-box;
}

.plugin-description::-webkit-scrollbar-thumb:hover {
  background-color: rgba(var(--v-theme-primary-rgb), 0.6);
}

.market-action-btn {
  font-size: 0.9rem;
  font-weight: 600;
}
</style>
