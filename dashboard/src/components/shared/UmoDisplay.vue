<template>
  <div class="umo-display" :class="{ 'umo-display--compact': compact }">
    <div class="umo-display__main">
      <div class="umo-display__line">
        <span
          class="umo-display__name"
          :class="{ 'umo-display__name--umo': !hasReadableName }"
          :title="showRawTitle ? displayNameTitle : displayName"
        >
          {{ displayName }}
        </span>
        <span
          v-if="showMeta && hasReadableName"
          class="umo-display__umo"
          :title="umo"
          >({{ umo }})</span
        >
      </div>

      <div v-if="showPlatform && resolvedPlatform" class="umo-display__meta">
        <PlatformLogo :platform-type="platformType || resolvedPlatform" />
        <span class="umo-display__platform">{{ resolvedPlatform }}</span>
        <v-chip
          v-if="
            resolvedMessageType === 'GroupMessage' ||
            resolvedMessageType === 'FriendMessage'
          "
          size="x-small"
          variant="flat"
          :color="
            resolvedMessageType === 'GroupMessage' ? '#1976D2' : '#2E7D32'
          "
        >
          {{
            t(
              resolvedMessageType === "GroupMessage"
                ? "core.common.umoSelector.group"
                : "core.common.umoSelector.private",
            )
          }}
        </v-chip>
      </div>
    </div>

    <div v-if="editable || showInfo" class="umo-display__actions">
      <v-btn
        v-if="editable"
        icon
        size="x-small"
        variant="text"
        class="umo-display__edit"
        @click.stop="$emit('edit')"
      >
        <v-icon size="small" color="grey">mdi-pencil-outline</v-icon>
        <v-tooltip v-if="editTooltip" activator="parent" location="top">
          {{ editTooltip }}
        </v-tooltip>
      </v-btn>
      <v-tooltip v-if="showInfo" location="top">
        <template v-slot:activator="{ props }">
          <v-icon v-bind="props" size="small" class="umo-display__info">
            mdi-information-outline
          </v-icon>
        </template>
        <div>
          <p>UMO: {{ umo }}</p>
        </div>
      </v-tooltip>
    </div>
  </div>
</template>

<script>
import { useI18n } from "@/i18n/composables";
import PlatformLogo from "./PlatformLogo.vue";

export default {
  name: "UmoDisplay",
  components: { PlatformLogo },
  setup() {
    const { t } = useI18n();
    return { t };
  },
  props: {
    umo: {
      type: String,
      required: true,
    },
    platform: {
      type: String,
      default: "",
    },
    platformType: {
      type: String,
      default: "",
    },
    messageType: {
      type: String,
      default: "",
    },
    sessionId: {
      type: String,
      default: "",
    },
    autoName: {
      type: String,
      default: "",
    },
    userAlias: {
      type: String,
      default: "",
    },
    customName: {
      type: String,
      default: "",
    },
    compact: {
      type: Boolean,
      default: false,
    },
    showPlatform: {
      type: Boolean,
      default: true,
    },
    showInfo: {
      type: Boolean,
      default: true,
    },
    showMeta: {
      type: Boolean,
      default: true,
    },
    showRawTitle: {
      type: Boolean,
      default: true,
    },
    editable: {
      type: Boolean,
      default: false,
    },
    editTooltip: {
      type: String,
      default: "",
    },
  },
  emits: ["edit"],
  computed: {
    umoParts() {
      return this.umo.split(":");
    },
    resolvedPlatform() {
      return this.platform || this.umoParts[0] || "";
    },
    resolvedMessageType() {
      return this.messageType || this.umoParts[1] || "";
    },
    resolvedSessionId() {
      return this.sessionId || this.umoParts.slice(2).join(":") || this.umo;
    },
    aliasName() {
      return this.userAlias || this.customName || "";
    },
    displayName() {
      if (this.aliasName && this.autoName && this.aliasName !== this.autoName) {
        return `${this.aliasName}（${this.autoName}）`;
      }
      return this.aliasName || this.autoName || this.umo;
    },
    displayNameTitle() {
      return this.hasReadableName
        ? `${this.displayName} / UMO: ${this.umo}`
        : this.umo;
    },
    hasReadableName() {
      return Boolean(this.aliasName || this.autoName);
    },
  },
};
</script>

<style scoped>
.umo-display {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  width: 100%;
}

.umo-display__main {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-width: 0;
  gap: 4px;
}

.umo-display__line {
  min-width: 0;
  overflow-wrap: anywhere;
}

.umo-display__platform {
  min-width: 0;
  overflow-wrap: anywhere;
}

.umo-display__name {
  font-weight: 500;
  font-size: 14px;
  line-height: 1.3;
}

.umo-display__name--umo {
  color: rgba(var(--v-theme-on-surface), 0.78);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas,
    "Liberation Mono", monospace;
  font-size: 12px;
}

.umo-display__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 2px;
}

.umo-display__edit,
.umo-display__info {
  flex: 0 0 auto;
}

.umo-display__meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  min-width: 0;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 12px;
  line-height: 1.25;
}

.umo-display__umo {
  margin-left: 4px;
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 12px;
}

.umo-display__meta :deep(.v-chip) {
  flex: 0 0 auto;
}

.umo-display--compact .umo-display__name {
  font-size: 13px;
}

.umo-display--compact .umo-display__name--umo,
.umo-display--compact .umo-display__meta {
  font-size: 12px;
}

.umo-display--compact .umo-display__meta {
  line-height: 1.2;
}
</style>
