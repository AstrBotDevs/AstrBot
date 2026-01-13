<template>
    <v-dialog v-model="isOpen" persistent max-width="800" max-height="80vh" scrollable>
        <v-card>
            <v-card-title class="d-flex align-center">
                <v-icon class="mr-2" color="primary">mdi-file-document-outline</v-icon>
                {{ t('features.eula.dialog.title') }}
            </v-card-title>

            <v-card-text class="pa-0">
                <div v-if="loading" class="text-center py-8">
                    <v-progress-circular indeterminate color="primary" class="mb-4"></v-progress-circular>
                    <p>{{ t('features.eula.dialog.loading') }}</p>
                </div>

                <div v-else-if="error" class="text-center py-4 px-6">
                    <v-alert type="error" variant="tonal" class="mb-4">
                        <template v-slot:prepend>
                            <v-icon>mdi-alert</v-icon>
                        </template>
                        {{ error }}
                    </v-alert>
                    <v-btn color="primary" @click="loadEulaContent">
                        {{ t('features.eula.dialog.retry') }}
                    </v-btn>
                </div>

                <div v-else class="eula-content-container">
                    <!-- EULA 内容区域 -->
                    <div class="eula-content pa-6" v-html="renderedContent"></div>
                </div>
            </v-card-text>

            <v-divider></v-divider>

            <v-card-actions class="px-6 py-4">
                <v-checkbox
                    v-model="accepted"
                    :label="t('features.eula.dialog.acceptLabel')"
                    color="primary"
                    hide-details
                    density="compact"
                ></v-checkbox>
                <v-spacer></v-spacer>
                <v-btn
                    color="primary"
                    variant="elevated"
                    @click="handleAccept"
                    :disabled="!accepted"
                    :loading="submitting"
                >
                    {{ t('features.eula.dialog.confirm') }}
                </v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import axios from 'axios'
import MarkdownIt from 'markdown-it'
import { useI18n } from '@/i18n/composables'

const { t } = useI18n()

// 创建 MarkdownIt 实例
const md = new MarkdownIt({
    html: true,
    linkify: true,
    typographer: true,
    breaks: false,
})

const isOpen = ref(false)
const loading = ref(false)
const error = ref('')
const submitting = ref(false)
const eulaContent = ref('')
const accepted = ref(false)

let resolvePromise = null

// 渲染 Markdown 内容
const renderedContent = computed(() => {
    if (!eulaContent.value) return ''
    try {
        return md.render(eulaContent.value)
    } catch (e) {
        console.error('Failed to render markdown:', e)
        return eulaContent.value
    }
})

// 监听对话框打开
watch(isOpen, (newVal) => {
    if (newVal) {
        loadEulaContent()
        accepted.value = false
    } else {
        eulaContent.value = ''
        error.value = ''
    }
})

// 加载 EULA 内容
const loadEulaContent = async () => {
    loading.value = true
    error.value = ''

    try {
        const response = await axios.get('/api/eula/content')
        if (response.data.status === 'ok') {
            eulaContent.value = response.data.data.content || ''
        } else {
            error.value = response.data.message || t('features.eula.dialog.loadError')
        }
    } catch (err) {
        console.error('Failed to load EULA content:', err)
        error.value = t('features.eula.dialog.loadError')
    } finally {
        loading.value = false
    }
}

// 确认签署
const handleAccept = async () => {
    if (!accepted.value) return

    submitting.value = true

    try {
        const response = await axios.post('/api/eula/accept')
        if (response.data.status === 'ok') {
            isOpen.value = false
            if (resolvePromise) {
                resolvePromise({ success: true })
            }
        } else {
            error.value = response.data.message || t('features.eula.dialog.acceptError')
        }
    } catch (err) {
        console.error('Failed to accept EULA:', err)
        error.value = t('features.eula.dialog.acceptError')
    } finally {
        submitting.value = false
    }
}

// 检查 EULA 状态并打开对话框（如果需要）
const checkAndOpen = async () => {
    try {
        const response = await axios.get('/api/eula/status')
        if (response.data.status === 'ok') {
            if (!response.data.data.accepted) {
                // 未签署，打开对话框
                isOpen.value = true
                return new Promise((resolve) => {
                    resolvePromise = resolve
                })
            }
            // 已签署
            return { success: true, alreadyAccepted: true }
        }
    } catch (err) {
        console.error('Failed to check EULA status:', err)
    }
    return { success: false }
}

// 直接打开对话框
const open = () => {
    isOpen.value = true
    return new Promise((resolve) => {
        resolvePromise = resolve
    })
}

defineExpose({ checkAndOpen, open })
</script>

<style scoped>
.eula-content-container {
    max-height: 60vh;
    overflow-y: auto;
}

.eula-content {
    line-height: 1.8;
}

.eula-content :deep(h1) {
    font-size: 1.5rem;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.eula-content :deep(h2) {
    font-size: 1.25rem;
    margin-top: 1.5rem;
    margin-bottom: 0.75rem;
}

.eula-content :deep(h3) {
    font-size: 1.1rem;
    margin-top: 1rem;
    margin-bottom: 0.5rem;
}

.eula-content :deep(p) {
    margin-bottom: 0.75rem;
}

.eula-content :deep(ul),
.eula-content :deep(ol) {
    margin-bottom: 0.75rem;
    padding-left: 1.5rem;
}

.eula-content :deep(li) {
    margin-bottom: 0.25rem;
}

.eula-content :deep(blockquote) {
    border-left: 4px solid rgb(var(--v-theme-primary));
    padding-left: 1rem;
    margin: 1rem 0;
    font-style: italic;
    opacity: 0.9;
}

.eula-content :deep(hr) {
    margin: 2rem 0;
    border: none;
    border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.eula-content :deep(code) {
    background-color: rgba(var(--v-theme-surface-variant), 0.5);
    padding: 0.2rem 0.4rem;
    border-radius: 4px;
    font-size: 0.9em;
}

.eula-content :deep(strong) {
    font-weight: 600;
}
</style>
