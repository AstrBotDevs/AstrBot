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
                        <!-- 步骤1: 选择文件 -->
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
                                    @click="uploadAndCheck"
                                    :disabled="!importFile"
                                    :loading="importStatus === 'uploading'"
                                >
                                    <v-icon class="mr-2">mdi-upload</v-icon>
                                    {{ t('features.settings.backup.import.uploadAndCheck') }}
                                </v-btn>
                            </div>
                        </div>

                        <!-- 步骤1.5: 上传中 -->
                        <div v-else-if="importStatus === 'uploading'" class="text-center py-8">
                            <v-icon size="64" color="primary" class="mb-4">mdi-cloud-upload</v-icon>
                            <h3 class="mb-4">{{ t('features.settings.backup.import.uploading') }}</h3>
                            <p class="text-grey mb-2">
                                {{ uploadProgress.message || t('features.settings.backup.import.uploadWait') }}
                            </p>
                            <p class="text-grey-darken-1 mb-4">
                                {{ formatFileSize(uploadProgress.uploaded) }} / {{ formatFileSize(uploadProgress.total) }}
                                ({{ uploadProgress.percent }}%)
                            </p>
                            <v-progress-linear
                                :model-value="uploadProgress.percent"
                                :max="100"
                                class="mt-2"
                                color="primary"
                                height="8"
                                rounded
                            ></v-progress-linear>
                        </div>

                        <!-- 步骤2: 确认导入 -->
                        <div v-else-if="importStatus === 'confirm'" class="py-4">
                            <v-alert
                                :type="versionAlertType"
                                variant="tonal"
                                class="mb-4"
                            >
                                <template v-slot:prepend>
                                    <v-icon>{{ versionAlertIcon }}</v-icon>
                                </template>
                                <div class="confirm-message">
                                    <div class="text-h6 mb-2">{{ versionAlertTitle }}</div>
                                    <div class="mb-2">
                                        <strong>{{ t('features.settings.backup.import.version.backupVersion') }}:</strong> {{ checkResult?.backup_version }}<br>
                                        <strong>{{ t('features.settings.backup.import.version.currentVersion') }}:</strong> {{ checkResult?.current_version }}
                                    </div>
                                    <div v-if="checkResult?.backup_time && checkResult?.backup_time !== '未知'" class="mb-2">
                                        <strong>{{ t('features.settings.backup.import.version.backupTime') }}:</strong> {{ formatISODate(checkResult?.backup_time) }}
                                    </div>
                                    <div class="mt-3" style="white-space: pre-line;">{{ versionAlertMessage }}</div>
                                </div>
                            </v-alert>

                            <!-- 备份摘要 -->
                            <v-card variant="outlined" class="mb-4" v-if="checkResult?.backup_summary">
                                <v-card-title class="text-subtitle-1">
                                    <v-icon class="mr-2">mdi-package-variant</v-icon>
                                    {{ t('features.settings.backup.import.backupContents') }}
                                </v-card-title>
                                <v-card-text>
                                    <div class="d-flex flex-wrap ga-2">
                                        <v-chip v-if="checkResult.backup_summary.tables?.length" size="small" color="primary" variant="tonal" :ripple="false" class="non-interactive-chip">
                                            {{ checkResult.backup_summary.tables.length }} {{ t('features.settings.backup.import.tables') }}
                                        </v-chip>
                                        <v-chip v-if="checkResult.backup_summary.has_knowledge_bases" size="small" color="success" variant="tonal" :ripple="false" class="non-interactive-chip">
                                            {{ t('features.settings.backup.import.knowledgeBases') }}
                                        </v-chip>
                                        <v-chip v-if="checkResult.backup_summary.has_config" size="small" color="info" variant="tonal" :ripple="false" class="non-interactive-chip">
                                            {{ t('features.settings.backup.import.configFiles') }}
                                        </v-chip>
                                        <v-chip v-for="dir in (checkResult.backup_summary.directories || [])" :key="dir" size="small" color="warning" variant="tonal" :ripple="false" class="non-interactive-chip">
                                            {{ dir }}
                                        </v-chip>
                                    </div>
                                </v-card-text>
                            </v-card>

                            <!-- 警告信息 -->
                            <v-alert v-if="checkResult?.warnings?.length" type="warning" variant="tonal" class="mb-4">
                                <div v-for="(warning, idx) in checkResult.warnings" :key="idx">{{ warning }}</div>
                            </v-alert>

                            <div class="d-flex justify-center align-center mt-4" style="gap: 16px;">
                                <v-btn
                                    color="grey-darken-1"
                                    variant="outlined"
                                    size="large"
                                    @click="resetImport"
                                >
                                    <v-icon class="mr-2">mdi-close</v-icon>
                                    {{ t('core.common.cancel') }}
                                </v-btn>
                                <v-btn
                                    v-if="checkResult?.can_import"
                                    color="error"
                                    size="large"
                                    variant="flat"
                                    @click="confirmImport"
                                >
                                    <v-icon class="mr-2">mdi-alert</v-icon>
                                    {{ t('features.settings.backup.import.confirmImport') }}
                                </v-btn>
                            </div>
                        </div>

                        <!-- 步骤3: 导入进行中 -->
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
                                    <v-icon :color="backup.type === 'uploaded' ? 'orange' : 'primary'">
                                        {{ backup.type === 'uploaded' ? 'mdi-upload' : 'mdi-zip-box' }}
                                    </v-icon>
                                </template>

                                <v-list-item-title>{{ backup.filename }}</v-list-item-title>
                                <v-list-item-subtitle>
                                    {{ formatFileSize(backup.size) }} · {{ formatDate(backup.created_at) }}
                                    <v-chip size="x-small" color="primary" variant="tonal" class="ml-2">
                                        v{{ backup.astrbot_version }}
                                    </v-chip>
                                    <v-chip v-if="backup.type === 'uploaded'" size="x-small" color="orange" variant="tonal" class="ml-1">
                                        {{ t('features.settings.backup.list.uploaded') }}
                                    </v-chip>
                                </v-list-item-subtitle>

                                <template v-slot:append>
                                    <v-btn
                                        icon="mdi-restore"
                                        variant="text"
                                        size="small"
                                        color="success"
                                        :title="t('features.settings.backup.list.restore')"
                                        @click="restoreFromList(backup.filename)"
                                    ></v-btn>
                                    <v-btn
                                        icon="mdi-pencil"
                                        variant="text"
                                        size="small"
                                        :title="t('features.settings.backup.list.rename')"
                                        @click="openRenameDialog(backup.filename)"
                                    ></v-btn>
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

                        <!-- 提示信息 -->
                        <p class="text-caption text-grey text-center mt-4">
                            <v-icon size="small" class="mr-1">mdi-information-outline</v-icon>
                            {{ t('features.settings.backup.list.ftpHint') }}
                        </p>
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

    <!-- 重命名对话框 -->
    <v-dialog v-model="renameDialogOpen" max-width="450" persistent>
        <v-card>
            <v-card-title>
                <v-icon class="mr-2">mdi-pencil</v-icon>
                {{ t('features.settings.backup.list.renameTitle') }}
            </v-card-title>
            <v-card-text>
                <v-text-field
                    v-model="renameNewName"
                    :label="t('features.settings.backup.list.newName')"
                    :rules="[renameValidationRule]"
                    :error-messages="renameError"
                    variant="outlined"
                    density="comfortable"
                    autofocus
                    @keyup.enter="confirmRename"
                >
                    <template v-slot:append-inner>
                        <span class="text-grey">.zip</span>
                    </template>
                </v-text-field>
                <p class="text-caption text-grey mt-1">
                    {{ t('features.settings.backup.list.renameHint') }}
                </p>
            </v-card-text>
            <v-card-actions>
                <v-spacer></v-spacer>
                <v-btn color="grey" variant="text" @click="closeRenameDialog">
                    {{ t('core.common.cancel') }}
                </v-btn>
                <v-btn
                    color="primary"
                    variant="flat"
                    @click="confirmRename"
                    :loading="renameLoading"
                    :disabled="!renameNewName || !!renameError"
                >
                    {{ t('core.common.confirm') }}
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
const importStatus = ref('idle') // idle, uploading, confirm, processing, completed, failed
const importFile = ref(null)
const importTaskId = ref(null)
const importProgress = ref({ current: 0, total: 100, message: '' })
const importError = ref('')
const uploadedFilename = ref('')  // 已上传的文件名
const checkResult = ref(null)     // 预检查结果

// 分片上传状态
const CONCURRENT_UPLOADS = 5     // 并发上传数
const uploadId = ref('')
const chunkSize = ref(0)         // 分片大小（从后端获取）
const uploadProgress = ref({
    uploaded: 0,
    total: 0,
    percent: 0,
    message: ''
})

// 备份列表
const loadingList = ref(false)
const backupList = ref([])

// 重命名对话框状态
const renameDialogOpen = ref(false)
const renameOldFilename = ref('')
const renameNewName = ref('')
const renameLoading = ref(false)
const renameError = ref('')

// 计算属性
const isProcessing = computed(() => {
    return exportStatus.value === 'processing' ||
           importStatus.value === 'processing' ||
           importStatus.value === 'uploading'
})

// 版本检查相关的计算属性
const versionAlertType = computed(() => {
    const status = checkResult.value?.version_status
    if (status === 'major_diff') return 'error'
    if (status === 'minor_diff') return 'warning'
    return 'info'
})

const versionAlertIcon = computed(() => {
    const status = checkResult.value?.version_status
    if (status === 'major_diff') return 'mdi-close-circle'
    if (status === 'minor_diff') return 'mdi-alert'
    return 'mdi-check-circle'
})

const versionAlertTitle = computed(() => {
    const status = checkResult.value?.version_status
    if (status === 'major_diff') return t('features.settings.backup.import.version.majorDiffTitle')
    if (status === 'minor_diff') return t('features.settings.backup.import.version.minorDiffTitle')
    return t('features.settings.backup.import.version.matchTitle')
})

const versionAlertMessage = computed(() => {
    const status = checkResult.value?.version_status
    if (status === 'major_diff') return t('features.settings.backup.import.version.majorDiffMessage')
    if (status === 'minor_diff') return t('features.settings.backup.import.version.minorDiffMessage')
    return t('features.settings.backup.import.version.matchMessage')
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

/**
 * 并发上传分片
 *
 * 使用并发控制同时上传多个分片，提升上传速度。
 * 后端按分片索引命名文件（如 0.part, 1.part），合并时按顺序读取，
 * 因此分片到达顺序不影响最终结果。
 */
const uploadChunksInParallel = async (file, totalChunks, currentUploadId, currentChunkSize) => {
    // 跟踪已完成的字节数（使用原子操作避免并发问题）
    let completedBytes = 0
    const chunkSizes = []
    
    // 预计算每个分片的大小（使用后端返回的 chunk_size）
    for (let i = 0; i < totalChunks; i++) {
        const start = i * currentChunkSize
        const end = Math.min(start + currentChunkSize, file.size)
        chunkSizes[i] = end - start
    }

    // 上传单个分片的函数
    const uploadSingleChunk = async (chunkIndex) => {
        const start = chunkIndex * currentChunkSize
        const end = Math.min(start + currentChunkSize, file.size)
        const chunk = file.slice(start, end)

        const formData = new FormData()
        formData.append('upload_id', currentUploadId)
        formData.append('chunk_index', chunkIndex.toString())
        formData.append('chunk', chunk)

        const response = await axios.post('/api/backup/upload/chunk', formData, {
            headers: { 'Content-Type': 'multipart/form-data' }
        })

        if (response.data.status !== 'ok') {
            throw new Error(response.data.message)
        }

        // 更新进度（累加已完成字节）
        completedBytes += chunkSizes[chunkIndex]
        uploadProgress.value.uploaded = completedBytes
        uploadProgress.value.percent = Math.round((completedBytes / file.size) * 100)

        return response
    }

    // 创建分片索引队列
    const pendingChunks = Array.from({ length: totalChunks }, (_, i) => i)
    const activePromises = []

    // 处理队列中的分片
    while (pendingChunks.length > 0 || activePromises.length > 0) {
        // 填充并发槽位
        while (pendingChunks.length > 0 && activePromises.length < CONCURRENT_UPLOADS) {
            const chunkIndex = pendingChunks.shift()
            const promise = uploadSingleChunk(chunkIndex).then(() => {
                // 完成后从活动列表移除
                const idx = activePromises.indexOf(promise)
                if (idx > -1) activePromises.splice(idx, 1)
            })
            activePromises.push(promise)
        }

        // 等待至少一个完成
        if (activePromises.length > 0) {
            await Promise.race(activePromises)
        }
    }
}

// 上传并检查
const uploadAndCheck = async () => {
    if (!importFile.value) return

    importStatus.value = 'uploading'
    const file = importFile.value

    try {
        // 初始化上传进度
        uploadProgress.value = {
            uploaded: 0,
            total: file.size,
            percent: 0,
            message: t('features.settings.backup.import.uploadInit')
        }

        // 步骤1: 初始化分片上传（后端计算并返回 chunk_size 和 total_chunks）
        const initResponse = await axios.post('/api/backup/upload/init', {
            filename: file.name,
            total_size: file.size
        })

        if (initResponse.data.status !== 'ok') {
            throw new Error(initResponse.data.message)
        }

        uploadId.value = initResponse.data.data.upload_id
        chunkSize.value = initResponse.data.data.chunk_size
        const totalChunks = initResponse.data.data.total_chunks

        // 步骤2: 并行分片上传（5个并发连接）
        uploadProgress.value.message = t('features.settings.backup.import.uploadingChunks')
        
        await uploadChunksInParallel(file, totalChunks, uploadId.value, chunkSize.value)

        // 步骤3: 完成上传
        uploadProgress.value.message = t('features.settings.backup.import.uploadComplete')

        const completeResponse = await axios.post('/api/backup/upload/complete', {
            upload_id: uploadId.value
        })

        if (completeResponse.data.status !== 'ok') {
            throw new Error(completeResponse.data.message)
        }

        uploadedFilename.value = completeResponse.data.data.filename

        // 步骤4: 预检查
        uploadProgress.value.message = t('features.settings.backup.import.checking')

        const checkResponse = await axios.post('/api/backup/check', {
            filename: uploadedFilename.value
        })

        if (checkResponse.data.status !== 'ok') {
            throw new Error(checkResponse.data.message)
        }

        checkResult.value = checkResponse.data.data
        
        // 检查是否有效
        if (!checkResult.value.valid) {
            importStatus.value = 'failed'
            importError.value = checkResult.value.error || t('features.settings.backup.import.invalidBackup')
            return
        }

        // 显示确认对话框
        importStatus.value = 'confirm'

    } catch (error) {
        // 上传失败时尝试清理已上传的分片
        if (uploadId.value) {
            try {
                await axios.post('/api/backup/upload/abort', {
                    upload_id: uploadId.value
                })
            } catch (abortError) {
                console.error('Failed to abort upload:', abortError)
            }
        }
        
        importStatus.value = 'failed'
        importError.value = error.response?.data?.message || error.message || 'Upload failed'
    }
}

// 确认导入
const confirmImport = async () => {
    if (!uploadedFilename.value) return

    importStatus.value = 'processing'
    importProgress.value = { current: 0, total: 100, message: '' }

    try {
        const response = await axios.post('/api/backup/import', {
            filename: uploadedFilename.value,
            confirmed: true
        })

        if (response.data.status === 'ok') {
            importTaskId.value = response.data.data.task_id
            pollImportProgress()
        } else {
            throw new Error(response.data.message)
        }
    } catch (error) {
        importStatus.value = 'failed'
        importError.value = error.response?.data?.message || error.message || 'Import failed'
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
const resetImport = async () => {
    // 如果有进行中的上传，先取消
    if (uploadId.value && importStatus.value === 'uploading') {
        try {
            await axios.post('/api/backup/upload/abort', {
                upload_id: uploadId.value
            })
        } catch (error) {
            console.error('Failed to abort upload:', error)
        }
    }
    
    importStatus.value = 'idle'
    importFile.value = null
    importTaskId.value = null
    importProgress.value = { current: 0, total: 100, message: '' }
    importError.value = ''
    uploadedFilename.value = ''
    checkResult.value = null
    uploadId.value = ''
    chunkSize.value = 0
    uploadProgress.value = { uploaded: 0, total: 0, percent: 0, message: '' }
}

// 下载备份（使用浏览器原生下载，可显示下载进度）
const downloadBackup = (filename) => {
    // 获取 token 用于鉴权（因为浏览器原生下载无法携带 Authorization header）
    const token = localStorage.getItem('token')
    if (!token) {
        alert(t('core.common.unauthorized'))
        return
    }
    
    // 直接使用浏览器下载，这样可以看到原生下载进度条
    const downloadUrl = `/api/backup/download?filename=${encodeURIComponent(filename)}&token=${encodeURIComponent(token)}`
    
    // 创建隐藏的 a 标签触发下载
    const link = document.createElement('a')
    link.href = downloadUrl
    link.download = filename
    link.style.display = 'none'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
}

// 从列表中恢复备份
const restoreFromList = async (filename) => {
    // 切换到导入标签页并设置文件名
    uploadedFilename.value = filename
    
    // 预检查
    try {
        const checkResponse = await axios.post('/api/backup/check', {
            filename: filename
        })

        if (checkResponse.data.status !== 'ok') {
            throw new Error(checkResponse.data.message)
        }

        checkResult.value = checkResponse.data.data
        
        if (!checkResult.value.valid) {
            alert(checkResult.value.error || t('features.settings.backup.import.invalidBackup'))
            return
        }

        // 切换到导入标签页并显示确认
        activeTab.value = 'import'
        importStatus.value = 'confirm'

    } catch (error) {
        alert(error.response?.data?.message || error.message || 'Check failed')
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

// 重命名相关函数
const openRenameDialog = (filename) => {
    renameOldFilename.value = filename
    // 移除 .zip 后缀，只显示文件名部分
    renameNewName.value = filename.replace(/\.zip$/i, '')
    renameError.value = ''
    renameDialogOpen.value = true
}

const closeRenameDialog = () => {
    renameDialogOpen.value = false
    renameOldFilename.value = ''
    renameNewName.value = ''
    renameError.value = ''
}

// 文件名验证规则
const renameValidationRule = (value) => {
    if (!value) return t('features.settings.backup.list.renameRequired')
    // 检查是否包含非法字符
    if (/[\\/:*?"<>|]/.test(value)) {
        return t('features.settings.backup.list.renameInvalidChars')
    }
    // 检查是否包含路径遍历字符
    if (value.includes('..')) {
        return t('features.settings.backup.list.renameInvalidChars')
    }
    return true
}

const confirmRename = async () => {
    if (!renameNewName.value || renameError.value) return
    
    // 前端验证
    const validationResult = renameValidationRule(renameNewName.value)
    if (validationResult !== true) {
        renameError.value = validationResult
        return
    }

    renameLoading.value = true
    renameError.value = ''

    try {
        const response = await axios.post('/api/backup/rename', {
            filename: renameOldFilename.value,
            new_name: renameNewName.value
        })

        if (response.data.status === 'ok') {
            closeRenameDialog()
            loadBackupList()
        } else {
            renameError.value = response.data.message || t('features.settings.backup.list.renameFailed')
        }
    } catch (error) {
        renameError.value = error.response?.data?.message || error.message || t('features.settings.backup.list.renameFailed')
    } finally {
        renameLoading.value = false
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

// 格式化日期（从时间戳）
const formatDate = (timestamp) => {
    return new Date(timestamp * 1000).toLocaleString()
}

// 格式化 ISO 日期字符串
const formatISODate = (isoString) => {
    if (!isoString) return ''
    try {
        return new Date(isoString).toLocaleString()
    } catch {
        return isoString
    }
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
const resetAll = async () => {
    resetExport()
    await resetImport()
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

/* 禁用 Chip 的交互效果 */
.non-interactive-chip {
    pointer-events: none;
    cursor: default;
}

.non-interactive-chip:hover {
    box-shadow: none !important;
}
</style>