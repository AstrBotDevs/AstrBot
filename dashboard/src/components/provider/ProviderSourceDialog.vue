<template>
  <v-dialog
    v-model="open"
    max-width="820"
    scrollable
    :aria-label="tm('providerSources.selector.title')"
    @after-leave="search = ''"
  >
    <template #activator="{ props: activatorProps }">
      <v-btn
        v-bind="activatorProps"
        :disabled="sourceTypes.length === 0"
        prepend-icon="mdi-plus"
        color="primary"
        variant="text"
        size="small"
        rounded="xl"
      >
        {{ tm('providerSources.add') }}
      </v-btn>
    </template>

    <v-card class="source-dialog" elevation="0">
      <v-card-title class="text-h3 pa-4 pb-0 pl-6 source-dialog__header">
        <span>{{ tm('providerSources.selector.title') }}</span>
        <div class="source-dialog__search">
          <v-text-field
            v-model="search"
            :placeholder="tm('providerSources.selector.search')"
            :aria-label="tm('providerSources.selector.search')"
            prepend-inner-icon="mdi-magnify"
            variant="plain"
            density="compact"
            hide-details
            clearable
          >
            <template #clear="{ props: clearProps }">
              <v-btn
                v-bind="clearProps"
                icon="mdi-close"
                size="x-small"
                variant="text"
                :aria-label="tm('providerSources.selector.clearSearch')"
              />
            </template>
          </v-text-field>
        </div>
        <v-btn
          icon="mdi-close"
          variant="text"
          size="small"
          class="source-dialog__close"
          :aria-label="tm('dialogs.settings.close')"
          @click="open = false"
        />
      </v-card-title>

      <v-card-text class="source-dialog__body">
        <section
          v-for="group in groups"
          :key="group.id"
          class="source-group"
          :class="`source-group--${group.id}`"
          :aria-label="tm(`providerSources.selector.${group.id}`)"
        >
          <div class="source-group__heading">
            <div class="source-group__label">
              <h3>{{ tm(`providerSources.selector.${group.id}`) }}</h3>
              <v-tooltip
                v-if="group.id === 'sponsors'"
                location="top"
                max-width="320"
                content-class="sponsor-info-tooltip"
              >
                <template #activator="{ props: tooltipProps }">
                  <v-btn
                    v-bind="tooltipProps"
                    icon="mdi-help-circle-outline"
                    variant="text"
                    size="22"
                    class="source-group__help"
                    :aria-label="tm('providerSources.selector.sponsorInfoTitle')"
                  />
                </template>
                <div class="sponsor-tooltip">
                  <div class="sponsor-tooltip__title">
                    <Heart :size="16" class="sponsor-tooltip__heart" aria-hidden="true" />
                    {{ tm('providerSources.selector.sponsorInfoTitle') }}
                  </div>
                  <div>{{ tm('providerSources.selector.sponsorInfoBody') }}</div>
                </div>
              </v-tooltip>
            </div>
            <span class="source-group__count">{{ group.items.length }}</span>
          </div>
          <div class="source-grid">
            <div
              v-for="source in group.items"
              :key="source.value"
              class="source-card"
              :class="`source-card--${group.id}`"
            >
              <button
                type="button"
                class="source-card__select"
                :aria-label="source.label"
                @click="selectSource(source.value)"
              />
              <span class="source-card__icon">
                <v-img
                  v-if="source.icon"
                  :src="source.icon"
                  :class="{ 'provider-icon--monochrome': source.isMonochrome }"
                  width="24"
                  height="24"
                  alt=""
                />
                <span v-else class="source-card__initial" aria-hidden="true">{{ source.label.charAt(0) }}</span>
              </span>
              <span class="source-card__copy">
                <a
                  v-if="source.isSponsor && source.website_url"
                  class="source-card__name source-card__link"
                  :href="source.website_url"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {{ source.label }}
                </a>
                <span v-else class="source-card__name">{{ source.label }}</span>
                <span v-if="source.subtitle" class="source-card__subtitle">{{ source.subtitle }}</span>
              </span>
            </div>
          </div>
        </section>
        <div v-if="groups.length === 0" class="source-dialog__empty" role="status">
          {{ tm('providerSources.selector.noResults') }}
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Heart } from '@lucide/vue'
import { loadSponsorCatalog } from '@/utils/sponsorCatalog'

const props = defineProps({
  sourceTypes: { type: Array, default: () => [] },
  tm: { type: Function, required: true }
})
const emit = defineEmits(['select'])
const open = ref(false)
const search = ref('')

watch(open, value => {
  if (value) void loadSponsorCatalog()
})

const groups = computed(() => {
  const sponsorKeys = ['MiraRouter', 'SSYCloud(胜算云)']
  const preferredKeys = [
    'OpenAI Compatible', 'OpenAI Responses', 'Google Gemini', 'Anthropic',
    'DeepSeek', 'DeepSeek Responses', 'Moonshot', 'Kimi Coding Plan',
    'MiniMax', 'MiniMax Token Plan', 'Zhipu', 'Xiaomi', 'Xiaomi Token Plan',
    'xAI', 'LongCat'
  ]
  const labels = {
    'Google Gemini': 'Gemini Compatible',
    Anthropic: 'Anthropic Compatible',
    Moonshot: 'Kimi',
    'SSYCloud(胜算云)': props.tm('providerSources.selector.ssycloud'),
    Gemini_OpenAI_API: 'Gemini OpenAI API'
  }
  const domains = {
    MiraRouter: 'mirarouter.com',
    'SSYCloud(胜算云)': 'shengsuanyun.com'
  }
  const sponsors = [
    ...props.sourceTypes.filter(source => source.isSponsor && !sponsorKeys.includes(source.value)),
    ...sponsorKeys.map(key => props.sourceTypes.find(source => source.value === key)).filter(Boolean)
  ]
  const providers = props.sourceTypes.filter(source => !sponsors.includes(source))
  const query = (search.value || '').trim().toLowerCase()
  const sources = [
    ...sponsors,
    ...preferredKeys.map(key => providers.find(source => source.value === key)).filter(Boolean),
    ...providers.filter(source => !preferredKeys.includes(source.value))
  ].map(source => ({
    ...source,
    label: labels[source.value] || source.label,
    subtitle: source.subtitle ?? domains[source.value] ?? '',
    isSponsor: source.isSponsor || sponsorKeys.includes(source.value)
  })).filter(source => `${source.value} ${source.label} ${source.subtitle}`.toLowerCase().includes(query))

  return [
    { id: 'sponsors', items: sources.filter(source => source.isSponsor) },
    { id: 'providers', items: sources.filter(source => !source.isSponsor) }
  ].filter(group => group.items.length > 0)
})

function selectSource(value) {
  open.value = false
  emit('select', value)
}
</script>

<style scoped>
.source-dialog {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 24px !important;
  background: rgb(var(--v-theme-surface));
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.source-dialog__header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(200px, 300px) auto;
  margin-bottom: 24px;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  white-space: normal;
  flex-shrink: 0;
  font-family: inherit !important;
  font-weight: 600;
}

.source-dialog__search {
  min-width: 0;
  padding: 0 12px;
  font-weight: 400;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 12px;
  background: rgba(var(--v-theme-on-surface), 0.025);
}

.source-dialog__search:focus-within {
  border-color: rgba(var(--v-theme-primary), 0.75);
}

.source-dialog__search :deep(.v-field) {
  padding-top: 0;
}

.source-dialog__search :deep(.v-field__input) {
  min-height: 36px;
  padding-top: 6px;
  padding-bottom: 6px;
  font-size: 14px;
}

.source-dialog__search :deep(.v-field__prepend-inner),
.source-dialog__search :deep(.v-field__append-inner),
.source-dialog__search :deep(.v-field__clearable) {
  padding-top: 0;
  align-items: center;
}

.source-dialog__body {
  min-height: 0;
  height: 560px;
  padding: 0 24px 24px !important;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
}

.source-group {
  min-width: 0;
}

.source-group + .source-group {
  margin-top: 24px;
}

.source-group__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 0 4px 14px;
}

.source-group__heading h3 {
  font-size: 13px;
  font-weight: 600;
  line-height: 20px;
}

.source-group__label {
  display: flex;
  align-items: center;
  gap: 5px;
}

.source-group__help {
  color: rgba(var(--v-theme-on-surface), 0.5);
}

.source-group__help :deep(.v-icon) {
  font-size: 16px;
}

:global(.v-tooltip > .v-overlay__content.sponsor-info-tooltip) {
  padding: 14px 16px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.16);
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.18);
}

.sponsor-tooltip {
  font-size: 13px;
  line-height: 1.7;
}

.sponsor-tooltip__title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  font-weight: 600;
}

.sponsor-tooltip__heart {
  flex-shrink: 0;
}

.source-group__count {
  color: rgba(var(--v-theme-on-surface), 0.42);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.source-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-content: start;
  gap: 6px 10px;
}

.source-group--sponsors .source-grid {
  grid-template-columns: minmax(0, 1fr);
  gap: 10px;
}

.source-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: flex-start;
  min-width: 0;
  height: auto !important;
  min-height: 48px;
  padding: 12px !important;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.07);
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  font: inherit;
  text-align: left;
  text-transform: none;
  letter-spacing: normal;
  box-shadow: none;
  transition: background-color 120ms ease, border-color 120ms ease;
}

.source-card:hover {
  background: rgba(var(--v-theme-on-surface), 0.045);
  border-color: rgba(var(--v-theme-on-surface), 0.2);
}

.source-card__select {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border-radius: inherit;
  cursor: pointer;
}

.source-card__select:focus-visible,
.source-card__link:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 3px;
}

.source-card__icon,
.source-card__copy {
  pointer-events: none;
}

.source-card__link {
  position: relative;
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  pointer-events: auto;
  color: inherit;
  text-decoration: none;
  border-radius: 3px;
}

.source-card__link:hover {
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
  text-underline-offset: 3px;
}

.source-card__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 24px;
  width: 24px;
  height: 24px;
}

.source-card__initial {
  font-size: 22px;
  font-weight: 650;
  line-height: 1;
}

.source-card__copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 5px;
}

.source-card__name {
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
  overflow-wrap: anywhere;
}

.source-card__subtitle {
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 11px;
  line-height: 16px;
  overflow-wrap: anywhere;
}

.source-card--sponsors {
  min-height: 62px;
  border-color: rgba(var(--v-theme-on-surface), 0.09);
  border-radius: 14px;
}

.source-card--sponsors .source-card__name {
  font-weight: 600;
}

.source-dialog__empty {
  display: grid;
  place-items: center;
  padding: 40px 24px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-size: 14px;
}

@media (max-width: 700px) {
  .source-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .source-dialog__header {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 12px;
  }

  .source-dialog__close {
    grid-column: 2;
    grid-row: 1;
  }

  .source-dialog__search {
    grid-column: 1 / -1;
    grid-row: 2;
  }
}

@media (max-width: 480px) {
  .source-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .source-dialog__body {
    padding: 0 16px 20px !important;
  }

}
</style>
