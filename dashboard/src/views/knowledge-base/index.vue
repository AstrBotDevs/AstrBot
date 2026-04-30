<template>
  <div class="kb-container">
    <div class="page-header">
      <div>
        <h1 class="kb-page-title">
          <button
            v-if="isDetailRoute"
            class="kb-page-title__parent"
            type="button"
            @click="goToList"
          >
            {{ t('list.title') }}
          </button>
          <template v-else>
            {{ t('list.title') }}
          </template>
          <template v-if="isDetailRoute">
            <v-icon icon="mdi-chevron-right" size="24" class="mx-1" />
            <span class="kb-page-title__current">{{ displayDetailTitle }}</span>
          </template>
        </h1>
        <p class="text-body-2 text-medium-emphasis">{{ t('list.subtitle') }}</p>
      </div>
      <v-btn
        icon="mdi-information-outline"
        variant="text"
        size="small"
        color="grey"
        href="https://docs.astrbot.app/use/knowledge-base.html"
        target="_blank"
      />
    </div>

    <router-view @title-change="detailTitle = $event" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useModuleI18n } from '@/i18n/composables'

const { tm: t } = useModuleI18n('features/knowledge-base/index')
const route = useRoute()
const router = useRouter()
const detailTitle = ref('')

const isDetailRoute = computed(() => route.name === 'NativeKBDetail')
const displayDetailTitle = computed(() => detailTitle.value || String(route.params.kbId || ''))

const goToList = () => {
  router.push({ name: 'NativeKBList' })
}
</script>

<style scoped>
.kb-container {
  margin: 0 auto;
  max-width: 1400px;
  padding: 24px;
  width: 100%;
  height: 100%;
  position: relative;
}

.page-header {
  align-items: flex-start;
  display: flex;
  justify-content: space-between;
  margin-bottom: 24px;
}

.kb-page-title {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  font-size: 1.5rem;
  font-weight: 700;
  gap: 2px;
  letter-spacing: 0;
  line-height: 1.2;
  margin: 0 0 4px;
  min-width: 0;
}

.kb-page-title__parent {
  background: transparent;
  border: 0;
  color: inherit;
  cursor: pointer;
  font: inherit;
  padding: 0;
}

.kb-page-title__parent:hover {
  color: rgb(var(--v-theme-primary));
}

.kb-page-title__current {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 768px) {
  .kb-container {
    padding: 16px;
  }
}
</style>
