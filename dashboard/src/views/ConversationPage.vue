<template>
    <div class="conversation-page">
        <v-container fluid class="pa-0">
            <!-- 页面标题 -->
            <v-row>
                <v-col cols="12">
                    <h1 class="text-h4 font-weight-bold mb-2">
                        <v-icon size="x-large" color="primary" class="me-2">mdi-chat-processing</v-icon>{{ tm('title') }}
                    </h1>
                    <p class="text-subtitle-1 text-medium-emphasis mb-4">
                        {{ tm('subtitle') }}
                    </p>
                </v-col>
            </v-row>

            <!-- 过滤器部分 -->
            <v-card class="mb-4" elevation="2">
                <v-card-title class="d-flex align-center py-3 px-4">
                    <v-icon color="primary" class="me-2">mdi-filter-variant</v-icon>
                    <span class="text-h6">{{ tm('filters.title') }}</span>
                    <v-spacer></v-spacer>
                    <v-btn color="primary" variant="text" @click="resetFilters" class="ml-2">
                        <v-icon class="mr-1">mdi-refresh</v-icon>{{ tm('filters.reset') }}
                    </v-btn>
                </v-card-title>

                <v-divider></v-divider>

                <v-card-text class="py-4">
                    <v-row>
                        <v-col cols="12" sm="6" md="4">
                            <v-select v-model="platformFilter" :label="tm('filters.platform')" :items="availablePlatforms" chips multiple
                                clearable variant="outlined" density="compact" hide-details>
                                <template v-slot:selection="{ item }">
                                    <v-chip size="small" :color="getPlatformColor(item.value)" label>
                                        {{ item.title }}
                                    </v-chip>
                                </template>
                            </v-select>
                        </v-col>

                        <v-col cols="12" sm="6" md="4">
                            <v-select v-model="messageTypeFilter" :label="tm('filters.type')" :items="messageTypeItems" chips multiple
                                clearable variant="outlined" density="compact" hide-details>
                                <template v-slot:selection="{ item }">
                                    <v-chip size="small" :color="getMessageTypeColor(item.value)" variant="outlined"
                                        label>
                                        {{ item.title }}
                                    </v-chip>
                                </template>
                            </v-select>
                        </v-col>

                        <v-col cols="12" sm="12" md="4">
                            <v-text-field v-model="search" prepend-inner-icon="mdi-magnify" :label="tm('filters.search')" hide-details
                                density="compact" variant="outlined" clearable></v-text-field>
                        </v-col>
                    </v-row>
                </v-card-text>
            </v-card>

            <!-- 对话列表部分 -->
            <v-card class="mb-6" elevation="2">
                <v-card-title class="d-flex align-center py-3 px-4">
                    <v-icon color="primary" class="me-2">mdi-message</v-icon>
                    <span class="text-h6">{{ tm('history.title') }}</span>
                    <v-chip color="info" size="small" class="ml-2">{{ pagination.total || 0 }}</v-chip>
                    <v-spacer></v-spacer>
                    <v-btn color="primary" prepend-icon="mdi-refresh" variant="tonal" @click="fetchConversations"
                        :loading="loading">
                        {{ tm('history.refresh') }}
                    </v-btn>
                </v-card-title>

                <v-divider></v-divider>

                <v-card-text class="pa-0">
                    <v-data-table :headers="tableHeaders" :items="conversations" :loading="loading" density="comfortable"
                        hide-default-footer items-per-page="10" class="elevation-0"
                        :items-per-page="pagination.page_size" :items-per-page-options="[10, 20, 50, 100]"
                        @update:options="handleTableOptions">
                        <template v-slot:item.title="{ item }">
                            <div class="d-flex align-center">
                                <v-icon color="primary" class="mr-2">mdi-chat</v-icon>
                                <span>{{ item.title || tm('status.noTitle') }}</span>
                            </div>
                        </template>

                        <template v-slot:item.platform="{ item }">
                            <v-chip :color="getPlatformColor(item.sessionInfo.platform)" size="small" label>
                                {{ item.sessionInfo.platform || tm('status.unknown') }}
                            </v-chip>
                        </template>

                        <template v-slot:item.messageType="{ item }">
                            <v-chip :color="getMessageTypeColor(item.sessionInfo.messageType)" size="small"
                                variant="outlined" label>
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
                                <v-btn color="primary" variant="flat" size="small" class="action-button"
                                    @click="viewConversation(item)">
                                    <v-icon class="mr-1">mdi-eye</v-icon>{{ tm('actions.view') }}
                                </v-btn>
                                <v-btn color="warning" variant="flat" size="small" class="action-button"
                                    @click="editConversation(item)">
                                    <v-icon class="mr-1">mdi-pencil</v-icon>{{ tm('actions.edit') }}
                                </v-btn>
                                <v-btn color="error" variant="flat" size="small" class="action-button"
                                    @click="confirmDeleteConversation(item)">
                                    <v-icon class="mr-1">mdi-delete</v-icon>{{ tm('actions.delete') }}
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
                    <div class="d-flex justify-end pa-4">
                        <v-pagination v-model="pagination.page" :length="pagination.total_pages" :disabled="loading"
                            @update:model-value="fetchConversations" rounded="circle"></v-pagination>
                    </div>
                </v-card-text>
            </v-card>
        </v-container>

        <!-- 对话详情对话框 -->
        <v-dialog v-model="dialogView" max-width="900px" scrollable>
            <v-card class="conversation-detail-card">
                <v-card-title class="bg-primary text-white py-3 d-flex align-center">
                    <v-icon color="white" class="me-2">mdi-eye</v-icon>
                    <span class="text-truncate">{{ selectedConversation?.title || tm('status.noTitle') }}</span>
                    <v-spacer></v-spacer>

                    <div class="d-flex align-center" v-if="selectedConversation?.sessionInfo">
                        <v-chip color="white" text-color="primary" size="small" class="mr-2">
                            {{ selectedConversation.sessionInfo.platform }}
                        </v-chip>
                        <v-chip color="white" text-color="secondary" size="small">
                            {{ getMessageTypeDisplay(selectedConversation.sessionInfo.messageType) }}
                        </v-chip>
                    </div>
                </v-card-title>

                <v-divider></v-divider>

                <v-card-text class="py-4">
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

                        <!-- 消息列表 -->
                        <div v-else class="message-list">
                            <div class="message-item" v-for="(msg, index) in conversationHistory" :key="index">
                                <!-- 用户消息 -->
                                <div v-if="msg.role === 'user'" class="user-message">
                                    <div class="message-bubble user-bubble">
                                        <span v-html="formatMessage(msg.content)"></span>

                                        <!-- 图片附件 -->
                                        <div class="image-attachments" v-if="msg.image_url && msg.image_url.length > 0">
                                            <div v-for="(img, imgIndex) in msg.image_url" :key="imgIndex"
                                                class="image-attachment">
                                                <img :src="img" class="attached-image" />
                                            </div>
                                        </div>

                                        <!-- 音频附件 -->
                                        <div class="audio-attachment" v-if="msg.audio_url">
                                            <audio controls class="audio-player">
                                                <source :src="msg.audio_url" type="audio/wav">
                                                {{ tm('status.audioNotSupported') }}
                                            </audio>
                                        </div>
                                    </div>
                                    <v-avatar class="user-avatar" color="deep-purple-lighten-3" size="36">
                                        <v-icon icon="mdi-account" />
                                    </v-avatar>
                                </div>

                                <!-- 机器人消息 -->
                                <div v-else class="bot-message">
                                    <v-avatar class="bot-avatar" color="deep-purple" size="36">
                                        <span class="text-h6">✨</span>
                                    </v-avatar>
                                    <div class="message-bubble bot-bubble">
                                        <div v-html="formatMessage(msg.content)" class="markdown-content"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </v-card-text>

                <v-divider></v-divider>

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
                        <v-text-field v-model="editedItem.title" :label="tm('dialogs.edit.titleLabel')" :placeholder="tm('dialogs.edit.titlePlaceholder')" variant="outlined"
                            density="comfortable" class="mb-3"></v-text-field>
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
                    <p>{{ tm('dialogs.delete.message', { title: selectedConversation?.title || tm('status.noTitle') }) }}</p>
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
        VueMonacoEditor
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

            // 筛选条件
            platformFilter: [],
            messageTypeFilter: [],
            lastAppliedFilters: null, // 记录上次应用的筛选条件

            // 平台颜色映射
            platformColors: {
                'telegram': 'blue-lighten-1',
                'qq_official': 'purple-lighten-1',
                'qq_official_webhook': 'purple-lighten-2',
                'gewechat': 'green-lighten-1',
                'aiocqhttp': 'deep-purple-lighten-1',
                'lark': 'cyan-darken-1',
                'wecom': 'green-darken-1',
                'dingtalk': 'blue-darken-2',
                'default': 'grey-lighten-1'
            },

            // 消息类型颜色映射
            messageTypeColors: {
                'GroupMessage': 'green',
                'FriendMessage': 'blue',
                'GuildMessage': 'purple',
                'default': 'grey'
            },

            // 分页数据
            pagination: {
                page: 1,
                page_size: 20,
                total: 0,
                total_pages: 0
            },

            // 对话框控制
            dialogView: false,
            dialogEdit: false,
            dialogDelete: false,

            // 选中的对话
            selectedConversation: null,
            conversationHistory: [],

            // 编辑表单
            editedItem: {
                user_id: '',
                cid: '',
                title: ''
            },
            defaultItem: {
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
                { title: this.tm('table.headers.platform'), key: 'platform', sortable: true, width: '120px' },
                { title: this.tm('table.headers.type'), key: 'messageType', sortable: true, width: '100px' },
                { title: this.tm('table.headers.sessionId'), key: 'sessionId', sortable: true, width: '100px' },
                { title: this.tm('table.headers.createdAt'), key: 'created_at', sortable: true, width: '180px' },
                { title: this.tm('table.headers.updatedAt'), key: 'updated_at', sortable: true, width: '180px' },
                { title: this.tm('table.headers.actions'), key: 'actions', sortable: false, align: 'center', width: '240px' }
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

        // 筛选后的对话 - 现在只用于额外的客户端筛选（排除astrbot和webchat）
        filteredConversations() {
            return this.conversations.filter(conv => {
                // 排除 user_id 为 astrbot 或 platform 为 webchat 的对话
                if (conv.user_id === 'astrbot' || conv.sessionInfo?.platform === 'webchat') {
                    return false;
                }
                return true;
            });
        },

        // 当前的筛选条件对象
        currentFilters() {
            return {
                platforms: this.platformFilter,
                messageTypes: this.messageTypeFilter,
                search: this.search
            };
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

        // 重置过滤条件
        resetFilters() {
            this.platformFilter = [];
            this.messageTypeFilter = [];
            this.search = '';
            // 立即应用筛选，不使用防抖
            this.pagination.page = 1;
            this.fetchConversations();
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

        // 获取平台对应的颜色
        getPlatformColor(platform) {
            return this.platformColors[platform] || this.platformColors.default;
        },

        // 获取消息类型对应的颜色
        getMessageTypeColor(messageType) {
            return this.messageTypeColors[messageType] || this.messageTypeColors.default;
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

                // 添加筛选条件
                if (this.platformFilter.length > 0) {
                    params.platforms = this.platformFilter.join(',');
                }

                if (this.messageTypeFilter.length > 0) {
                    params.message_types = this.messageTypeFilter.join(',');
                }

                if (this.search) {
                    params.search = this.search;
                }

                // 添加排除条件
                params.exclude_ids = 'astrbot';
                params.exclude_platforms = 'webchat';

                console.log(`正在请求对话列表: /api/conversation/list 参数:`, params);

                const response = await axios.get('/api/conversation/list', { params });

                console.log('收到对话列表响应:', response.data);

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

        // 格式化消息内容
        formatMessage(content) {

            // content 可能是数组
            // [{"type": "image_url", "image_url": {"url": url_or_base64}}, {"type": "text", "text": "text"}]

            let final_content = content;
            if (Array.isArray(content)) {
                // 处理数组内容
                final_content = content.map(item => {
                    if (item.type === 'image_url') {
                        return `<img src="${item.image_url.url}" alt="Image" />`;
                    } else if (item.type === 'text') {
                        return item.text;
                    }
                    return '';
                }).join('\n');
            } else if (typeof content === 'object') {
                // 处理对象内容
                final_content = Object.values(content).join('');
            } else if (typeof content === 'string') {
                // 处理字符串内容
                final_content = content;
            } else if (!final_content) return this.tm('status.emptyContent');
            
            // 使用markdown-it处理，默认安全（html: false会禁用HTML标签）
            return md.render(final_content);
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
        }
    }
}
</script>

<style>
.conversation-page {
    padding: 20px;
}

.actions-wrapper {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
}

.action-button {
    border-radius: 8px;
    font-weight: 500;
    transition: all 0.2s ease;
}

.action-button:hover {
    transform: translateY(-2px);
}

.monaco-editor-container {
    height: 500px;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

/* 聊天消息样式 */
.conversation-messages-container {
    max-height: 500px;
    overflow-y: auto;
    padding: 8px;
    border-radius: 8px;
    background-color: #f9f9f9;
}

.message-list {
    display: flex;
    flex-direction: column;
    gap: 16px;
}

.message-item {
    margin-bottom: 8px;
    animation: fadeIn 0.3s ease-out;
}

.user-message {
    display: flex;
    justify-content: flex-end;
    align-items: flex-start;
    gap: 12px;
}

.bot-message {
    display: flex;
    justify-content: flex-start;
    align-items: flex-start;
    gap: 12px;
}

.message-bubble {
    padding: 12px 16px;
    border-radius: 18px;
    max-width: 80%;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.user-bubble {
    background-color: #f0f4ff;
    color: #333;
    border-top-right-radius: 4px;
}

.bot-bubble {
    background-color: #fff;
    border: 1px solid #eaeaea;
    color: #333;
    border-top-left-radius: 4px;
}

.user-avatar,
.bot-avatar {
    margin-top: 2px;
}

/* 附件样式 */
.image-attachments {
    display: flex;
    gap: 8px;
    margin-top: 8px;
    flex-wrap: wrap;
}

.attached-image {
    width: 120px;
    height: 120px;
    object-fit: cover;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    transition: transform 0.2s ease;
}

.attached-image:hover {
    transform: scale(1.05);
}

.audio-attachment {
    margin-top: 8px;
}

.audio-player {
    width: 100%;
    height: 36px;
    border-radius: 18px;
}

/* 对话详情卡片 */
.conversation-detail-card {
    max-height: 90vh;
    display: flex;
    flex-direction: column;
}

/* Markdown内容样式 */
.markdown-content {
    font-family: inherit;
    line-height: 1.6;
}

.markdown-content h1,
.markdown-content h2,
.markdown-content h3,
.markdown-content h4,
.markdown-content h5,
.markdown-content h6 {
    margin-top: 16px;
    margin-bottom: 10px;
    font-weight: 600;
    color: #333;
}

.markdown-content h1 {
    font-size: 1.8em;
    border-bottom: 1px solid #eee;
    padding-bottom: 6px;
}

.markdown-content h2 {
    font-size: 1.5em;
}

.markdown-content h3 {
    font-size: 1.3em;
}

.markdown-content li {
    margin-left: 16px;
    margin-bottom: 4px;
}

.markdown-content p {
    margin-top: 10px;
    margin-bottom: 10px;
}

.markdown-content pre {
    background-color: #f8f8f8;
    padding: 12px;
    border-radius: 6px;
    overflow-x: auto;
    margin: 12px 0;
}

.markdown-content code {
    background-color: #f5f0ff;
    padding: 2px 4px;
    border-radius: 4px;
    font-family: 'Fira Code', monospace;
    font-size: 0.9em;
    color: #673ab7;
}

.markdown-content img {
    max-width: 100%;
    border-radius: 8px;
    margin: 10px 0;
}

.markdown-content blockquote {
    border-left: 4px solid #673ab7;
    padding-left: 16px;
    color: #666;
    margin: 16px 0;
}

.markdown-content table {
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
}

.markdown-content th,
.markdown-content td {
    border: 1px solid #eee;
    padding: 8px 12px;
    text-align: left;
}

.markdown-content th {
    background-color: #f5f0ff;
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