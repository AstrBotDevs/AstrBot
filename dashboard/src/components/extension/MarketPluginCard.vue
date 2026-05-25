<script setup>
import { ref, computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import PluginPlatformChip from "@/components/shared/PluginPlatformChip.vue";

const { tm } = useModuleI18n("features/extension");

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

const emit = defineEmits(["install"]);

const normalizePlatformList = (platforms) => {
  if (!Array.isArray(platforms)) return [];
  return platforms.filter((item) => typeof item === "string");
};

const platformDisplayList = computed(() =>
  normalizePlatformList(props.plugin?.support_platforms),
);

const handleInstall = (plugin) => {
  emit("install", plugin);
};

</script>

<template>
  <v-card
    class="rounded-lg d-flex flex-column plugin-card"
    elevation="0"
    style="height: 13rem; position: relative"
  >
    <v-chip
      v-if="plugin?.pinned"
      color="warning"
      size="x-small"
      label
      style="
        position: absolute;
        right: 8px;
        top: 8px;
        z-index: 10;
        height: 20px;
        font-weight: bold;
      "
    >
      {{ tm("market.recommended") }}
    </v-chip>

    <v-card-text
      style="
        padding: 12px;
        padding-bottom: 8px;
        display: flex;
        gap: 12px;
        width: 100%;
        flex: 1;
        overflow: hidden;
      "
    >
      <div style="flex-shrink: 0">
        <img
          :src="plugin?.logo || defaultPluginIcon"
          :alt="plugin.name"
          style="
            height: 75px;
            width: 75px;
            border-radius: 8px;
            object-fit: cover;
          "
        />
      </div>

      <div
        style="
          flex: 1;
          overflow: hidden;
          display: flex;
          flex-direction: column;
        "
      >
        <div
          class="font-weight-bold"
          style="
            margin-bottom: 4px;
            line-height: 1.3;
            font-size: 1.2rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          "
        >
          <span style="overflow: hidden; text-overflow: ellipsis">
            {{
              plugin.display_name?.length
                ? plugin.display_name
                : showPluginFullName
                ? plugin.name
                : plugin.trimmedName
            }}
          </span>
        </div>

        <div class="d-flex align-center" style="gap: 4px; margin-bottom: 6px">
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
            class="d-flex align-center text-subtitle-2 ml-2"
            style="color: rgba(var(--v-theme-on-surface), 0.7)"
          >
            <v-icon
              icon="mdi-source-branch"
              size="x-small"
              style="margin-right: 2px"
            ></v-icon>
            <span>{{ plugin.version }}</span>
          </div>
        </div>

        <div class="text-caption plugin-description">
          {{ plugin.desc }}
        </div>

        <div
          v-if="plugin.astrbot_version || platformDisplayList.length"
          class="d-flex align-center flex-wrap"
          style="gap: 4px; margin-top: 4px; margin-bottom: 4px"
        >
          <v-chip
            v-if="plugin.astrbot_version"
            size="x-small"
            color="secondary"
            variant="outlined"
            style="height: 20px"
          >
            AstrBot: {{ plugin.astrbot_version }}
          </v-chip>
          <PluginPlatformChip
            :platforms="plugin.support_platforms"
            size="x-small"
            :chip-style="{ height: '20px' }"
          />
        </div>

        <div class="d-flex align-center" style="gap: 8px; margin-top: auto">
          <div
            v-if="plugin.stars !== undefined"
            class="d-flex align-center text-subtitle-2"
            style="color: rgba(var(--v-theme-on-surface), 0.7)"
          >
            <v-icon
              icon="mdi-star"
              size="x-small"
              style="margin-right: 2px"
            ></v-icon>
            <span>{{ plugin.stars }}</span>
          </div>
          <div
            v-if="plugin.updated_at"
            class="d-flex align-center text-subtitle-2"
            style="color: rgba(var(--v-theme-on-surface), 0.7)"
          >
            <v-icon
              icon="mdi-clock-outline"
              size="x-small"
              style="margin-right: 2px"
            ></v-icon>
            <span>{{ new Date(plugin.updated_at).toLocaleString() }}</span>
          </div>
        </div>
      </div>
    </v-card-text>

    <v-card-actions
      style="gap: 6px; padding: 8px 12px; padding-top: 0"
      @click.stop
    >
      <v-chip
        v-for="tag in plugin.tags?.slice(0, 2)"
        :key="tag"
        :color="tag === 'danger' ? 'error' : 'primary'"
        label
        size="x-small"
        style="height: 20px"
      >
        {{ tag === "danger" ? tm("tags.danger") : tag }}
      </v-chip>
      <v-menu v-if="plugin.tags && plugin.tags.length > 2" open-on-hover offset-y>
        <template v-slot:activator="{ props: menuProps }">
          <v-chip
            v-bind="menuProps"
            color="grey"
            label
            size="x-small"
            style="height: 20px; cursor: pointer"
          >
            +{{ plugin.tags.length - 2 }}
          </v-chip>
        </template>
        <v-list density="compact">
          <v-list-item v-for="tag in plugin.tags.slice(2)" :key="tag">
            <v-chip :color="tag === 'danger' ? 'error' : 'primary'" label size="small">
              {{ tag === "danger" ? tm("tags.danger") : tag }}
            </v-chip>
          </v-list-item>
        </v-list>
      </v-menu>
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
      <v-chip v-else color="success" size="x-small" label style="height: 20px">
        ✓ {{ tm("status.installed") }}
      </v-chip>
    </v-card-actions>
  </v-card>
</template>

<style scoped>
.plugin-description {
  color: rgba(var(--v-theme-on-surface), 0.6);
  line-height: 1.3;
  margin-bottom: 6px;
  flex: 1;
  overflow-y: hidden;
}

.plugin-card:hover .plugin-description {
  overflow-y: auto;
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
