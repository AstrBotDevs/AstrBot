<template>
  <div
    class="widget-card"
    :class="variant === 'welcome' ? 'widget-card--welcome' : `widget-card--${status}`"
  >
    <template v-if="variant === 'welcome'">
      <slot />
    </template>

    <Transition v-else name="widget-fold" mode="out-in">
      <div v-if="status === 'active'" key="active" class="widget-card__pane">
        <div class="widget-card__header">
          <div class="widget-card__title">
            <v-icon :icon="icon" size="18" color="primary" />
            <h2>{{ title }}</h2>
          </div>
          <span
            v-if="badgeText"
            class="widget-badge"
            :class="`widget-badge--${badgeTone}`"
            :title="badgeTone === 'ready' ? badgeText : undefined"
          >
            <span v-if="badgeTone === 'ready'" class="status-dot" aria-hidden="true" />
            <span class="widget-badge__label">{{ badgeText }}</span>
          </span>
        </div>

        <div
          class="widget-card__body"
          :class="bodyVariant !== 'default' ? `widget-card__body--${bodyVariant}` : undefined"
        >
          <slot />
        </div>

        <div
          v-if="$slots.footer"
          class="widget-card__footer"
          :class="footerLayout !== 'end' ? `widget-card__footer--${footerLayout}` : undefined"
        >
          <slot name="footer" />
        </div>
      </div>

      <div v-else key="receipt" class="widget-card__pane">
        <div class="widget-receipt">
          <div class="widget-receipt__info">
            <v-icon
              class="widget-receipt__icon"
              :icon="status === 'done' ? 'mdi-check-circle' : 'mdi-arrow-right-circle-outline'"
              size="18"
              :color="status === 'done' ? 'success' : undefined"
            />
            <span>{{ summary }}</span>
          </div>
          <v-btn
            v-if="actionLabel"
            size="small"
            variant="text"
            :disabled="actionDisabled"
            @click="emit('action')"
          >
            {{ actionLabel }}
          </v-btn>
        </div>
        <slot name="after-receipt" />
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: 'standard' | 'welcome';
    status?: 'active' | 'done' | 'skipped';
    icon?: string;
    title?: string;
    badgeText?: string;
    badgeTone?: 'active' | 'ready';
    summary?: string;
    actionLabel?: string;
    actionDisabled?: boolean;
    bodyVariant?: 'default' | 'notice' | 'trial';
    footerLayout?: 'end' | 'split' | 'platform';
  }>(),
  {
    variant: 'standard',
    status: 'active',
    icon: '',
    title: '',
    badgeText: '',
    badgeTone: 'active',
    summary: '',
    actionLabel: '',
    actionDisabled: false,
    bodyVariant: 'default',
    footerLayout: 'end',
  },
);

const emit = defineEmits<{ action: [] }>();
</script>

<style scoped>
.widget-card {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  border: 1px solid rgba(var(--v-theme-borderLight), 0.42);
  border-radius: var(--astrbot-radius-card);
  background: rgb(var(--v-theme-surface));
  overflow: hidden;
  transform-origin: center top;
  animation: widget-spring-up 380ms cubic-bezier(0.22, 1, 0.36, 1) both;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background-color 0.2s ease;
}

.widget-card__pane {
  width: 100%;
  min-width: 0;
}

.widget-card--active {
  border-color: rgba(var(--v-theme-primary), 0.18);
  box-shadow: 0 3px 16px rgba(var(--v-theme-primary), 0.035);
}

.widget-card--done,
.widget-card--skipped {
  background: rgba(var(--v-theme-on-surface), 0.025);
}

.widget-card--welcome {
  border-color: rgba(var(--v-theme-primary), 0.18);
  background: linear-gradient(
    180deg,
    rgba(var(--v-theme-primary), 0.04) 0%,
    rgb(var(--v-theme-surface)) 56%
  );
}

.widget-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 20px;
  border-bottom: 1px solid rgba(var(--v-theme-borderLight), 0.32);
}

.widget-card__title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex-shrink: 0;
}

.widget-card__title h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.4;
}

.widget-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex-shrink: 1;
  padding: 2px 10px;
  border-radius: var(--astrbot-radius-pill);
  font-size: 12px;
  font-weight: 500;
  max-width: min(240px, 58%);
  overflow: hidden;
  white-space: nowrap;
}

.widget-badge__label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.widget-badge--active {
  background: rgba(var(--v-theme-primary), 0.11);
  color: rgb(var(--v-theme-primary));
}

.widget-badge--ready {
  background: rgba(var(--v-theme-success), 0.12);
  color: rgb(var(--v-theme-on-surface));
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: rgb(var(--v-theme-success));
  flex-shrink: 0;
}

.widget-card__body {
  padding: 18px 20px;
  min-width: 0;
}

.widget-card__body :deep(.property-hint) {
  overflow-wrap: anywhere;
}

.widget-card__body :deep(.v-field) {
  border-radius: var(--astrbot-radius-control);
  background: rgba(var(--v-theme-on-surface), 0.025);
  --v-field-border-opacity: 0.2;
}

.widget-card__body--notice {
  max-height: 360px;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-block: 14px;
}

.widget-card__body--notice :deep(.markdown-body),
.widget-card :deep(.widget-card__body--reopened .markdown-body) {
  padding: 0;
}

.widget-card__body--notice :deep(.markdown-body > :first-child),
.widget-card :deep(.widget-card__body--reopened .markdown-body > :first-child) {
  margin-top: 0;
}

.widget-card__body--notice :deep(.markdown-body > :last-child),
.widget-card :deep(.widget-card__body--reopened .markdown-body > :last-child) {
  margin-bottom: 0;
}

.widget-card__body--notice :deep(.markdown-body h1),
.widget-card__body--notice :deep(.markdown-body h2),
.widget-card :deep(.widget-card__body--reopened .markdown-body h1),
.widget-card :deep(.widget-card__body--reopened .markdown-body h2) {
  font-size: 1.25rem;
  margin-top: 14px;
  margin-bottom: 10px;
  padding-bottom: 0;
  border-bottom: 0;
}

.widget-card__body--notice :deep(.markdown-body p),
.widget-card :deep(.widget-card__body--reopened .markdown-body p) {
  margin-bottom: 10px;
}

.widget-card__body--trial {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.widget-card__footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
  padding: 12px 20px 14px;
  border-top: 1px solid rgba(var(--v-theme-borderLight), 0.32);
}

.widget-card__footer--split,
.widget-card__footer--platform {
  justify-content: space-between;
}

.widget-card__footer :deep(.v-btn),
.widget-receipt :deep(.v-btn),
.widget-card--welcome :deep(.widget-welcome-actions .v-btn) {
  text-transform: none;
  letter-spacing: 0;
  border-radius: var(--astrbot-radius-pill);
}

.widget-card__footer :deep(.widget-card__actions) {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-inline-start: auto;
}

.widget-card__footer :deep(.widget-card__hint) {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.62);
}

.widget-receipt {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
}

.widget-receipt__info {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-size: 14px;
  color: rgba(var(--v-theme-on-surface), 0.82);
  overflow-wrap: anywhere;
}

.widget-receipt__icon {
  animation: check-pop 340ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

.widget-fold-leave-active {
  transition:
    opacity 180ms ease,
    transform 200ms cubic-bezier(0.4, 0, 1, 1);
  transform-origin: top center;
}

.widget-fold-leave-to {
  opacity: 0;
  transform: translateY(-8px) scaleY(0.92);
}

.widget-fold-enter-active {
  transition:
    opacity 240ms ease,
    transform 300ms cubic-bezier(0.22, 1, 0.36, 1);
  transform-origin: top center;
}

.widget-fold-enter-from {
  opacity: 0;
  transform: translateY(10px) scale(0.97);
}

@keyframes widget-spring-up {
  0% {
    opacity: 0;
    transform: translateY(20px) scale(0.98);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes check-pop {
  0% {
    opacity: 0;
    transform: scale(0.5);
  }
  70% {
    opacity: 1;
    transform: scale(1.16);
  }
  100% {
    opacity: 1;
    transform: scale(1);
  }
}

@media (prefers-reduced-motion: reduce) {
  .widget-card,
  .widget-receipt__icon {
    animation: none !important;
  }

  .widget-fold-enter-active,
  .widget-fold-leave-active {
    transition: none !important;
  }
}

@media (max-width: 760px) {
  .widget-card__header,
  .widget-card__body,
  .widget-card__footer {
    padding-inline: 14px;
  }

  .widget-card__body--notice {
    max-height: min(360px, 46dvh);
  }

  .widget-card__body--notice :deep(.markdown-body) {
    font-size: 14px;
  }

  .widget-card__body--notice :deep(.markdown-body h1),
  .widget-card__body--notice :deep(.markdown-body h2) {
    font-size: 1.125rem;
  }
}

@media (max-width: 600px) {
  .widget-card__footer--split {
    flex-direction: column-reverse;
    align-items: stretch;
    gap: 8px;
  }

  .widget-card__footer--split :deep(.widget-card__actions) {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    width: 100%;
    margin-inline-start: 0;
  }

  .widget-card__footer--platform {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }

  .widget-card__footer--platform :deep(.widget-card__actions) {
    width: 100%;
    justify-content: flex-end;
    flex-wrap: wrap;
    margin-inline-start: 0;
  }
}
</style>
