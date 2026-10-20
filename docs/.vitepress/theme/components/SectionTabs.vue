<script setup>
import { computed } from 'vue'
import { useData, useRoute } from 'vitepress'

const route = useRoute()
const { frontmatter } = useData()

const isEnglish = computed(() => route.path.startsWith('/en/'))

const zhTabs = [
  {
    text: '简介和部署',
    link: '/what-is-astrbot',
    matchers: ['/what-is-astrbot', '/community', '/faq', '/deploy/', '/others/', '/ospp/']
  },
  { text: '接入消息平台', link: '/platform/start', matchers: ['/platform/'] },
  { text: '接入 AI', link: '/providers/start', matchers: ['/providers/'] },
  { text: '使用', link: '/use/webui', matchers: ['/use/'] },
  { text: '开发', link: '/dev/star/plugin-new', matchers: ['/dev/'] }
]

const enTabs = [
  {
    text: 'Intro & Deploy',
    link: '/en/what-is-astrbot',
    matchers: ['/en/what-is-astrbot', '/en/community', '/en/faq', '/en/deploy/', '/en/others/', '/en/ospp/']
  },
  { text: 'Messaging Platforms', link: '/en/platform/start', matchers: ['/en/platform/'] },
  { text: 'AI Integration', link: '/en/providers/start', matchers: ['/en/providers/'] },
  { text: 'Usage', link: '/en/use/webui', matchers: ['/en/use/'] },
  { text: 'Development', link: '/en/dev/star/plugin-new', matchers: ['/en/dev/'] }
]

const tabs = computed(() => (isEnglish.value ? enTabs : zhTabs))

const isHome = computed(() => route.path === '/' || route.path === '/en/')

const shouldShow = computed(() => frontmatter.value.layout !== false && frontmatter.value.layout !== 'home' && !isHome.value)

function isActive(tab) {
  return tab.matchers.some(prefix => route.path.startsWith(prefix))
}
</script>

<template>
  <template v-if="shouldShow">
    <div class="VPSectionTabsPlaceholder" aria-hidden="true" />
    <div class="VPSectionTabs">
      <div class="container">
        <a
          v-for="tab in tabs"
          :key="tab.link"
          class="tab"
          :class="{ active: isActive(tab) }"
          :href="tab.link"
        >
          {{ tab.text }}
        </a>
      </div>
    </div>
  </template>
</template>

<style scoped>
.VPSectionTabs {
  display: none;
}

.VPSectionTabsPlaceholder {
  display: none;
}

@media (min-width: 1280px) {
  .VPSectionTabsPlaceholder {
    display: block;
    height: var(--vp-section-tabs-height, 44px);
  }

  .VPSectionTabs {
    display: block;
    position: fixed;
    left: 0;
    right: 0;
    top: calc(var(--vp-layout-top-height, 0px) + var(--vp-nav-height));
    z-index: 26;
    border-bottom: 1px solid var(--vp-c-gutter);
    background-color: var(--vp-nav-bg-color);
  }

  .container {
    margin: 0 auto;
    max-width: var(--vp-layout-max-width);
    display: flex;
    align-items: flex-end;
    gap: 10px;
    box-sizing: border-box;
    height: var(--vp-section-tabs-height, 44px);
    padding: 0 32px 8px;
  }

  .tab {
    border-radius: 999px;
    padding: 6px 12px;
    font-size: 13px;
    line-height: 20px;
    color: var(--vp-c-text-2);
    white-space: nowrap;
    transition: color 0.2s ease, background-color 0.2s ease;
  }

  .tab:hover {
    color: var(--vp-c-text-1);
    background-color: var(--vp-c-default-soft);
  }

  .tab.active {
    color: var(--vp-c-brand-1);
    background-color: var(--vp-c-brand-soft);
  }
}
</style>
