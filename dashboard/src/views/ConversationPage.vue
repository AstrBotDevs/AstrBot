<template>
    <div class="conversation-page">
        <v-container fluid class="pa-0">
            <!-- 对话列表部分 -->
            <v-card flat>
                <v-card-title class="d-flex align-center py-3 px-4">
                    <span class="text-h4">{{ tm('history.title') }}</span>
                    <v-chip size="small" class="ml-2">{{ pagination.total || 0 }}</v-chip>
                    <v-row class="me-4 ms-4" dense>
                        <v-col cols="12" sm="6" md="4">
                            <v-combobox v-model="platformFilter" :label="tm('filters.platform')"
                                :items="availablePlatforms" chips multiple clearable variant="solo-filled" flat
                                density="compact" hide-details :disabled="loading">
                                <template v-slot:selection="{ item }">
                                    <v-chip size="small" label>
                                        {{ item.title }}
                                    </v-chip>
                                </template>
                            </v-combobox>
                        </v-col>

                        <v-col cols="12" sm="6" md="4">
                            <v-select v-model="messageTypeFilter" :label="tm('filters.type')" :items="messageTypeItems"
                                chips multiple clearable variant="solo-filled" density="compact" hide-details flat
                                :disabled="loading">
                                <template v-slot:selection="{ item }">
                                    <v-chip size="small" variant="solo-filled" label>
                                        {{ item.title }}
                                    </v-chip>
                                </template>
                            </v-select>
                        </v-col>

                        <v-col cols="12" sm="12" md="4">
                            <v-text-field v-model="search" prepend-inner-icon="mdi-magnify"
                                :label="tm('filters.search')" hide-details density="compact" variant="solo-filled" flat
                                clearable :disabled="loading"></v-text-field>
                        </v-col>
                    </v-row>
                    <v-btn color="primary" prepend-icon="mdi-refresh" variant="tonal" @click="fetchConversations"
                        :loading="loading" size="small" class="mr-2">
                        {{ tm('history.refresh') }}
                    </v-btn>
                    <v-btn 
                        v-if="selectedItems.length > 0" 
                        color="error" 
                        prepend-icon="mdi-delete"
                        variant="tonal" 
                        @click="confirmBatchDelete" 
                        :disabled="loading"
                        size="small">
                        {{ tm('batch.deleteSelected', { count: selectedItems.length }) }}
                    </v-btn>
                </v-card-title>

                <v-divider></v-divider>

                <v-card-text class="pa-0">
                    <v-data-table v-model="selectedItems" :headers="tableHeaders" :items="conversations"
                        :loading="loading" style="font-size: 12px;" density="comfortable" hide-default-footer
                        class="elevation-0" :items-per-page="pagination.page_size"
                        :items-per-page-options="pageSizeOptions" show-select return-object
                        :disabled="loading" @update:options="handleTableOptions">
                        <template v-slot:item.title="{ item }">
                            <div class="d-flex align-center">
                                <span>{{ item.title || tm('status.noTitle') }}</span>
                            </div>
                        </template>

                        <template v-slot:item.platform="{ item }">
                            <v-chip size="small" label>
                                {{ item.sessionInfo.platform || tm('status.unknown') }}
                            </v-chip>
                        </template>

                        <template v-slot:item.messageType="{ item }">
                            <v-chip size="small" label>
                                {{ getMessageTypeDisplay(item.sessionInfo.messageType) }}
                            </v-chip>
                        </template>

                        <template v-slot:item.sessionId="{ item }">
                            <span>{{ item.sessionInfo.sessionId || tm('status.unknown') }}</span>
                        </template>

                        <template v-slot:item.created_at="{ item }">
                            {{ formatTimestamp(item.created_at) }}
                        </template>

                        <template v-slot:item.updated_at="{ item }">
                            {{ formatTimestamp(item.updated_at) }}
                        </template>

                        <template v-slot:item.actions="{ item }">
                            <div class="actions-wrapper">
                                <v-btn icon variant="plain" size="x-small" class="action-button"
                                    @click="viewConversation(item)" :disabled="loading">
                                    <v-icon>mdi-eye</v-icon>
                                </v-btn>
                                <v-btn icon variant="plain" size="x-small" class="action-button"
                                    @click="editConversation(item)" :disabled="loading">
                                    <v-icon>mdi-pencil</v-icon>
                                </v-btn>
                                <v-btn icon color="error" variant="plain" size="x-small" class="action-button"
                                    @click="confirmDeleteConversation(item)" :disabled="loading">
                                    <v-icon>mdi-delete</v-icon>
                                </v-btn>
                            </div>
                        </template>

                        <template v-slot:no-data>
                            <div class="d-flex flex-column align-center py-6">
                                <v-icon size="64" color="grey lighten-1">mdi-chat-remove</v-icon>
                                <span class="text-subtitle-1 text-disabled mt-3">{{ tm('status.noData') }}</span>
                            </div>
                        </template>
                    </v-data-table>

                    <!-- 分页控制 -->
                    <div class="d-flex justify-center py-3">
                        <!-- 每页大小选择器 -->
                        <div class="d-flex justify-between align-center px-4 py-2 bg-grey-lighten-5">
                            <div class="d-flex align-center">
                                <span class="text-caption mr-2">{{ tm('pagination.itemsPerPage') }}:</span>
                                <v-select v-model="pagination.page_size" :items="pageSizeOptions" variant="outlined"
                                    density="compact" hide-details style="max-width: 100px;"
                                    :disabled="loading" @update:model-value="onPageSizeChange"></v-select>
                            </div>
                            <div class="text-caption ml-4">
                                {{ tm('pagination.showingItems', {
                                    start: Math.min((pagination.page - 1) * pagination.page_size + 1, pagination.total),
                                    end: Math.min(pagination.page * pagination.page_size, pagination.total),
                                    total: pagination.total
                                }) }}
                            </div>
                        </div>
                        <v-pagination v-model="pagination.page" :length="pagination.total_pages" :disabled="loading"
                            @update:model-value="fetchConversations" rounded="circle" :total-visible="7"></v-pagination>
                    </div>
                </v-card-text>
            </v-card>
        </v-container>

        <!-- 对话详情对话框 -->
        <v-dialog v-model="dialogView" max-width="900px" scrollable>
            <v-card class="conversation-detail-card">
                <v-card-title class="ml-2 mt-2 d-flex align-center">
                    <span class="text-truncate">{{ selectedConversation?.title || tm('status.noTitle') }}</span>
                    <v-spacer></v-spacer>
                    <div class="d-flex align-center" v-if="selectedConversation?.sessionInfo">
                        <v-chip text-color="primary" size="small" class="mr-2" rounded="md">
                            {{ selectedConversation.sessionInfo.platform }}
                        </v-chip>
                        <v-chip text-color="secondary" size="small" rounded="md">
                            {{ getMessageTypeDisplay(selectedConversation.sessionInfo.messageType) }}
                        </v-chip>
                    </div>
                </v-card-title>

                <v-card-text>
                    <div class="mb-4 d-flex align-center">
                        <v-btn color="secondary" variant="tonal" size="small" class="mr-2"
                            @click="isEditingHistory = !isEditingHistory">
                            <v-icon class="mr-1">{{ isEditingHistory ? 'mdi-eye' : 'mdi-pencil' }}</v-icon>
                            {{ isEditingHistory ? tm('dialogs.view.previewMode') : tm('dialogs.view.editMode') }}
                        </v-btn>
                        <v-btn v-if="isEditingHistory" color="success" variant="tonal" size="small"
                            :loading="savingHistory" @click="saveHistoryChanges">
                            <v-icon class="mr-1">mdi-content-save</v-icon>
                            {{ tm('dialogs.view.saveChanges') }}
                        </v-btn>
                    </div>

                    <!-- 编辑模式 - Monaco编辑器 -->
                    <div v-if="isEditingHistory" class="monaco-editor-container">
                        <VueMonacoEditor v-model:value="editedHistory" theme="vs-dark" language="json" :options="{
                            automaticLayout: true,
                            fontSize: 13,
                            tabSize: 2,
                            minimap: { enabled: false },
                            scrollBeyondLastLine: false,
                            wordWrap: 'on'
                        }" @editorDidMount="onMonacoMounted" />
                    </div>

                    <!-- 预览模式 - 聊天界面 -->
                    <div v-else class="conversation-messages-container">
                        <!-- 空对话提示 -->
                        <div v-if="conversationHistory.length === 0" class="text-center py-5">
                            <v-icon size="48" color="grey">mdi-chat-remove</v-icon>
                            <p class="text-disabled mt-2">{{ tm('status.emptyContent') }}</p>
                        </div>

                        <!-- 消息列表组件 -->
                        <MessageList v-else :messages="formattedMessages" :isDark="false" />
                    </div>
                </v-card-text>

                <v-card-actions class="pa-4">
                    <v-spacer></v-spacer>
                    <v-btn variant="text" @click="closeHistoryDialog">
                        {{ tm('dialogs.view.close') }}
                    </v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>

        <!-- 编辑对话框 -->
        <v-dialog v-model="dialogEdit" max-width="500px">
            <v-card>
                <v-card-title class="bg-primary text-white py-3">
                    <v-icon color="white" class="me-2">mdi-pencil</v-icon>
                    <span>{{ tm('dialogs.edit.title') }}</span>
                </v-card-title>

                <v-card-text class="py-4">
                    <v-form ref="form" v-model="valid">
                        <v-text-field v-model="editedItem.title" :label="tm('dialogs.edit.titleLabel')"
                            :placeholder="tm('dialogs.edit.titlePlaceholder')" variant="outlined" density="comfortable"
                            class="mb-3"></v-text-field>
                    </v-form>
                </v-card-text>

                <v-divider></v-divider>

                <v-card-actions class="pa-4">
                    <v-spacer></v-spacer>
                    <v-btn variant="text" @click="dialogEdit = false" :disabled="loading">
                        {{ tm('dialogs.edit.cancel') }}
                    </v-btn>
                    <v-btn color="primary" @click="saveConversation" :loading="loading">
                        {{ tm('dialogs.edit.save') }}
                    </v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>

        <!-- 删除确认对话框 -->
        <v-dialog v-model="dialogDelete" max-width="500px">
            <v-card>
                <v-card-title class="bg-error text-white py-3">
                    <v-icon color="white" class="me-2">mdi-alert</v-icon>
                    <span>{{ tm('dialogs.delete.title') }}</span>
                </v-card-title>

                <v-card-text class="py-4">
                    <p>{{ tm('dialogs.delete.message', { title: selectedConversation?.title || tm('status.noTitle') })
                        }}</p>
                </v-card-text>

                <v-divider></v-divider>

                <v-card-actions class="pa-4">
                    <v-spacer></v-spacer>
                    <v-btn variant="text" @click="dialogDelete = false" :disabled="loading">
                        {{ tm('dialogs.delete.cancel') }}
                    </v-btn>
                    <v-btn color="error" @click="deleteConversation" :loading="loading">
                        {{ tm('dialogs.delete.confirm') }}
                    </v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>

        <!-- 批量删除确认对话框 -->
        <v-dialog v-model="dialogBatchDelete" max-width="600px">
            <v-card>
                <v-card-title class="bg-error text-white py-3">
                    <v-icon color="white" class="me-2">mdi-delete</v-icon>
                    <span>{{ tm('dialogs.batchDelete.title') }}</span>
                </v-card-title>

                <v-card-text class="py-4">
                    <p class="mb-3">{{ tm('dialogs.batchDelete.message', { count: selectedItems.length }) }}</p>

                    <!-- 显示前几个要删除的对话 -->
                    <div v-if="selectedItems.length > 0" class="mb-3">
                        <v-chip v-for="(item, index) in selectedItems.slice(0, 5)" :key="`${item.user_id}-${item.cid}`"
                            size="small" class="mr-1 mb-1" closable @click:close="removeFromSelection(item)"
                            :disabled="loading">
                            {{ item.title || tm('status.noTitle') }}
                        </v-chip>
                        <v-chip v-if="selectedItems.length > 5" size="small" class="mr-1 mb-1">
                            {{ tm('dialogs.batchDelete.andMore', { count: selectedItems.length - 5 }) }}
                        </v-chip>
                    </div>

                    <v-alert type="warning" variant="tonal" class="mb-3">
                        {{ tm('dialogs.batchDelete.warning') }}
                    </v-alert>
                </v-card-text>

                <v-divider></v-divider>

                <v-card-actions class="pa-4">
                    <v-spacer></v-spacer>
                    <v-btn variant="text" @click="dialogBatchDelete = false" :disabled="loading">
                        {{ tm('dialogs.batchDelete.cancel') }}
                    </v-btn>
                    <v-btn color="error" @click="batchDeleteConversations" :loading="loading">
                        {{ tm('dialogs.batchDelete.confirm') }}
                    </v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>

        <!-- 消息提示 -->
        <v-snackbar :timeout="3000" elevation="24" :color="messageType" v-model="showMessage" location="top">
            {{ message }}
        </v-snackbar>
    </div>
</template>

<script>
import axios from 'axios';
import { VueMonacoEditor } from '@guolao/vue-monaco-editor';
import MarkdownIt from 'markdown-it';
import { useCommonStore } from '@/stores/common';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import MessageList from '@/components/chat/MessageList.vue';

// 配置markdown-it，默认安全设置
const md = new MarkdownIt({
    html: false,        // 禁用HTML标签（关键！）
    breaks: true,       // 换行转<br>
    linkify: true,      // 自动转链接
    typographer: false  // 禁用智能引号（避免干扰）
});

export default {
    name: 'ConversationPage',
    components: {
        VueMonacoEditor,
        MessageList
    },

    setup() {
        const { t, locale } = useI18n();
        const { tm } = useModuleI18n('features/conversation');

        return {
            t,
            tm,
            locale
        };
    },

    data() {
        return {
            // 表格数据
            conversations: [],
            search: '',
            headers: [],
            selectedItems: [], // 批量选择的项目

            // 筛选条件
            platformFilter: [],
            messageTypeFilter: [],
            lastAppliedFilters: null, // 记录上次应用的筛选条件

            // 分页数据
            pagination: {
                page: 1,
                page_size: 20,
                total: 0,
                total_pages: 0
            },
            pageSizeOptions: [10, 20, 50, 100], // 每页大小选项

            // 对话框控制
            dialogView: false,
            dialogEdit: false,
            dialogDelete: false,
            dialogBatchDelete: false, // 批量删除对话框

            // 选中的对话
            selectedConversation: null,
            conversationHistory: [],

            // 编辑表单
            editedItem: {
                user_id: '',
                cid: '',
                title: ''
            },

            // 表单验证
            valid: true,

            // 状态控制
            loading: false,
            showMessage: false,
            message: '',
            messageType: 'success',

            // 对话历史编辑
            isEditingHistory: false,
            editedHistory: '',
            savingHistory: false,
            monacoEditor: null,

            commonStore: useCommonStore()
        }
    },

    watch: {
        // 监听筛选条件变化，使用防抖处理
        platformFilter() {
            this.debouncedApplyFilters();
        },
        messageTypeFilter() {
            this.debouncedApplyFilters();
        },
        search() {
            this.debouncedApplyFilters();
        }
    },

    created() {
        // 创建一个防抖函数，避免频繁请求
        this.debouncedApplyFilters = this.debounce(() => {
            // 重置到第一页
            this.pagination.page = 1;
            this.fetchConversations();
        }, 300);
    },

    computed: {
        // 动态表头
        tableHeaders() {
            return [
                { title: this.tm('table.headers.title'), key: 'title', sortable: true },
                {
                    title: this.tm('table.headers.sessionId'),
                    align: 'center',
                    children: [
                        { title: this.tm('table.headers.platform'), key: 'platform', sortable: true, width: '120px' },
                        { title: this.tm('table.headers.type'), key: 'messageType', sortable: true, width: '100px' },
                        { title: '会话 ID', key: 'sessionId', sortable: true, width: '100px' },
                    ],
                },
                { title: this.tm('table.headers.createdAt'), key: 'created_at', sortable: true, width: '180px' },
                { title: this.tm('table.headers.updatedAt'), key: 'updated_at', sortable: true, width: '180px' },
                { title: this.tm('table.headers.actions'), key: 'actions', sortable: false, align: 'center' }
            ];
        },

        // 可用平台列表
        availablePlatforms() {
            const platforms = []
            // 解析 tutorial_map
            const tutorialMap = this.commonStore.tutorial_map;
            for (const platform in tutorialMap) {
                if (tutorialMap.hasOwnProperty(platform)) {
                    platforms.push({
                        title: platform,
                        value: platform
                    })
                }
            }
            return platforms;
        },

        // 可用消息类型列表
        messageTypeItems() {
            return [
                { title: this.tm('messageTypes.group'), value: 'GroupMessage' },
                { title: this.tm('messageTypes.friend'), value: 'FriendMessage' },
            ];
        },

        // 当前的筛选条件对象
        currentFilters() {
            const platforms = this.platformFilter.map(item =>
                typeof item === 'object' ? item.value : item
            );
            return {
                platforms: platforms,
                messageTypes: this.messageTypeFilter,
                search: this.search
            };
        },

        // 将对话历史转换为 MessageList 组件期望的格式
        formattedMessages() {
            return this.conversationHistory.map(msg => {
                console.log('处理消息:', msg.role, msg.image_url, msg.audio_url);
                if (msg.role === 'user') {
                    return {
                        content: {
                            type: 'user',
                            message: this.extractTextFromContent(msg.content),
                            image_url: this.extractImagesFromContent(msg.content),
                        }
                    };
                } else {
                    return {
                        content: {
                            type: 'bot',
                            message: this.extractTextFromContent(msg.content),
                            embedded_images: this.extractImagesFromContent(msg.content),
                        }
                    };
                }
            });
        }
    },

    mounted() {
        this.fetchConversations();
    },

    methods: {
        // Monaco编辑器挂载后的回调
        onMonacoMounted(editor) {
            this.monacoEditor = editor;
            // 添加JSON格式校验
            editor.onDidChangeModelContent(() => {
                try {
                    JSON.parse(this.editedHistory);
                    // 有效的JSON格式
                    editor.getAction('editor.action.formatDocument').run();
                } catch (e) {
                    // 无效的JSON格式，不做处理，Monaco编辑器会自动提示
                }
            });
        },

        // 添加防抖函数
        debounce(func, wait) {
            let timeout;
            return function () {
                const context = this;
                const args = arguments;
                clearTimeout(timeout);
                timeout = setTimeout(() => {
                    func.apply(context, args);
                }, wait);
            };
        },

        // 处理表格选项变更（页面大小等）
        handleTableOptions(options) {
            // 处理页面大小变更
            if (options.itemsPerPage !== this.pagination.page_size) {
                this.pagination.page_size = options.itemsPerPage;
                this.pagination.page = 1; // 重置到第一页
                this.fetchConversations();
            }
        },

        // 从会话ID解析平台和消息类型信息
        parseSessionId(userId) {
            if (!userId) return { platform: 'default', messageType: 'default', sessionId: '' };

            // 使用冒号进行分割，格式: platform:messageType:sessionId
            const parts = userId.split(':');

            if (parts.length >= 3) {
                return {
                    platform: parts[0] || 'default',
                    messageType: parts[1] || 'default',
                    sessionId: parts.slice(2).join(':') // 保留可能包含冒号的后续部分
                };
            }

            return { platform: 'default', messageType: 'default', sessionId: userId };
        },

        // 获取消息类型的显示文本
        getMessageTypeDisplay(messageType) {
            const typeMap = {
                'GroupMessage': this.tm('messageTypes.group'),
                'FriendMessage': this.tm('messageTypes.friend'),
                'default': this.tm('messageTypes.unknown')
            };

            return typeMap[messageType] || typeMap.default;
        },

        // 获取对话列表
        async fetchConversations() {
            this.loading = true;
            try {
                // 准备请求参数，包含分页和筛选条件
                const params = {
                    page: this.pagination.page,
                    page_size: this.pagination.page_size
                };

                // 添加筛选条件 - 处理combobox的混合数据格式
                if (this.platformFilter.length > 0) {
                    const platforms = this.platformFilter.map(item =>
                        typeof item === 'object' ? item.value : item
                    );
                    params.platforms = platforms.join(',');
                }

                if (this.messageTypeFilter.length > 0) {
                    params.message_types = this.messageTypeFilter.join(',');
                }

                if (this.search) {
                    params.search = this.search.trim();
                }

                // 添加排除条件
                params.exclude_ids = 'astrbot';
                params.exclude_platforms = 'webchat';

                const response = await axios.get('/api/conversation/list', { params });

                this.lastAppliedFilters = { ...this.currentFilters }; // 记录已应用的筛选条件

                if (response.data.status === "ok") {
                    const data = response.data.data;

                    if (!data || !data.conversations) {
                        console.error('API 返回数据格式不符合预期:', data);
                        this.showErrorMessage(this.tm('messages.fetchError'));
                        return;
                    }

                    // 处理会话数据，解析sessionId
                    this.conversations = (data.conversations || []).map(conv => {
                        // 为每个会话添加会话信息
                        conv.sessionInfo = this.parseSessionId(conv.user_id);
                        return conv;
                    });

                    // 更新分页信息
                    if (data.pagination) {
                        this.pagination = {
                            page: data.pagination.page || 1,
                            page_size: data.pagination.page_size || 20,
                            total: data.pagination.total || 0,
                            total_pages: data.pagination.total_pages || 1
                        };
                    } else {
                        console.warn('API 响应中没有分页信息');
                    }
                } else {
                    this.showErrorMessage(response.data.message || this.tm('messages.fetchError'));
                }
            } catch (error) {
                console.error('获取对话列表出错:', error);
                if (error.response) {
                    console.error('错误响应数据:', error.response.data);
                    console.error('错误状态码:', error.response.status);
                }
                this.showErrorMessage(error.response?.data?.message || error.message || this.tm('messages.fetchError'));
            } finally {
                // this.loading = false;
                setTimeout(() => {
                    this.loading = false;
                }, 200);
            }
        },

        // 查看对话详情
        async viewConversation(item) {
            this.selectedConversation = item;
            this.loading = true;
            this.isEditingHistory = false;

            try {
                console.log(`正在请求对话详情，user_id=${item.user_id}, cid=${item.cid}`);
                const response = await axios.post('/api/conversation/detail', {
                    user_id: item.user_id,
                    cid: item.cid
                });

                if (response.data.status === "ok") {
                    try {
                        const historyData = response.data.data.history || '[]';
                        this.conversationHistory = JSON.parse(historyData);
                        this.editedHistory = JSON.stringify(this.conversationHistory, null, 2);
                    } catch (e) {
                        this.conversationHistory = [];
                        this.editedHistory = '[]';
                        console.error('解析对话历史失败:', e);
                    }
                    this.dialogView = true;
                } else {
                    this.showErrorMessage(response.data.message || this.tm('messages.historyError'));
                }
            } catch (error) {
                console.error('获取对话详情出错:', error);
                this.showErrorMessage(error.response?.data?.message || error.message || this.tm('messages.historyError'));
            } finally {
                this.loading = false;
            }
        },

        // 保存对话历史的修改
        async saveHistoryChanges() {
            if (!this.selectedConversation) return;

            this.savingHistory = true;

            try {
                // 验证JSON格式
                let historyJson;
                try {
                    historyJson = JSON.parse(this.editedHistory);
                } catch (e) {
                    this.showErrorMessage(this.tm('messages.invalidJson'));
                    return;
                }

                const response = await axios.post('/api/conversation/update_history', {
                    user_id: this.selectedConversation.user_id,
                    cid: this.selectedConversation.cid,
                    history: historyJson
                });

                if (response.data.status === "ok") {
                    this.conversationHistory = historyJson;
                    this.showSuccessMessage(this.tm('messages.historySaveSuccess'));
                    this.isEditingHistory = false;
                } else {
                    this.showErrorMessage(response.data.message || this.tm('messages.historySaveError'));
                }
            } catch (error) {
                console.error('更新对话历史出错:', error);
                this.showErrorMessage(error.response?.data?.message || error.message || this.tm('messages.historySaveError'));
            } finally {
                this.savingHistory = false;
            }
        },

        // 关闭对话历史对话框
        closeHistoryDialog() {
            if (this.isEditingHistory) {
                if (confirm(this.tm('dialogs.view.confirmClose'))) {
                    this.dialogView = false;
                }
            } else {
                this.dialogView = false;
            }
        },

        // 编辑对话
        editConversation(item) {
            this.selectedConversation = item;
            this.editedItem = Object.assign({}, item);
            this.dialogEdit = true;
        },

        // 保存编辑后的对话
        async saveConversation() {
            if (!this.$refs.form.validate()) return;

            this.loading = true;
            try {
                const response = await axios.post('/api/conversation/update', {
                    user_id: this.editedItem.user_id,
                    cid: this.editedItem.cid,
                    title: this.editedItem.title
                });

                if (response.data.status === "ok") {
                    // 更新本地数据
                    const index = this.conversations.findIndex(item => item.user_id === this.editedItem.user_id && item.cid === this.editedItem.cid
                    );

                    if (index !== -1) {
                        this.conversations[index].title = this.editedItem.title;
                    }

                    this.dialogEdit = false;
                    this.showSuccessMessage(this.tm('messages.saveSuccess'));

                    // 刷新数据
                    this.fetchConversations();
                } else {
                    this.showErrorMessage(response.data.message || this.tm('messages.saveError'));
                }
            } catch (error) {
                this.showErrorMessage(error.response?.data?.message || error.message || this.tm('messages.saveError'));
            } finally {
                this.loading = false;
            }
        },

        // 确认删除对话
        confirmDeleteConversation(item) {
            this.selectedConversation = item;
            this.dialogDelete = true;
        },

        // 删除对话
        async deleteConversation() {
            this.loading = true;
            try {
                const response = await axios.post('/api/conversation/delete', {
                    user_id: this.selectedConversation.user_id,
                    cid: this.selectedConversation.cid
                });

                if (response.data.status === "ok") {
                    const index = this.conversations.findIndex(item => item.user_id === this.selectedConversation.user_id && item.cid === this.selectedConversation.cid
                    );

                    if (index !== -1) {
                        this.conversations.splice(index, 1);
                    }

                    this.dialogDelete = false;
                    this.showSuccessMessage(this.tm('messages.deleteSuccess'));
                } else {
                    this.showErrorMessage(response.data.message || this.tm('messages.deleteError'));
                }
            } catch (error) {
                this.showErrorMessage(error.response?.data?.message || error.message || this.tm('messages.deleteError'));
            } finally {
                this.loading = false;
                this.selectedItems = this.selectedItems.filter(item =>
                    !(item.user_id === this.selectedConversation.user_id && item.cid === this.selectedConversation.cid)
                );
                this.selectedConversation = null;
            }
        },

        // 处理页面大小变更
        onPageSizeChange() {
            this.pagination.page = 1; // 重置到第一页
            this.fetchConversations();
        },

        // 确认批量删除
        confirmBatchDelete() {
            if (this.selectedItems.length === 0) {
                this.showErrorMessage(this.tm('messages.noItemSelected'));
                return;
            }
            this.dialogBatchDelete = true;
        },

        // 从选择中移除项目
        removeFromSelection(item) {
            const index = this.selectedItems.findIndex(selected =>
                selected.user_id === item.user_id && selected.cid === item.cid
            );
            if (index !== -1) {
                this.selectedItems.splice(index, 1);
            }
        },

        // 批量删除对话
        async batchDeleteConversations() {
            if (this.selectedItems.length === 0) {
                this.showErrorMessage(this.tm('messages.noItemSelected'));
                return;
            }

            this.loading = true;
            try {
                // 准备批量删除的数据
                const conversations = this.selectedItems.map(item => ({
                    user_id: item.user_id,
                    cid: item.cid
                }));

                const response = await axios.post('/api/conversation/delete', {
                    conversations: conversations
                });

                if (response.data.status === "ok") {
                    const result = response.data.data;
                    this.dialogBatchDelete = false;
                    this.selectedItems = []; // 清空选择

                    // 显示结果消息
                    if (result.failed_count > 0) {
                        this.showErrorMessage(
                            this.tm('messages.batchDeletePartial', {
                                deleted: result.deleted_count,
                                failed: result.failed_count
                            })
                        );
                    } else {
                        this.showSuccessMessage(
                            this.tm('messages.batchDeleteSuccess', {
                                count: result.deleted_count
                            })
                        );
                    }

                    // 刷新列表
                    this.fetchConversations();
                } else {
                    this.showErrorMessage(response.data.message || this.tm('messages.batchDeleteError'));
                }
            } catch (error) {
                console.error('批量删除对话出错:', error);
                this.showErrorMessage(error.response?.data?.message || error.message || this.tm('messages.batchDeleteError'));
            } finally {
                this.loading = false;
            }
        },

        // 格式化时间戳
        formatTimestamp(timestamp) {
            if (!timestamp) return this.tm('status.unknown');

            const date = new Date(timestamp * 1000);
            const locale = this.locale || 'zh-CN';
            return new Intl.DateTimeFormat(locale, {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false
            }).format(date);
        },

        // 显示成功消息
        showSuccessMessage(message) {
            this.message = message;
            this.messageType = 'success';
            this.showMessage = true;
        },

        // 显示错误消息
        showErrorMessage(message) {
            this.message = message;
            this.messageType = 'error';
            this.showMessage = true;
        },

        // 从内容中提取文本
        extractTextFromContent(content) {
            if (typeof content === 'string') {
                return content;
            } else if (Array.isArray(content)) {
                return content.filter(item => item.type === 'text')
                    .map(item => item.text)
                    .join('\n');
            } else if (typeof content === 'object') {
                return Object.values(content).filter(val => typeof val === 'string').join('');
            }
            return '';
        },

        // 从内容中提取图片URL
        extractImagesFromContent(content) {
            if (Array.isArray(content)) {
                return content.filter(item => item.type === 'image_url')
                    .map(item => item.image_url?.url)
                    .filter(url => url);
            }
            return [];
        }
    }
}
</script>

<style>
.actions-wrapper {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
}

.action-button {
    border-radius: 8px;
    font-weight: 500;
}

.monaco-editor-container {
    height: 500px;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

/* 聊天消息容器样式 */
.conversation-messages-container {
    max-height: 500px;
    overflow-y: auto;
    padding: 8px;
    border-radius: 8px;
    background-color: #f9f9f9;
}

/* 对话详情卡片 */
.conversation-detail-card {
    max-height: 90vh;
    display: flex;
    flex-direction: column;
}

/* 动画 */
@keyframes fadeIn {
    from {
        opacity: 0;
        transform: translateY(10px);
    }

    to {
        opacity: 1;
        transform: translateY(0);
    }
}
</style>