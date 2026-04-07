<script setup>
import { computed } from "vue";
import defaultPluginIcon from "@/assets/images/plugin_icon.png";

const props = defineProps({
  plugin: {
    type: Object,
    required: true,
  },
  isPinned: {
    type: Boolean,
    default: false,
  },
  tm: {
    type: Function,
    required: true,
  },
  dragged: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits([
  "toggle-pin",
  "view-readme",
  "open-config",
  "reload",
  "update",
  "show-info",
  "uninstall",
  "dragstart",
  "dragover",
  "dragenter",
  "dragend",
  "drop",
]);

const handlePinnedImgError = (e) => {
  e.target.src = defaultPluginIcon;
};

const authorDisplay = computed(() => {
  const p = props.plugin || {};
  if (typeof p.author === "string" && p.author.trim()) return p.author;
  if (Array.isArray(p.authors) && p.authors.length) return p.authors.join(", ");
  if (typeof p.author_name === "string" && p.author_name.trim())
    return p.author_name;
  if (typeof p.owner === "string" && p.owner.trim()) return p.owner;
  if (p.author && typeof p.author === "object" && p.author.name)
    return p.author.name;
  return "";
});
</script>

<template>
  <div
    class="pinned-item pinned-card-wrapper"
    :class="{ 'is-dragging': dragged }"
    style="position: relative"
    draggable="true"
    @dragstart="$emit('dragstart')"
    @dragover.prevent="$emit('dragover', $event)"
    @dragenter.prevent="$emit('dragenter', $event)"
    @dragend="$emit('dragend', $event)"
    @drop="$emit('drop', $event)"
  >
    <v-menu offset-y>
      <template #activator="{ props: menuProps }">
        <div
          class="d-flex flex-column align-center"
          style="cursor: pointer; width: 80px"
        >
          <v-avatar
            v-bind="menuProps"
            size="72"
            class="pinned-avatar activator-avatar mb-1"
            :title="plugin.display_name || plugin.name"
          >
            <img
              :src="
                typeof plugin.logo === 'string' && plugin.logo.trim()
                  ? plugin.logo
                  : defaultPluginIcon
              "
              :alt="plugin.name"
              @error="handlePinnedImgError"
            />
          </v-avatar>
          <span
            class="text-caption text-center text-truncate"
            style="
              width: 100%;
              font-size: 0.75rem;
              opacity: 0.9;
              line-height: 1.2;
            "
          >
            {{ plugin.display_name || plugin.name }}
          </span>
        </div>
      </template>

      <v-card>
        <v-card-title
          class="d-flex"
          style="gap: 8px; padding: 12px; align-items: center"
        >
          <div
            style="display: flex; align-items: center; gap: 8px; min-width: 0"
          >
            <v-avatar
              size="40"
              class="pinned-avatar"
              style="width: 40px; height: 40px"
            >
              <img
                :src="
                  typeof plugin.logo === 'string' && plugin.logo.trim()
                    ? plugin.logo
                    : defaultPluginIcon
                "
                :alt="plugin.name"
                @error="handlePinnedImgError"
              />
            </v-avatar>
            <div style="min-width: 0; overflow: hidden">
              <div
                style="
                  font-weight: 600;
                  font-size: 0.95rem;
                  white-space: nowrap;
                  text-overflow: ellipsis;
                  overflow: hidden;
                "
              >
                {{ plugin.display_name || plugin.name }}
              </div>
              <div
                style="
                  font-size: 0.8rem;
                  color: var(--v-theme-on-surface);
                  opacity: 0.8;
                  white-space: nowrap;
                  text-overflow: ellipsis;
                  overflow: hidden;
                "
              >
                {{ authorDisplay || plugin.author || "" }}
              </div>
            </div>
          </div>
        </v-card-title>
        <v-divider></v-divider>
        <v-card-text class="d-flex" style="gap: 8px; padding: 12px">
          <v-tooltip location="top" :text="tm('buttons.viewDocs')">
            <template #activator="{ props: a }">
              <v-btn
                v-bind="a"
                icon
                size="small"
                variant="tonal"
                color="info"
                @click.stop="$emit('view-readme', plugin)"
              >
                <v-icon>mdi-book-open-page-variant</v-icon>
              </v-btn>
            </template>
          </v-tooltip>

          <v-tooltip location="top" :text="tm('card.actions.pluginConfig')">
            <template #activator="{ props: a }">
              <v-btn
                v-bind="a"
                icon
                size="small"
                variant="tonal"
                color="primary"
                @click.stop="$emit('open-config', plugin.name)"
              >
                <v-icon>mdi-cog</v-icon>
              </v-btn>
            </template>
          </v-tooltip>

          <v-tooltip location="top" :text="tm('card.actions.reloadPlugin')">
            <template #activator="{ props: a }">
              <v-btn
                v-bind="a"
                icon
                size="small"
                variant="tonal"
                color="primary"
                @click.stop="$emit('reload', plugin.name)"
              >
                <v-icon>mdi-refresh</v-icon>
              </v-btn>
            </template>
          </v-tooltip>

          <v-tooltip location="top" :text="tm('buttons.update')">
            <template #activator="{ props: a }">
              <v-btn
                v-bind="a"
                icon
                size="small"
                variant="tonal"
                color="warning"
                @click.stop="$emit('update', plugin.name)"
              >
                <v-icon>mdi-update</v-icon>
              </v-btn>
            </template>
          </v-tooltip>

          <v-tooltip location="top" :text="tm('buttons.viewInfo')">
            <template #activator="{ props: a }">
              <v-btn
                v-bind="a"
                icon
                size="small"
                variant="tonal"
                color="secondary"
                @click.stop="$emit('show-info', plugin)"
              >
                <v-icon>mdi-information</v-icon>
              </v-btn>
            </template>
          </v-tooltip>

          <v-tooltip location="top" :text="tm('buttons.uninstall')">
            <template #activator="{ props: a }">
              <v-btn
                v-bind="a"
                icon
                size="small"
                variant="tonal"
                color="error"
                @click.stop="$emit('uninstall', plugin.name)"
                v-if="!plugin.reserved"
              >
                <v-icon>mdi-delete</v-icon>
              </v-btn>
            </template>
          </v-tooltip>
        </v-card-text>
      </v-card>
    </v-menu>

    <v-btn
      icon
      size="small"
      class="pinned-pin-btn"
      :color="isPinned ? 'primary' : 'secondary'"
      @click.stop="$emit('toggle-pin', plugin)"
      :title="isPinned ? tm('buttons.unpin') : tm('buttons.pin')"
      style="
        position: absolute;
        top: 6px;
        right: 6px;
        min-width: 22px;
        width: 22px;
        height: 22px;
      "
    >
      <v-icon size="14">{{ isPinned ? "mdi-pin" : "mdi-pin-outline" }}</v-icon>
    </v-btn>
  </div>
</template>

<style scoped>
.pinned-avatar {
  display: inline-flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
  cursor: pointer;
  border-radius: 12px;
}

.pinned-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.pinned-card-wrapper {
  position: relative;
  display: inline-block;
  width: 80px;
}

.pinned-item {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition:
    transform 0.2s ease,
    opacity 0.2s ease;
}

.is-dragging {
  opacity: 0.5;
  transform: scale(0.95);
  cursor: grabbing;
}

[draggable="true"] {
  cursor: grab;
}

[draggable="true"]:active {
  cursor: grabbing;
}
</style>
