<template>
    <v-chip v-if="domain" class="ref-chip" size="x-small" variant="flat"
        :style="{ backgroundColor: isDark ? '#303030' : '#f4f4f4', color: isDark ? '#999' : '#666' }" :href="url"
        target="_blank" clickable>
        <v-icon start size="x-small" color>mdi-link-variant</v-icon>
        <span>{{ domain }}</span>

    </v-chip>
    <span v-else class="ref-fallback" :style="{ color: isDark ? '#999' : '#666' }">{{ 'site' }}</span>
</template>

<script setup>
import { computed, inject } from 'vue'

const props = defineProps({
    node: {
        type: Object,
        required: true
    }
})

console.log('RefNode node:', props.node);

// 从父组件注入的暗黑模式状态和搜索结果
const isDark = inject('isDark', false)
const webSearchResults = inject('webSearchResults', () => ({}))

// 从 node.content 中提取 ref index (格式: uuid.idx)
const refIndex = computed(() => props.node?.content?.trim() || '')

// 根据 refIndex 查找对应的 URL
const resultData = computed(() => {
    if (!refIndex.value) return null
    const results = typeof webSearchResults === 'function' ? webSearchResults() : webSearchResults
    return results?.[refIndex.value] || null
})

const url = computed(() => resultData.value?.url || '')

const domain = computed(() => {
    if (!url.value) return ''
    try {
        const urlObj = new URL(url.value)
        return urlObj.hostname.replace(/^www\./, '')
    } catch (e) {
        return ''
    }
})
</script>

<style scoped>
.ref-chip {
    margin: 0 2px;
    cursor: pointer;
    text-decoration: none;
    transition: opacity;
    margin-left: 4px;
}

.ref-chip:hover {
    opacity: 0.8;
}

.ref-fallback {
    font-size: 0.9em;
}
</style>
