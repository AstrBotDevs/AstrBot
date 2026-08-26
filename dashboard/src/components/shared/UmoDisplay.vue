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
      </div>

      <div v-if="showMeta && hasReadableName" class="umo-display__meta">
        <span class="umo-display__umo" :title="umo">{{ umo }}</span>
      </div>
    </div>

    <v-chip
      v-if="showPlatform && resolvedPlatform"
      size="x-small"
      :color="platformColor"
      class="umo-display__platform"
    >
      {{ resolvedPlatform }}
    </v-chip>

    <div v-if="editable || showInfo" class="umo-display__actions">
      <v-btn
        v-if="editable"
        icon
        size="x-small"
        variant="text"
        class="umo-display__edit"
        @click.stop="$emit('edit')"
      >
        <v-icon size="small" color="on-surface-variant"
          >mdi-pencil-outline</v-icon
        >
        <v-tooltip v-if="editTooltip" activator="parent" location="top">
          {{ editTooltip }}
        </v-tooltip>
      </v-btn>
      <v-tooltip v-if="showInfo" location="top">
        <template #activator="{ props: activatorProps }">
          <v-icon
            v-bind="activatorProps"
            size="small"
            class="umo-display__info"
          >
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

<script setup lang="ts">
import { computed } from 'vue';
import { getPlatformColor } from '@/utils/platformUtils';

const props = withDefaults(
  defineProps<{
    umo: string;
    platform?: string;
    messageType?: string;
    sessionId?: string;
    autoName?: string;
    userAlias?: string;
    customName?: string;
    compact?: boolean;
    showPlatform?: boolean;
    showInfo?: boolean;
    showMeta?: boolean;
    showRawTitle?: boolean;
    editable?: boolean;
    editTooltip?: string;
  }>(),
  {
    platform: '',
    messageType: '',
    sessionId: '',
    autoName: '',
    userAlias: '',
    customName: '',
    compact: false,
    showPlatform: true,
    showInfo: true,
    showMeta: true,
    showRawTitle: true,
    editable: false,
    editTooltip: '',
  },
);

defineEmits<{
  edit: [];
}>();

const umoParts = computed(() => props.umo.split(':'));
const resolvedPlatform = computed(
  () => props.platform || umoParts.value[0] || '',
);
const aliasName = computed(() => props.userAlias || props.customName || '');
const hasReadableName = computed(() =>
  Boolean(aliasName.value || props.autoName),
);
const displayName = computed(() => {
  if (aliasName.value && props.autoName && aliasName.value !== props.autoName) {
    return `${aliasName.value}（${props.autoName}）`;
  }
  return aliasName.value || props.autoName || props.umo;
});
const displayNameTitle = computed(() =>
  hasReadableName.value
    ? `${displayName.value} / UMO: ${props.umo}`
    : props.umo,
);
const platformColor = computed(() => getPlatformColor(resolvedPlatform.value));
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
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 6px;
}

.umo-display__platform {
  flex: 0 0 auto;
  max-width: 96px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.umo-display__name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
  font-size: 14px;
  line-height: 1.3;
}

.umo-display__name--umo {
  color: rgba(var(--v-theme-on-surface), 0.78);
  font-family: var(--astrbot-font-mono);
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
  min-width: 0;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 12px;
  line-height: 1.25;
}

.umo-display__umo {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--astrbot-font-mono);
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
