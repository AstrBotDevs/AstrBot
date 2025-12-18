<template>
    <v-dialog v-model="isOpen" persistent max-width="700" scrollable>
        <v-card>
            <v-card-title class="d-flex align-center">
                <v-icon class="mr-2">mdi-backup-restore</v-icon>
                {{ t('features.settings.backup.dialog.title') }}
            </v-card-title>

            <v-card-text class="pa-6">
                <!-- 选项卡 -->
                <v-tabs v-model="activeTab" color="primary" class="mb-4">
                    <v-tab value="export">
                        <v-icon class="mr-2">mdi-export</v-icon>
                        {{ t('features.settings.backup.tabs.export') }}
                    </v-tab>
                    <v-tab value="import">
                        <v-icon class="mr-2">mdi-import</v-icon>
                        {{ t('features.settings.backup.tabs.import') }}
                    </v-tab>
                    <v-tab value="list">
                        <v-icon class="mr-2">mdi-format-list-bulleted</v-icon>
                        {{ t('features.settings.backup.tabs.list') }}
                    </v-tab>
                </v-tabs>

                <v-window v-model="activeTab">
                    <!-- 导出标签页 -->
                    <v-window-item value="export">
                        <div v-if="exportStatus === 'idle'" class="text-center py-8">
                            <v-icon size="64" color="primary" class="mb-4">mdi-cloud-upload</v-icon>
                            <h3 class="mb-4">{{ t('features.settings.backup.export.title') }}</h3>
                            <p class="mb-4 text-grey">{{ t('features.settings.backup.export.description') }}</p>
                            <v-alert type="info" variant="tonal" class="mb-4 text-left">
                                <template v-slot:prepend>
                                    <v-icon>mdi-information</v-icon>
                                </template>
                                {{ t('features.settings.backup.export.includes') }}
                            </v-alert>
                            <v-btn color="primary" size="large" @click="startExport" :loading="exportStatus === 'processing'">
                                <v-icon class="mr-2">mdi-export</v-icon>
                                {{ t('features.settings.backup.export.button') }}
                            </v-btn>
                        </div>

                        <div v-else-if="exportStatus === 'processing'" class="text-center py-8">
                            <v-progress-circular indeterminate color="primary" size="64" class="mb-4"></v-progress-circular>
                            <h3 class="mb-4">{{ t('features.settings.backup.export.processing') }}</h3>
                            <p class="text-grey">{{ exportProgress.message || t('features.settings.backup.export.wait') }}</p>
                            <v-progress-linear :model-value="exportProgress.current" :max="exportProgress.total" class="mt-4" color="primary"></v-progress-linear>
                        </div>

                        <div v-else-if="exportStatus === 'completed'" class="text-center py-8">
                            <v-icon size="64" color="success" class="mb-4">mdi-check-circle</v-icon>
                            <h3 class="mb-4">{{ t('features.settings.backup.export.completed') }}</h3>
                            <p class="mb-4">{{ exportResult?.filename }}</p>
                            <v-btn color="primary" @click="downloadBackup(exportResult?.filename)" class="mr-2">
                                <v-icon class="mr-2">mdi-download</v-icon>
                                {{ t('features.settings.backup.export.download') }}
                            </v-btn>
                            <v-btn color="grey" variant="text" @click="resetExport">
                                {{ t('features.settings.backup.export.another') }}
                            </v-btn>
                        </div>

                        <div v-else-if="exportStatus === 'failed'" class="text-center py-8">
                            <v-icon size="64" color="error" class="mb-4">mdi-alert-circle</v-icon>
                            <h3 class="mb-4">{{ t('features.settings.backup.export.failed') }}</h3>
                            <v-alert type="error" variant="tonal" class="mb-4">
                                {{ exportError }}
                            </v-alert>
                            <v-btn color="primary" @click="resetExport">
                                {{ t('features.settings.backup.export.retry') }}
                            </v-btn>
                        </div>
                    </v-window-item>

                    <!-- 导入标签页 -->
                    <v-window-item value="import">
                        <div v-if="importStatus === 'idle'" class="py-4">
                            <v-alert type="warning" variant="tonal" class="mb-4">
                                <template v-slot:prepend>
                                    <v-icon>mdi-alert</v-icon>
                                </template>
                                {{ t('features.settings.backup.import.warning') }}
                            </v-alert>

                            <v-file-input
                                v-model="importFile"
                                :label="t('features.settings.backup.import.selectFile')"
                                accept=".zip"
                                prepend-icon="mdi-file-upload"
                                show-size
                                class="mb-4"
                            ></v-file-input>

                            <div class="d-flex justify-center">
                                <v-btn 
                                    color="primary" 
                                    size="large" 
                                    @click="startImport" 
                                    :disabled="!importFile"
                                    :loading="importStatus === 'processing'"
                                >
                                    <v-icon class="mr-2">mdi-import</v-icon>
                                    {{ t('features.settings.backup.import.button') }}
                                </v-btn>
                            </div>
                        </div>

                        <div v-else-if="importStatus === 'processing'" class="text-center py-8">
                            <v-progress-circular indeterminate color="primary" size="64" class="mb-4"></v-progress-circular>
                            <h3 class="mb-4">{{ t('features.settings.backup.import.processing') }}</h3>
                            <p class="text-grey">{{ importProgress.message || t('features.settings.backup.import.wait') }}</p>
                            <v-progress-linear :model-value="importProgress.current" :max="importProgress.total" class="mt-4" color="primary"></v-progress-linear>
                        </div>

                        <div v-else-if="importStatus === 'completed'" class="text-center py-8">
                            <v-icon size="64" color="success" class="mb-4">mdi-check-circle</v-icon>
                            <h3 class="mb-4">{{ t('features.settings.backup.import.completed') }}</h3>
                            <v-alert type="info" variant="tonal" class="mb-4">
                                {{ t('features.settings.backup.import.restartRequired') }}
                            </v-alert>
                            <v-btn color="primary" @click="restartAstrBot" class="mr-2">
                                <v-icon class="mr-2">mdi-restart</v-icon>
                                {{ t('features.settings.backup.import.restartNow') }}
                            </v-btn>
                            <v-btn color="grey" variant="text" @click="resetImport">
                                {{ t('core.common.close') }}
                            </v-btn>
                        </div>

                        <div v-else-if="importStatus === 'failed'" class="text-center py-8">
                            <v-icon size="64" color="error" class="mb-4">mdi-alert-circle</v-icon>
                            <h3 class="mb-4">{{ t('features.settings.backup.import.failed') }}</h3>
                            <v-alert type="error" variant="tonal" class="mb-4">
                                {{ importError }}
                            </v-alert>
                            <v-btn color="primary" @click="resetImport">
                                {{ t('features.settings.backup.import.retry') }}
                            </v-btn>
                        </div>
                    </v-window-item>

                    <!-- 备份列表标签页 -->
                    <v-window-item value="list">
                        <div v-if="loadingList" class="text-center py-8">
                            <v-progress-circular indeterminate color="primary"></v-progress-circular>
                        </div>

                        <div v-else-if="backupList.length === 0" class="text-center py-8">
                            <v-icon size="64" color="grey" class="mb-4">mdi-folder-open-outline</v-icon>
                            <p class="text-grey">{{ t('features.settings.backup.list.empty') }}</p>
                        </div>

                        <v-list v-else lines="two">
                            <v-list-item
                                v-for="backup in backupList"
                                :key="backup.filename"
                            >
                                <template v-slot:prepend>
                                    <v-icon color="primary">mdi-zip-box</v-icon>
                                </template>

                                <v-list-item-title>{{ backup.filename }}</v-list-item-title>
                                <v-list-item-subtitle>
                                    {{ formatFileSize(backup.size) }} · {{ formatDate(backup.created_at) }}
                                </v-list-item-subtitle>

                                <template v-slot:append>
                                    <v-btn icon="mdi-download" variant="text" size="small" @click="downloadBackup(backup.filename)"></v-btn>
                                    <v-btn icon="mdi-delete" variant="text" size="small" color="error" @click="deleteBackup(backup.filename)"></v-btn>
                                </template>
                            </v-list-item>
                        </v-list>

                        <div class="d-flex justify-center mt-4">
                            <v-btn color="primary" variant="text" @click="loadBackupList">
                                <v-icon class="mr-2">mdi-refresh</v-icon>
                                {{ t('features.settings.backup.list.refresh') }}
                            </v-btn>
                        </div>
                    </v-window-item>
                </v-window>
            </v-card-text>

            <v-card-actions class="px-6 py-4">
                <v-spacer></v-spacer>
                <v-btn color="grey" variant="text" @click="handleClose" :disabled="isProcessing">
                    {{ t('core.common.close') }}
                </v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>

    <WaitingForRestart ref="wfr"></WaitingForRestart>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import axios from 'axios'
import { useI18n } from '@/i18n/composables'
import WaitingForRestart from './WaitingForRestart.vue'

const { t } = useI18n()

const isOpen = ref(false)
const activeTab = ref('export')
const wfr = ref(null)

// 导出状态
const exportStatus = ref('idle') // idle, processing, completed, failed
const exportTaskId = ref(null)
const exportProgress = ref({ current: 0, total: 100, message: '' })
const exportResult = ref(null)
const exportError = ref('')

// 导入状态
const importStatus = ref('idle') // idle, processing, completed, failed
const importFile = ref(null)
const importTaskId = ref(null)
const importProgress = ref({ current: 0, total: 100, message: '' })
const importError = ref('')

// 备份列表
const loadingList = ref(false)
const backupList = ref([])

// 计算属性
const isProcessing = computed(() => {
    return exportStatus.value === 'processing' || importStatus.value === 'processing'
})

// 监听对话框打开
watch(isOpen, (newVal) => {
    if (newVal) {
        loadBackupList()
    } else {
        resetAll()
    }
})

// 监听标签页切换
watch(activeTab, (newVal) => {
    if (newVal === 'list') {
        loadBackupList()
    }
})

// 加载备份列表
const loadBackupList = async () => {
    loadingList.value = true
    try {
        const response = await axios.get('/api/backup/list')
        if (response.data.status === 'ok') {
            backupList.value = response.data.data.items || []
        }
    } catch (error) {
        console.error('Failed to load backup list:', error)
    } finally {
        loadingList.value = false
    }
}

// 开始导出
const startExport = async () => {
    exportStatus.value = 'processing'
    exportProgress.value = { current: 0, total: 100, message: '' }

    try {
        const response = await axios.post('/api/backup/export')
        if (response.data.status === 'ok') {
            exportTaskId.value = response.data.data.task_id
            pollExportProgress()
        } else {
            throw new Error(response.data.message)
        }
    } catch (error) {
        exportStatus.value = 'failed'
        exportError.value = error.message || 'Export failed'
    }
}

// 轮询导出进度
const pollExportProgress = async () => {
    if (!exportTaskId.value) return

    try {
        const response = await axios.get('/api/backup/progress', {
            params: { task_id: exportTaskId.value }
        })

        if (response.data.status === 'ok') {
            const data = response.data.data
            
            if (data.status === 'processing' && data.progress) {
                exportProgress.value = {
                    current: data.progress.current || 0,
                    total: data.progress.total || 100,
                    message: data.progress.message || ''
                }
                setTimeout(pollExportProgress, 1000)
            } else if (data.status === 'completed') {
                exportStatus.value = 'completed'
                exportResult.value = data.result
                loadBackupList()
            } else if (data.status === 'failed') {
                exportStatus.value = 'failed'
                exportError.value = data.error || 'Export failed'
            } else {
                setTimeout(pollExportProgress, 1000)
            }
        }
    } catch (error) {
        exportStatus.value = 'failed'
        exportError.value = error.message || 'Failed to get export progress'
    }
}

// 重置导出状态
const resetExport = () => {
    exportStatus.value = 'idle'
    exportTaskId.value = null
    exportProgress.value = { current: 0, total: 100, message: '' }
    exportResult.value = null
    exportError.value = ''
}

// 开始导入
const startImport = async () => {
    if (!importFile.value) return

    importStatus.value = 'processing'
    importProgress.value = { current: 0, total: 100, message: '' }

    try {
        const formData = new FormData()
        formData.append('file', importFile.value)

        const response = await axios.post('/api/backup/import', formData, {
            headers: { 'Content-Type': 'multipart/form-data' }
        })

        if (response.data.status === 'ok') {
            importTaskId.value = response.data.data.task_id
            pollImportProgress()
        } else {
            throw new Error(response.data.message)
        }
    } catch (error) {
        importStatus.value = 'failed'
        importError.value = error.message || 'Import failed'
    }
}

// 轮询导入进度
const pollImportProgress = async () => {
    if (!importTaskId.value) return

    try {
        const response = await axios.get('/api/backup/progress', {
            params: { task_id: importTaskId.value }
        })

        if (response.data.status === 'ok') {
            const data = response.data.data
            
            if (data.status === 'processing' && data.progress) {
                importProgress.value = {
                    current: data.progress.current || 0,
                    total: data.progress.total || 100,
                    message: data.progress.message || ''
                }
                setTimeout(pollImportProgress, 1000)
            } else if (data.status === 'completed') {
                importStatus.value = 'completed'
            } else if (data.status === 'failed') {
                importStatus.value = 'failed'
                importError.value = data.error || 'Import failed'
            } else {
                setTimeout(pollImportProgress, 1000)
            }
        }
    } catch (error) {
        importStatus.value = 'failed'
        importError.value = error.message || 'Failed to get import progress'
    }
}

// 重置导入状态
const resetImport = () => {
    importStatus.value = 'idle'
    importFile.value = null
    importTaskId.value = null
    importProgress.value = { current: 0, total: 100, message: '' }
    importError.value = ''
}

// 下载备份
const downloadBackup = async (filename) => {
    try {
        const response = await axios.get('/api/backup/download', {
            params: { filename },
            responseType: 'blob'
        })
        
        // 创建 Blob URL 并触发下载
        const blob = new Blob([response.data], { type: 'application/zip' })
        const url = window.URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = filename
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        window.URL.revokeObjectURL(url)
    } catch (error) {
        console.error('Download failed:', error)
        alert(t('features.settings.backup.export.failed') + ': ' + (error.message || 'Unknown error'))
    }
}

// 删除备份
const deleteBackup = async (filename) => {
    if (!confirm(t('features.settings.backup.list.confirmDelete'))) return

    try {
        const response = await axios.post('/api/backup/delete', { filename })
        if (response.data.status === 'ok') {
            loadBackupList()
        } else {
            alert(response.data.message || 'Delete failed')
        }
    } catch (error) {
        alert(error.message || 'Delete failed')
    }
}

// 格式化文件大小
const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// 格式化日期
const formatDate = (timestamp) => {
    return new Date(timestamp * 1000).toLocaleString()
}

// 重启 AstrBot
const restartAstrBot = () => {
    axios.post('/api/stat/restart-core').then(() => {
        if (wfr.value) {
            wfr.value.check()
        }
    })
}

// 重置所有状态
const resetAll = () => {
    resetExport()
    resetImport()
    activeTab.value = 'export'
}

// 关闭对话框
const handleClose = () => {
    if (isProcessing.value) return
    isOpen.value = false
}

// 打开对话框
const open = () => {
    isOpen.value = true
}

defineExpose({ open })
</script>

<style scoped>
.v-list-item {
    border-bottom: 1px solid rgba(0, 0, 0, 0.08);
}

.v-list-item:last-child {
    border-bottom: none;
}
</style>