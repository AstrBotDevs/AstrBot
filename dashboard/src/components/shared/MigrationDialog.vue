<template>
    <v-dialog v-model="isOpen" persistent max-width="600" max-height="80vh" scrollable>
        <v-card>
            <v-card-title>
                {{ t('features.migration.dialog.title') }}
            </v-card-title>

            <v-card-text class="pa-6">
                <p class="mb-4">{{ t('features.migration.dialog.warning') }}</p>


                <div v-if="migrationCompleted" class="text-center py-8">
                    <v-icon size="64" color="success" class="mb-4">mdi-check-circle</v-icon>
                    <h3 class="mb-4">{{ t('features.migration.dialog.completed') }}</h3>
                    <p class="mb-4">{{ migrationResult?.message || t('features.migration.dialog.success') }}</p>
                    <v-alert type="info" variant="tonal" class="mb-4">
                        <template v-slot:prepend>
                            <v-icon>mdi-information</v-icon>
                        </template>
                        {{ t('features.migration.dialog.restartRecommended') }}
                    </v-alert>
                </div>

                <div v-else-if="migrating" class="migration-in-progress">
                    <div class="text-center py-4">
                        <v-progress-circular indeterminate color="primary" class="mb-4"></v-progress-circular>
                        <h3 class="mb-4">{{ t('features.migration.dialog.migrating') }}</h3>
                        <p class="mb-4">{{ t('features.migration.dialog.migratingSubtitle') }}</p>
                    </div>
                    <div class="console-container">
                        <ConsoleDisplayer ref="consoleDisplayer" :showLevelBtns="false" style="height: 300px;" />
                    </div>
                </div>

                <div v-else-if="loading" class="text-center py-8">
                    <v-progress-circular indeterminate color="primary" class="mb-4"></v-progress-circular>
                    <p>{{ t('features.migration.dialog.loading') }}</p>
                </div>

                <div v-else-if="error" class="text-center py-4">
                    <v-alert type="error" variant="tonal" class="mb-4">
                        <template v-slot:prepend>
                            <v-icon>mdi-alert</v-icon>
                        </template>
                        {{ error }}
                    </v-alert>
                    <v-btn color="primary" @click="loadPlatforms">
                        {{ t('features.migration.dialog.retry') }}
                    </v-btn>
                </div>

                <div v-else>
                    <div v-if="platformGroups.length === 0" class="text-center py-4">
                        <v-alert type="info" variant="tonal">
                            <template v-slot:prepend>
                                <v-icon>mdi-information</v-icon>
                            </template>
                            {{ t('features.migration.dialog.noPlatforms') }}
                        </v-alert>
                    </div>

                    <div v-else>
                        <div v-for="group in platformGroups" :key="group.type" class="mb-6">
                            <v-card variant="outlined" v-if="group.platforms.length > 1">
                                <v-card-subtitle class="py-2">
                                    {{ group.type }}
                                </v-card-subtitle>

                                <v-divider></v-divider>

                                <v-card-text style="padding: 16px;">
                                    <small>请选择该平台类型下您主要使用的平台适配器。</small>
                                    <v-radio-group v-model="selectedPlatforms[group.type]" :key="group.type"
                                        hide-details>
                                        <v-radio v-for="platform in group.platforms" :key="platform.id"
                                            :value="platform.id" :label="getPlatformLabel(platform)" color="primary"
                                            class="mb-1"></v-radio>
                                    </v-radio-group>
                                </v-card-text>
                            </v-card>
                        </div>
                    </div>
                </div>
            </v-card-text>

            <v-card-actions class="px-6 py-4">
                <v-spacer></v-spacer>
                <template v-if="migrationCompleted">
                    <v-btn color="grey" variant="text" @click="handleClose">
                        {{ t('core.common.close') }}
                    </v-btn>
                    <v-btn color="primary" variant="elevated" @click="restartAstrBot">
                        {{ t('features.migration.dialog.restartNow') }}
                    </v-btn>
                </template>
                <template v-else>
                    <v-btn color="grey" variant="text" @click="handleCancel" :disabled="migrating">
                        {{ t('core.common.cancel') }}
                    </v-btn>
                    <v-btn color="primary" variant="elevated" @click="handleMigration" :disabled="!canMigrate || migrating"
                        :loading="migrating">
                        {{ t('features.migration.dialog.startMigration') }}
                    </v-btn>
                </template>
            </v-card-actions>
        </v-card>
    </v-dialog>
    
    <WaitingForRestart ref="wfr"></WaitingForRestart>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import axios from 'axios'
import { useI18n } from '@/i18n/composables'
import ConsoleDisplayer from './ConsoleDisplayer.vue'
import WaitingForRestart from './WaitingForRestart.vue'

const { t } = useI18n()

const isOpen = ref(false)
const loading = ref(false)
const error = ref('')
const migrating = ref(false)
const migrationCompleted = ref(false)
const migrationResult = ref(null)
const platforms = ref([])
const selectedPlatforms = ref({})
const wfr = ref(null)

let resolvePromise = null

// 计算属性：将平台按类型分组
const platformGroups = computed(() => {
    const groups = {}
    platforms.value.forEach(platform => {
        const type = platform.platform_type || platform.type
        if (!groups[type]) {
            groups[type] = {
                type,
                platforms: []
            }
        }
        groups[type].platforms.push(platform)
    })
    return Object.values(groups)
})

// 计算属性：检查是否可以开始迁移
const canMigrate = computed(() => {
    return platformGroups.value.every(group => selectedPlatforms.value[group.type])
})

// 监听 isOpen 变化，当对话框打开时加载平台列表
watch(isOpen, (newVal) => {
    if (newVal) {
        loadPlatforms()
    } else {
        // 重置状态
        platforms.value = []
        selectedPlatforms.value = {}
        error.value = ''
        migrating.value = false
        migrationCompleted.value = false
        migrationResult.value = null
    }
})

// 加载平台列表
const loadPlatforms = async () => {
    loading.value = true
    error.value = ''

    try {
        const response = await axios.get('/api/config/platform/list')
        if (response.data.status === 'ok') {
            platforms.value = response.data.data.platforms || []

            // 为每个平台类型初始化默认选择（选择第一个）
            platformGroups.value.forEach(group => {
                if (group.platforms.length > 0) {
                    selectedPlatforms.value[group.type] = group.platforms[0].id
                }
            })
        } else {
            error.value = response.data.message || t('features.migration.dialog.loadError')
        }
    } catch (err) {
        console.error('Failed to load platforms:', err)
        error.value = t('features.migration.dialog.loadError')
    } finally {
        loading.value = false
    }
}

// 执行迁移
const handleMigration = async () => {
    migrating.value = true

    try {
        // 构建 platform_id_map
        const platformIdMap = {}

        Object.entries(selectedPlatforms.value).forEach(([type, platformId]) => {
            const selectedPlatform = platforms.value.find(p => p.id === platformId)
            if (selectedPlatform) {
                platformIdMap[type] = {
                    platform_id: platformId,
                    platform_type: type
                }
            }
        })

        console.log('Migration platform_id_map:', platformIdMap)

        const response = await axios.post('/api/update/migration', {
            platform_id_map: platformIdMap
        })

        if (response.data.status === 'ok') {
            migrationCompleted.value = true
            migrationResult.value = {
                success: true,
                message: response.data.message || t('features.migration.dialog.success')
            }
        } else {
            throw new Error(response.data.message || t('features.migration.dialog.migrationError'))
        }
    } catch (err) {
        console.error('Migration failed:', err)
        error.value = err.message || t('features.migration.dialog.migrationError')
    } finally {
        migrating.value = false
    }
}

// 取消操作
const handleCancel = () => {
    isOpen.value = false
    if (resolvePromise) {
        resolvePromise({ success: false, cancelled: true })
    }
}

// 关闭已完成的迁移对话框
const handleClose = () => {
    isOpen.value = false
    if (resolvePromise) {
        resolvePromise(migrationResult.value)
    }
}


// 获取平台显示标签
const getPlatformLabel = (platform) => {
    const name = platform.name || platform.id || 'Unknown'
    return `${name}`
}

// 重启 AstrBot
const restartAstrBot = () => {
    axios.post('/api/stat/restart-core').then(() => {
        if (wfr.value) {
            wfr.value.check();
        }
    })
}

// 打开对话框的方法
const open = () => {
    isOpen.value = true

    return new Promise((resolve) => {
        resolvePromise = resolve
    })
}

defineExpose({ open })
</script>

<style scoped>
.v-radio-group {
    max-height: 200px;
    overflow-y: auto;
}

.migration-in-progress {
    min-height: 400px;
}

.console-container {
    border: 1px solid var(--v-theme-border);
    border-radius: 8px;
    margin-top: 16px;
    overflow: hidden;
}
</style>
