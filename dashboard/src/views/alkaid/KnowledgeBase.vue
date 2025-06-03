<template>
    <div class="flex-grow-1" style="display: flex; flex-direction: column; height: 100%;">
        <div style="flex-grow: 1; width: 100%; border: 1px solid #eee; border-radius: 8px; padding: 16px">
            <!-- knowledge card -->
            <div v-if="!installed" class="d-flex align-center justify-center flex-column"
                style="flex-grow: 1; width: 100%; height: 100%;">
                <h2>还没有安装知识库插件
                    <v-icon v-class="ml - 2" size="small" color="grey"
                        @click="openUrl('https://astrbot.app/use/knowledge-base.html')">mdi-information-outline</v-icon>
                </h2>
                <v-btn style="margin-top: 16px;" variant="tonal" color="primary" @click="installPlugin"
                    :loading="installing">
                    立即安装
                </v-btn>
                <ConsoleDisplayer v-show="installing" style="background-color: #fff; max-height: 300px; margin-top: 16px; max-width: 100%" :show-level-btns="false"></ConsoleDisplayer>
            </div>
            <div v-else-if="kbCollections.length == 0" class="d-flex align-center justify-center flex-column"
                style="flex-grow: 1; width: 100%; height: 100%;">
                <h2>还没有知识库，快创建一个吧！🙂</h2>
                <v-btn style="margin-top: 16px;" variant="tonal" color="primary" @click="showCreateDialog = true">
                    创建知识库
                </v-btn>
            </div>
            <div v-else>
                <h2 class="mb-4">知识库列表
                    <v-icon v-class="ml - 2" size="x-small" color="grey"
                        @click="openUrl('https://astrbot.app/use/knowledge-base.html')">mdi-information-outline</v-icon>
                </h2>
                <v-btn class="mb-4" prepend-icon="mdi-plus" variant="tonal" color="primary"
                    @click="showCreateDialog = true">
                    创建知识库
                </v-btn>
                <v-btn class="mb-4 ml-4" prepend-icon="mdi-cog" variant="tonal" color="success"
                    @click="$router.push('/extension?open_config=astrbot_plugin_knowledge_base')">
                    配置
                </v-btn>

                <div class="kb-grid">
                    <div v-for="(kb, index) in kbCollections" :key="index" class="kb-card"
                        @click="openKnowledgeBase(kb)">
                        <div class="book-spine"></div>
                        <div class="book-content">
                            <div class="emoji-container">
                                <span class="kb-emoji">{{ kb.emoji || '🙂' }}</span>
                            </div>
                            <div class="kb-name">{{ kb.collection_name }}</div>
                            <div class="kb-count">{{ kb.count || 0 }} 条知识</div>
                            <div class="kb-actions">
                                <v-btn icon variant="text" size="small" color="error" @click.stop="confirmDelete(kb)">
                                    <v-icon>mdi-delete</v-icon>
                                </v-btn>
                            </div>
                        </div>
                    </div>
                </div>
                <div style="padding: 16px; text-align: center;">
                    <small style="color: #a3a3a3">Tips: 在聊天页面通过 /kb 指令了解如何使用！</small>
                </div>

            </div>

        </div>

        <!-- 创建知识库对话框 -->
        <v-dialog v-model="showCreateDialog" max-width="500px">
            <v-card>
                <v-card-title class="text-h4">创建新知识库</v-card-title>
                <v-card-text>

                    <div style="width: 100%; display: flex; align-items: center; justify-content: center;">
                        <span id="emoji-display" @click="showEmojiPicker = true">
                            {{ newKB.emoji || '🙂' }}
                        </span>
                    </div>
                    <v-form @submit.prevent="submitCreateForm">


                        <v-text-field variant="outlined" v-model="newKB.name" label="知识库名称" required></v-text-field>

                        <v-textarea v-model="newKB.description" label="描述" variant="outlined" placeholder="知识库的简短描述..."
                            rows="3"></v-textarea>

                        <v-select v-model="newKB.embedding_provider_id" :items="embeddingProviderConfigs"
                            :item-props="embeddingModelProps" label="Embedding(嵌入)模型" variant="outlined" class="mt-2">
                        </v-select>

                        <small>Tips: 一旦选择了一个知识库的嵌入模型，请不要再修改该提供商的模型或者向量维度信息，否则将严重影响该知识库的召回率甚至报错。</small>
                    </v-form>
                </v-card-text>
                <v-card-actions>
                    <v-spacer></v-spacer>
                    <v-btn color="error" variant="text" @click="showCreateDialog = false">取消</v-btn>
                    <v-btn color="primary" variant="text" @click="submitCreateForm">创建</v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>

        <!-- 表情选择器对话框 -->
        <v-dialog v-model="showEmojiPicker" max-width="400px">
            <v-card>
                <v-card-title class="text-h6">选择表情</v-card-title>
                <v-card-text>
                    <div class="emoji-picker">
                        <div v-for="(category, catIndex) in emojiCategories" :key="catIndex" class="mb-4">
                            <div class="text-subtitle-2 mb-2">{{ category.name }}</div>
                            <div class="emoji-grid">
                                <div v-for="(emoji, emojiIndex) in category.emojis" :key="emojiIndex" class="emoji-item"
                                    @click="selectEmoji(emoji)">
                                    {{ emoji }}
                                </div>
                            </div>
                        </div>
                    </div>
                </v-card-text>
                <v-card-actions>
                    <v-spacer></v-spacer>
                    <v-btn color="primary" variant="text" @click="showEmojiPicker = false">关闭</v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>

        <!-- 知识库内容管理对话框 -->
        <v-dialog v-model="showContentDialog" max-width="1000px">
            <v-card>
                <v-card-title class="d-flex align-center">
                    <div class="me-2 emoji-sm">{{ currentKB.emoji || '🙂' }}</div>
                    <span>{{ currentKB.collection_name }} - 知识库管理</span>
                    <v-spacer></v-spacer>
                    <v-btn variant="plain" icon @click="showContentDialog = false">
                        <v-icon>mdi-close</v-icon>
                    </v-btn>
                </v-card-title>

                <div v-if="currentKB._embedding_provider_config" class="px-6 py-2">
                    <v-chip class="mr-2" color="primary" variant="tonal" size="small" rounded="sm">
                        <v-icon start size="small">mdi-database</v-icon>
                        嵌入模型: {{ currentKB._embedding_provider_config.embedding_model }}
                    </v-chip>
                    <v-chip color="secondary" variant="tonal" size="small" rounded="sm">
                        <v-icon start size="small">mdi-vector-point</v-icon>
                        向量维度: {{ currentKB._embedding_provider_config.embedding_dimensions }}
                    </v-chip>
                    <small style="margin-left: 8px;">💡 使用方式: 在聊天页中输入 “/kb use {{ currentKB.collection_name }}”</small>
                </div>

                <v-card-text>
                    <v-tabs v-model="activeTab">
                        <v-tab value="upload">上传文件</v-tab>
                        <v-tab value="search">搜索内容</v-tab>
                    </v-tabs>

                    <v-window v-model="activeTab" class="mt-4">
                        <!-- 上传文件标签页 -->
                        <v-window-item value="upload">
                            <div class="upload-container pa-4">
                                <div class="text-center mb-4">
                                    <h3>上传文件到知识库</h3>
                                    <p class="text-subtitle-1">支持 txt、pdf、word、excel 等多种格式</p>
                                </div>

                                <div class="upload-zone" @dragover.prevent @drop.prevent="onFileDrop"
                                    @click="triggerFileInput">
                                    <input type="file" ref="fileInput" style="display: none" @change="onFileSelected" />
                                    <v-icon size="48" color="primary">mdi-cloud-upload</v-icon>
                                    <p class="mt-2">拖放文件到这里或点击上传</p>
                                </div>

                                <!-- 优化后的分片长度和重叠长度设置 -->
                                <v-card class="mt-4 chunk-settings-card" variant="outlined" color="grey-lighten-4">
                                    <v-card-title class="pa-4 pb-0 d-flex align-center">
                                        <v-icon color="primary" class="mr-2">mdi-puzzle-outline</v-icon>
                                        <span class="text-subtitle-1 font-weight-bold">分片设置</span>
                                        <v-tooltip location="top">
                                            <template v-slot:activator="{ props }">
                                                <v-icon v-bind="props" class="ml-2" size="small" color="grey">
                                                    mdi-information-outline
                                                </v-icon>
                                            </template>
                                            <span>
                                                分片长度决定每块文本的大小，重叠长度决定相邻文本块之间的重叠程度。<br>
                                                较小的分片更精确但会增加数量，适当的重叠可提高检索准确性。
                                            </span>
                                        </v-tooltip>
                                    </v-card-title>
                                    <v-card-text class="pa-4 pt-2">
                                        <div class="d-flex flex-wrap" style="gap: 8px">
                                            <v-text-field v-model="chunkSize" label="分片长度" type="number"
                                                hint="控制每个文本块大小，留空使用默认值" persistent-hint variant="outlined"
                                                density="comfortable" class="flex-grow-1 chunk-field"
                                                prepend-inner-icon="mdi-text-box-outline" min="50"></v-text-field>

                                            <v-text-field v-model="overlap" label="重叠长度" type="number"
                                                hint="控制相邻文本块重叠度，留空使用默认值" persistent-hint variant="outlined"
                                                density="comfortable" class="flex-grow-1 chunk-field"
                                                prepend-inner-icon="mdi-vector-intersection" min="0"></v-text-field>
                                        </div>
                                    </v-card-text>
                                </v-card>

                                <div class="selected-files mt-4" v-if="selectedFile">
                                    <div type="info" variant="tonal" class="d-flex align-center">
                                        <div>
                                            <v-icon class="me-2">{{ getFileIcon(selectedFile.name) }}</v-icon>
                                            <span style="font-weight: 1000;">{{ selectedFile.name }}</span>
                                        </div>
                                        <v-btn size="small" color="error" variant="text" @click="selectedFile = null">
                                            <v-icon>mdi-close</v-icon>
                                        </v-btn>
                                    </div>

                                    <div class="text-center mt-4">
                                        <v-btn color="primary" variant="elevated" :loading="uploading"
                                            :disabled="!selectedFile" @click="uploadFile">
                                            上传到知识库
                                        </v-btn>
                                    </div>
                                </div>

                                <div class="upload-progress mt-4" v-if="uploading">
                                    <v-progress-linear indeterminate color="primary"></v-progress-linear>
                                </div>
                            </div>
                        </v-window-item>

                        <!-- 搜索内容标签页 -->
                        <v-window-item value="search">
                            <div class="search-container pa-4">
                                <v-form @submit.prevent="searchKnowledgeBase" class="d-flex align-center">
                                    <v-text-field v-model="searchQuery" label="搜索知识库内容" append-icon="mdi-magnify"
                                        variant="outlined" class="flex-grow-1 me-2" @click:append="searchKnowledgeBase"
                                        @keyup.enter="searchKnowledgeBase" placeholder="输入关键词搜索知识库内容..."
                                        hide-details></v-text-field>

                                    <v-select v-model="topK" :items="[3, 5, 10, 20]" label="结果数量" variant="outlined"
                                        style="max-width: 120px;" hide-details></v-select>
                                </v-form>

                                <div class="search-results mt-4">
                                    <div v-if="searching">
                                        <v-progress-linear indeterminate color="primary"></v-progress-linear>
                                        <p class="text-center mt-4">正在搜索...</p>
                                    </div>

                                    <div v-else-if="searchResults.length > 0">
                                        <h3 class="mb-2">搜索结果</h3>
                                        <v-card v-for="(result, index) in searchResults" :key="index"
                                            class="mb-4 search-result-card" variant="outlined">
                                            <v-card-text>
                                                <div class="d-flex align-center mb-2">
                                                    <v-icon class="me-2" size="small"
                                                        color="primary">mdi-file-document-outline</v-icon>
                                                    <span class="text-caption text-medium-emphasis">{{
                                                        result.metadata.source }}</span>
                                                    <v-spacer></v-spacer>
                                                    <v-chip v-if="result.score" size="small" color="primary"
                                                        variant="tonal">
                                                        相关度: {{ Math.round(result.score * 100) }}%
                                                    </v-chip>
                                                </div>
                                                <div class="search-content">{{ result.content }}</div>
                                            </v-card-text>
                                        </v-card>
                                    </div>

                                    <div v-else-if="searchPerformed">
                                        <v-alert type="info" variant="tonal">
                                            没有找到匹配的内容
                                        </v-alert>
                                    </div>
                                </div>
                            </div>
                        </v-window-item>
                    </v-window>
                </v-card-text>
            </v-card>
        </v-dialog>

        <!-- 删除知识库确认对话框 -->
        <v-dialog v-model="showDeleteDialog" max-width="400px">
            <v-card>
                <v-card-title class="text-h5">确认删除</v-card-title>
                <v-card-text>
                    <p>您确定要删除知识库 <span class="font-weight-bold">{{ deleteTarget.collection_name }}</span> 吗？</p>
                    <p class="text-red">此操作不可逆，所有知识库内容将被永久删除。</p>
                </v-card-text>
                <v-card-actions>
                    <v-spacer></v-spacer>
                    <v-btn color="grey-darken-1" variant="text" @click="showDeleteDialog = false">取消</v-btn>
                    <v-btn color="error" variant="text" @click="deleteKnowledgeBase" :loading="deleting">删除</v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>

        <!-- 消息提示 -->
        <v-snackbar v-model="snackbar.show" :color="snackbar.color">
            {{ snackbar.text }}
        </v-snackbar>
    </div>
</template>

<script>
import axios from 'axios';
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';

export default {
    name: 'KnowledgeBase',
    components: {
        ConsoleDisplayer,
    },
    data() {
        return {
            installed: true,
            installing: false,
            kbCollections: [],
            showCreateDialog: false,
            showEmojiPicker: false,
            newKB: {
                name: '',
                emoji: '🙂',
                description: '',
                embedding_provider_id: ''
            },
            snackbar: {
                show: false,
                text: '',
                color: 'success'
            },
            emojiCategories: [
                {
                    name: '笑脸和情感',
                    emojis: ['😀', '😃', '😄', '😁', '😆', '😅', '🤣', '😂', '🙂', '🙃', '😉', '😊', '😇', '🥰', '😍', '🤩', '😘']
                },
                {
                    name: '动物和自然',
                    emojis: ['🐶', '🐱', '🐭', '🐹', '🐰', '🦊', '🐻', '🐼', '🐨', '🐯', '🦁', '🐮', '🐷', '🐸', '🐵']
                },
                {
                    name: '食物和饮料',
                    emojis: ['🍏', '🍎', '🍐', '🍊', '🍋', '🍌', '🍉', '🍇', '🍓', '🍈', '🍒', '🍑', '🥭', '🍍', '🥥']
                },
                {
                    name: '活动和物品',
                    emojis: ['⚽', '🏀', '🏈', '⚾', '🥎', '🎾', '🏐', '🏉', '🎱', '🏓', '🏸', '🥅', '🏒', '🏑', '🥍']
                },
                {
                    name: '旅行和地点',
                    emojis: ['🚗', '🚕', '🚙', '🚌', '🚎', '🏎️', '🚓', '🚑', '🚒', '🚐', '🚚', '🚛', '🚜', '🛴', '🚲']
                },
                {
                    name: '符号和旗帜',
                    emojis: ['❤️', '🧡', '💛', '💚', '💙', '💜', '🖤', '🤍', '🤎', '💔', '❣️', '💕', '💞', '💓', '💗']
                }
            ],
            showContentDialog: false,
            currentKB: {
                collection_name: '',
                emoji: ''
            },
            activeTab: 'upload',
            selectedFile: null,
            chunkSize: null,
            overlap: null,
            uploading: false,
            searchQuery: '',
            searchResults: [],
            searching: false,
            searchPerformed: false,
            topK: 5,
            showDeleteDialog: false,
            deleteTarget: {
                collection_name: ''
            },
            deleting: false,
            embeddingProviderConfigs: []
        }
    },
    mounted() {
        this.checkPlugin();
        this.getEmbeddingProviderList();
    },
    methods: {
        embeddingModelProps(providerConfig) {
            return {
                title: providerConfig.embedding_model,
                subtitle: `提供商 ID: ${providerConfig.id} | 嵌入模型维度: ${providerConfig.embedding_dimensions}`,
            }
        },
        checkPlugin() {
            axios.get('/api/plugin/get?name=astrbot_plugin_knowledge_base')
                .then(response => {
                    if (response.data.status !== 'ok') {
                        this.showSnackbar('插件未安装或不可用', 'error');
                    }
                    if (response.data.data.length > 0) {
                        this.installed = true;
                        this.getKBCollections();
                    } else {
                        this.installed = false;
                    }
                })
                .catch(error => {
                    console.error('Error checking plugin:', error);
                    this.showSnackbar('检查插件失败', 'error');
                })
        },

        installPlugin() {
            this.installing = true;
            axios.post('/api/plugin/install', {
                url: "https://github.com/lxfight/astrbot_plugin_knowledge_base",
                proxy: localStorage.getItem('selectedGitHubProxy') || ""
            })
                .then(response => {
                    if (response.data.status === 'ok') {
                        this.checkPlugin();
                    } else {
                        this.showSnackbar(response.data.message || '安装失败', 'error');
                    }
                })
                .catch(error => {
                    console.error('Error installing plugin:', error);
                    this.showSnackbar('安装插件失败', 'error');
                }).finally(() => {
                    this.installing = false;
                });
        },

        getKBCollections() {
            axios.get('/api/plug/alkaid/kb/collections')
                .then(response => {
                    this.kbCollections = response.data.data;
                })
                .catch(error => {
                    console.error('Error fetching knowledge base collections:', error);
                    this.showSnackbar('获取知识库列表失败', 'error');
                });
        },

        createCollection(name, emoji, description) {
            // 如果 this.newKB.embedding_provider_id 是 Object
            if (typeof this.newKB.embedding_provider_id === 'object') {
                this.newKB.embedding_provider_id = this.newKB.embedding_provider_id.id || '';
            }
            axios.post('/api/plug/alkaid/kb/create_collection', {
                collection_name: name,
                emoji: emoji,
                description: description,
                embedding_provider_id: this.newKB.embedding_provider_id || ''
            })
                .then(response => {
                    if (response.data.status === 'ok') {
                        this.showSnackbar('知识库创建成功');
                        this.getKBCollections();
                        this.showCreateDialog = false;
                        this.resetNewKB();
                    } else {
                        this.showSnackbar(response.data.message || '创建失败', 'error');
                    }
                })
                .catch(error => {
                    console.error('Error creating knowledge base collection:', error);
                    this.showSnackbar('创建知识库失败', 'error');
                });
        },

        submitCreateForm() {
            if (!this.newKB.name) {
                this.showSnackbar('请输入知识库名称', 'warning');
                return;
            }
            this.createCollection(
                this.newKB.name,
                this.newKB.emoji || '🙂',
                this.newKB.description,
                this.newKB.embedding_provider_id || ''
            );
        },

        resetNewKB() {
            this.newKB = {
                name: '',
                emoji: '🙂',
                description: '',
                embedding_provider: ''
            };
        },

        openKnowledgeBase(kb) {
            // 不再跳转路由，而是打开对话框
            this.currentKB = kb;
            this.showContentDialog = true;
            this.resetContentDialog();
        },

        resetContentDialog() {
            this.activeTab = 'upload';
            this.selectedFile = null;
            this.searchQuery = '';
            this.searchResults = [];
            this.searchPerformed = false;
            // 重置分片长度和重叠长度参数
            this.chunkSize = null;
            this.overlap = null;
        },

        triggerFileInput() {
            this.$refs.fileInput.click();
        },

        onFileSelected(event) {
            const files = event.target.files;
            if (files.length > 0) {
                this.selectedFile = files[0];
            }
        },

        onFileDrop(event) {
            const files = event.dataTransfer.files;
            if (files.length > 0) {
                this.selectedFile = files[0];
            }
        },

        getFileIcon(filename) {
            const extension = filename.split('.').pop().toLowerCase();

            switch (extension) {
                case 'pdf':
                    return 'mdi-file-pdf-box';
                case 'doc':
                case 'docx':
                    return 'mdi-file-word-box';
                case 'xls':
                case 'xlsx':
                    return 'mdi-file-excel-box';
                case 'ppt':
                case 'pptx':
                    return 'mdi-file-powerpoint-box';
                case 'txt':
                    return 'mdi-file-document-outline';
                default:
                    return 'mdi-file-outline';
            }
        },

        uploadFile() {
            if (!this.selectedFile) {
                this.showSnackbar('请先选择文件', 'warning');
                return;
            }

            this.uploading = true;

            const formData = new FormData();
            formData.append('file', this.selectedFile);
            formData.append('collection_name', this.currentKB.collection_name);

            // 添加可选的分片长度和重叠长度参数
            if (this.chunkSize && this.chunkSize > 0) {
                formData.append('chunk_size', this.chunkSize);
            }

            if (this.overlap && this.overlap >= 0) {
                formData.append('chunk_overlap', this.overlap);
            }

            axios.post('/api/plug/alkaid/kb/collection/add_file', formData, {
                headers: {
                    'Content-Type': 'multipart/form-data'
                }
            })
                .then(response => {
                    if (response.data.status === 'ok') {
                        this.showSnackbar('操作成功: ' + response.data.message);
                        this.selectedFile = null;

                        // 刷新知识库列表，获取更新的数量
                        this.getKBCollections();
                    } else {
                        this.showSnackbar(response.data.message || '上传失败', 'error');
                    }
                })
                .catch(error => {
                    console.error('Error uploading file:', error);
                    this.showSnackbar('文件上传失败', 'error');
                })
                .finally(() => {
                    this.uploading = false;
                });
        },

        searchKnowledgeBase() {
            if (!this.searchQuery.trim()) {
                this.showSnackbar('请输入搜索内容', 'warning');
                return;
            }

            this.searching = true;
            this.searchPerformed = true;

            axios.get(`/api/plug/alkaid/kb/collection/search`, {
                params: {
                    collection_name: this.currentKB.collection_name,
                    query: this.searchQuery,
                    top_k: this.topK
                }
            })
                .then(response => {
                    if (response.data.status === 'ok') {
                        this.searchResults = response.data.data || [];

                        if (this.searchResults.length === 0) {
                            this.showSnackbar('没有找到匹配的内容', 'info');
                        }
                    } else {
                        this.showSnackbar(response.data.message || '搜索失败', 'error');
                        this.searchResults = [];
                    }
                })
                .catch(error => {
                    console.error('Error searching knowledge base:', error);
                    this.showSnackbar('搜索知识库失败', 'error');
                    this.searchResults = [];
                })
                .finally(() => {
                    this.searching = false;
                });
        },

        showSnackbar(text, color = 'success') {
            this.snackbar.text = text;
            this.snackbar.color = color;
            this.snackbar.show = true;
        },

        selectEmoji(emoji) {
            this.newKB.emoji = emoji;
            this.showEmojiPicker = false;
        },

        confirmDelete(kb) {
            this.deleteTarget = kb;
            this.showDeleteDialog = true;
        },

        deleteKnowledgeBase() {
            if (!this.deleteTarget.collection_name) {
                this.showSnackbar('删除目标不存在', 'error');
                return;
            }

            this.deleting = true;

            axios.get('/api/plug/alkaid/kb/collection/delete', {
                params: {
                    collection_name: this.deleteTarget.collection_name
                }
            })
                .then(response => {
                    if (response.data.status === 'ok') {
                        this.showSnackbar('知识库删除成功');
                        this.getKBCollections(); // 刷新列表
                        this.showDeleteDialog = false;
                    } else {
                        this.showSnackbar(response.data.message || '删除失败', 'error');
                    }
                })
                .catch(error => {
                    console.error('Error deleting knowledge base:', error);
                    this.showSnackbar('删除知识库失败', 'error');
                })
                .finally(() => {
                    this.deleting = false;
                });
        },

        getEmbeddingProviderList() {
            axios.get('/api/config/provider/list', {
                params: {
                    provider_type: 'embedding'
                }
            })
                .then(response => {
                    if (response.data.status === 'ok') {
                        this.embeddingProviderConfigs = response.data.data || [];
                    } else {
                        this.showSnackbar(response.data.message || '获取嵌入模型列表失败', 'error');
                        return [];
                    }
                })
                .catch(error => {
                    console.error('Error fetching embedding providers:', error);
                    this.showSnackbar('获取嵌入模型列表失败', 'error');
                    return [];
                });
        },

        openUrl(url) {
            window.open(url, '_blank');
        }
    }
}
</script>

<style scoped>
.kb-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 24px;
    margin-top: 16px;
}

.kb-card {
    height: 280px;
    border-radius: 8px;
    overflow: hidden;
    position: relative;
    cursor: pointer;
    display: flex;
    background-color: var(--v-theme-background);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    transition: all 0.3s ease;
}

.kb-card:hover {
    transform: translateY(-5px);
    box-shadow: 0 8px 16px rgba(0, 0, 0, 0.15);
}

.book-spine {
    width: 12px;
    background-color: #5c6bc0;
    height: 100%;
    border-radius: 2px 0 0 2px;
}

.book-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 20px;
    background: linear-gradient(145deg, #f5f7fa 0%, #e4e8f0 100%);
}

.emoji-container {
    width: 80px;
    height: 80px;
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: var(--v-theme-background);
    border-radius: 50%;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    margin-bottom: 16px;
}

.kb-emoji {
    font-size: 40px;
}

.kb-name {
    font-weight: bold;
    font-size: 18px;
    margin-bottom: 8px;
    text-align: center;
    color: #333;
}

.kb-count {
    font-size: 14px;
    color: #666;
}

.emoji-picker {
    max-height: 300px;
    overflow-y: auto;
}

.emoji-grid {
    display: grid;
    grid-template-columns: repeat(8, 1fr);
    gap: 8px;
}

.emoji-item {
    font-size: 24px;
    padding: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    border-radius: 4px;
    transition: background-color 0.2s ease;
}

.emoji-item:hover {
    background-color: rgba(0, 0, 0, 0.05);
}

#emoji-display {
    font-size: 64px;
    cursor: pointer;
    transition: transform 0.2s ease;
}

#emoji-display:hover {
    transform: scale(1.1);
}

.emoji-sm {
    font-size: 24px;
}

.upload-zone {
    border: 2px dashed #ccc;
    border-radius: 8px;
    padding: 32px;
    text-align: center;
    cursor: pointer;
    transition: all 0.3s ease;
}

.upload-zone:hover {
    border-color: #5c6bc0;
    background-color: rgba(92, 107, 192, 0.05);
}

.search-container {
    min-height: 300px;
}

.search-result-card {
    transition: all 0.2s ease;
}

.search-result-card:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.search-content {
    white-space: pre-line;
    max-height: 200px;
    overflow-y: auto;
    font-size: 0.95rem;
    line-height: 1.6;
    padding: 8px;
    background-color: rgba(0, 0, 0, 0.02);
    border-radius: 4px;
}

.kb-actions {
    position: absolute;
    bottom: 10px;
    right: 10px;
    display: flex;
    gap: 8px;
    opacity: 0;
    transition: opacity 0.2s ease;
}

.kb-card {
    position: relative;
}

.kb-card:hover .kb-actions {
    opacity: 1;
}

.chunk-settings-card {
    border: 1px solid rgba(92, 107, 192, 0.2) !important;
    transition: all 0.3s ease;
}

.chunk-settings-card:hover {
    border-color: rgba(92, 107, 192, 0.4) !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.07) !important;
}

.chunk-field :deep(.v-field__input) {
    padding-top: 8px;
    padding-bottom: 8px;
}

.chunk-field :deep(.v-field__prepend-inner) {
    padding-right: 8px;
    opacity: 0.7;
}

.chunk-field:focus-within :deep(.v-field__prepend-inner) {
    opacity: 1;
}
</style>
