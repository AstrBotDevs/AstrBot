<template>
  <div class="document-list-panel">
    <!-- 文档统计 -->
    <v-row class="mb-4">
      <v-col cols="12" sm="6" md="3">
        <v-card variant="outlined">
          <v-card-text class="text-center">
            <div class="text-h5 primary--text">{{ documentStats.total }}</div>
            <div class="text-caption">{{ tm('stats.totalDocuments') }}</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-card variant="outlined">
          <v-card-text class="text-center">
            <div class="text-h5 success--text">{{ documentStats.chunks }}</div>
            <div class="text-caption">{{ tm('stats.totalChunks') }}</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-card variant="outlined">
          <v-card-text class="text-center">
            <div class="text-h5 warning--text">{{ documentStats.media }}</div>
            <div class="text-caption">{{ tm('stats.totalMedia') }}</div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" sm="6" md="3">
        <v-card variant="outlined">
          <v-card-text class="text-center">
            <div class="text-h5 info--text">{{ formatFileSize(documentStats.size) }}</div>
            <div class="text-caption">{{ tm('stats.totalSize') }}</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- 操作栏 -->
    <div class="d-flex justify-space-between align-center mb-4">
      <v-btn prepend-icon="mdi-upload" variant="tonal" color="primary" @click="showUploadDialog = true">
        {{ tm('actions.upload') }}
      </v-btn>
      <v-btn prepend-icon="mdi-refresh" variant="text" @click="loadDocuments" :loading="loading">
        {{ tm('actions.refresh') }}
      </v-btn>
    </div>

    <!-- 文档列表 -->
    <v-data-table
      :headers="headers"
      :items="documents"
      :loading="loading"
      items-per-page="10"
      class="elevation-1"
    >
      <template v-slot:item.doc_name="{ item }">
        <div class="d-flex align-center">
          <v-icon :icon="getFileIcon(item.file_type)" class="mr-2"></v-icon>
          <span>{{ item.doc_name }}</span>
        </div>
      </template>

      <template v-slot:item.file_size="{ item }">
        {{ formatFileSize(item.file_size) }}
      </template>

      <template v-slot:item.created_at="{ item }">
        {{ formatDate(item.created_at) }}
      </template>

      <template v-slot:item.actions="{ item }">
        <v-btn variant="text" size="small" prepend-icon="mdi-eye" @click="viewDocument(item)">
          {{ tm('actions.view') }}
        </v-btn>
        <v-btn variant="text" size="small" color="error" prepend-icon="mdi-delete" @click="confirmDelete(item)">
          {{ tm('actions.delete') }}
        </v-btn>
      </template>

      <template v-slot:no-data>
        <div class="text-center py-8">
          <v-icon size="64" color="grey-lighten-2">mdi-file-document-outline</v-icon>
          <p class="text-medium-emphasis mt-4">{{ tm('empty.noDocuments') }}</p>
        </div>
      </template>
    </v-data-table>

    <!-- 文档上传对话框 -->
    <v-dialog v-model="showUploadDialog" max-width="600px">
      <v-card>
        <v-card-title>{{ tm('upload.title') }}</v-card-title>
        <v-card-text>
          <div class="upload-zone" @click="triggerFileInput" @dragover.prevent @drop.prevent="onFileDrop">
            <input type="file" ref="fileInput" style="display: none" @change="onFileSelected" multiple />
            <v-icon size="64" color="primary">mdi-cloud-upload</v-icon>
            <p class="mt-4">{{ tm('upload.dropzone') }}</p>
            <p class="text-caption text-medium-emphasis">{{ tm('upload.supportedFormats') }}</p>
          </div>

          <div v-if="selectedFiles.length > 0" class="mt-4">
            <h4>{{ tm('upload.selectedFiles') }}</h4>
            <v-list density="compact">
              <v-list-item v-for="(file, index) in selectedFiles" :key="index">
                <template v-slot:prepend>
                  <v-icon :icon="getFileIcon(getFileExtension(file.name))"></v-icon>
                </template>
                <v-list-item-title>{{ file.name }}</v-list-item-title>
                <v-list-item-subtitle>{{ formatFileSize(file.size) }}</v-list-item-subtitle>
                <template v-slot:append>
                  <v-btn icon variant="text" size="small" @click="removeFile(index)">
                    <v-icon>mdi-close</v-icon>
                  </v-btn>
                </template>
              </v-list-item>
            </v-list>
          </div>

          <div v-if="uploading" class="mt-4">
            <v-progress-linear indeterminate color="primary"></v-progress-linear>
            <p class="text-center mt-2">{{ tm('upload.uploading') }}</p>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn @click="showUploadDialog = false">{{ tm('upload.cancel') }}</v-btn>
          <v-btn color="primary" @click="uploadFiles" :loading="uploading" :disabled="selectedFiles.length === 0">
            {{ tm('upload.upload') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 文档详情对话框 -->
    <v-dialog v-model="showDetailDialog" max-width="800px" scrollable>
      <v-card v-if="currentDocument">
        <v-card-title class="d-flex align-center">
          <v-icon :icon="getFileIcon(currentDocument.file_type)" class="mr-2"></v-icon>
          <span>{{ currentDocument.doc_name }}</span>
          <v-spacer></v-spacer>
          <v-btn variant="plain" icon @click="showDetailDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>

        <v-tabs v-model="detailTab">
          <v-tab value="info">{{ tm('detail.tabs.info') || '基本信息' }}</v-tab>
          <v-tab value="chunks">{{ tm('detail.tabs.chunks') || '文档块' }} ({{ currentDocument.chunk_count || 0 }})</v-tab>
          <v-tab value="media">{{ tm('detail.tabs.media') || '多媒体' }} ({{ currentDocument.media_count || 0 }})</v-tab>
        </v-tabs>

        <v-card-text>
          <v-window v-model="detailTab">
            <!-- 基本信息 Tab -->
            <v-window-item value="info">
              <v-row class="mb-4">
                <v-col cols="6">
                  <div class="text-caption text-medium-emphasis">{{ tm('detail.fileType') }}</div>
                  <div>{{ currentDocument.file_type.toUpperCase() }}</div>
                </v-col>
                <v-col cols="6">
                  <div class="text-caption text-medium-emphasis">{{ tm('detail.fileSize') }}</div>
                  <div>{{ formatFileSize(currentDocument.file_size) }}</div>
                </v-col>
                <v-col cols="6">
                  <div class="text-caption text-medium-emphasis">{{ tm('detail.chunks') }}</div>
                  <div>{{ currentDocument.chunk_count }}</div>
                </v-col>
                <v-col cols="6">
                  <div class="text-caption text-medium-emphasis">{{ tm('detail.uploadedAt') }}</div>
                  <div>{{ formatDate(currentDocument.created_at) }}</div>
                </v-col>
              </v-row>
            </v-window-item>

            <!-- 文档块 Tab -->
            <v-window-item value="chunks">
              <div v-if="loadingChunks" class="text-center py-4">
                <v-progress-circular indeterminate color="primary"></v-progress-circular>
              </div>
              <div v-else-if="chunks.length === 0" class="text-center py-4 text-medium-emphasis">
                {{ tm('detail.noChunks') }}
              </div>
              <div v-else>
                <v-card
                  v-for="(chunk, index) in chunks"
                  :key="index"
                  variant="outlined"
                  class="mb-2 chunk-card"
                >
                  <v-card-text>
                    <div class="d-flex justify-space-between align-center mb-2">
                      <span class="text-caption">{{ tm('detail.chunkIndex', { index: chunk.chunk_index }) }}</span>
                      <div class="d-flex align-center">
                        <span class="text-caption mr-2">{{ chunk.char_count }} {{ tm('detail.characters') }}</span>
                        <v-btn
                          icon
                          variant="text"
                          size="small"
                          color="error"
                          @click.stop="confirmDeleteChunk(chunk)"
                        >
                          <v-icon size="small">mdi-delete</v-icon>
                        </v-btn>
                      </div>
                    </div>
                    <div class="chunk-content">{{ truncateText(chunk.content, 200) }}</div>
                  </v-card-text>
                </v-card>
              </div>
            </v-window-item>

            <!-- 多媒体 Tab -->
            <v-window-item value="media">
              <div v-if="loadingMedia" class="text-center py-4">
                <v-progress-circular indeterminate color="primary"></v-progress-circular>
              </div>
              <div v-else-if="mediaList.length === 0" class="text-center py-4 text-medium-emphasis">
                {{ tm('detail.noMedia') || '暂无多媒体资源' }}
              </div>
              <v-list v-else density="compact">
                <v-list-item v-for="media in mediaList" :key="media.media_id">
                  <template v-slot:prepend>
                    <v-icon :icon="getMediaIcon(media.media_type)"></v-icon>
                  </template>
                  <v-list-item-title>{{ media.file_name }}</v-list-item-title>
                  <v-list-item-subtitle>
                    {{ media.mime_type }} | {{ formatFileSize(media.file_size) }}
                  </v-list-item-subtitle>
                  <template v-slot:append>
                    <v-btn icon size="small" variant="text" color="error" @click="confirmDeleteMedia(media)">
                      <v-icon>mdi-delete</v-icon>
                    </v-btn>
                  </template>
                </v-list-item>
              </v-list>
            </v-window-item>
          </v-window>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- 删除确认对话框 -->
    <v-dialog v-model="showDeleteDialog" max-width="400px">
      <v-card>
        <v-card-title>{{ tm('delete.title') }}</v-card-title>
        <v-card-text>
          <p>{{ tm('delete.confirmText', { name: deleteTarget.doc_name }) }}</p>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn @click="showDeleteDialog = false">{{ tm('delete.cancel') }}</v-btn>
          <v-btn color="error" @click="deleteDocument" :loading="deleting">{{ tm('delete.delete') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 删除块确认对话框 -->
    <v-dialog v-model="showDeleteChunkDialog" max-width="400px">
      <v-card>
        <v-card-title>{{ tm('delete.chunkTitle') || '删除文档块' }}</v-card-title>
        <v-card-text>
          <p>{{ tm('delete.chunkConfirmText', { index: deleteChunkTarget.chunk_index }) || `确定要删除块 #${deleteChunkTarget.chunk_index} 吗？` }}</p>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn @click="showDeleteChunkDialog = false">{{ tm('delete.cancel') }}</v-btn>
          <v-btn color="error" @click="deleteChunk" :loading="deletingChunk">{{ tm('delete.delete') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 删除多媒体确认对话框 -->
    <v-dialog v-model="showDeleteMediaDialog" max-width="400px">
      <v-card>
        <v-card-title>{{ tm('delete.mediaTitle') || '删除多媒体资源' }}</v-card-title>
        <v-card-text>
          <p>{{ tm('delete.mediaConfirmText', { name: deleteMediaTarget.file_name }) || `确定要删除 "${deleteMediaTarget.file_name}" 吗？` }}</p>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn @click="showDeleteMediaDialog = false">{{ tm('delete.cancel') }}</v-btn>
          <v-btn color="error" @click="deleteMedia" :loading="deletingMedia">{{ tm('delete.delete') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 消息提示 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script>
import axios from 'axios';
import { useModuleI18n } from '@/i18n/composables';

export default {
  name: 'DocumentListPanel',
  props: {
    kb: {
      type: Object,
      required: true,
    },
  },
  setup() {
    const { tm } = useModuleI18n('features/alkaid/knowledge-base-v2/documents');
    return { tm };
  },
  data() {
    return {
      documents: [],
      chunks: [],
      mediaList: [],
      loading: false,
      loadingChunks: false,
      loadingMedia: false,
      uploading: false,
      deleting: false,
      deletingChunk: false,
      deletingMedia: false,
      showUploadDialog: false,
      showDetailDialog: false,
      showDeleteDialog: false,
      showDeleteChunkDialog: false,
      showDeleteMediaDialog: false,
      selectedFiles: [],
      currentDocument: null,
      deleteTarget: {},
      deleteChunkTarget: {},
      deleteMediaTarget: {},
      detailTab: 'info',
      documentStats: {
        total: 0,
        chunks: 0,
        media: 0,
        size: 0,
      },
      headers: [
        { title: '文件名', key: 'doc_name', width: '35%' },
        { title: '类型', key: 'file_type', width: '10%' },
        { title: '大小', key: 'file_size', width: '15%' },
        { title: '块数量', key: 'chunk_count', width: '10%' },
        { title: '上传时间', key: 'created_at', width: '15%' },
        { title: '操作', key: 'actions', width: '15%', sortable: false },
      ],
      snackbar: {
        show: false,
        text: '',
        color: 'success',
      },
    };
  },
  mounted() {
    this.loadDocuments();
  },
  methods: {
    async loadDocuments() {
      this.loading = true;
      try {
        const response = await axios.get('/api/kb/document/list', {
          params: { kb_id: this.kb.kb_id },
        });
        if (response.data.status === 'ok') {
          this.documents = response.data.data.items || [];
          this.updateStats();
        }
      } catch (error) {
        console.error('Error loading documents:', error);
        this.showSnackbar(this.tm('messages.loadError'), 'error');
      } finally {
        this.loading = false;
      }
    },
    updateStats() {
      this.documentStats = {
        total: this.documents.length,
        chunks: this.documents.reduce((sum, doc) => sum + (doc.chunk_count || 0), 0),
        media: this.documents.reduce((sum, doc) => sum + (doc.media_count || 0), 0),
        size: this.documents.reduce((sum, doc) => sum + (doc.file_size || 0), 0),
      };
    },
    getFileIcon(fileType) {
      const iconMap = {
        pdf: 'mdi-file-pdf-box',
        docx: 'mdi-file-word-box',
        doc: 'mdi-file-word-box',
        txt: 'mdi-file-document-outline',
        md: 'mdi-language-markdown',
        markdown: 'mdi-language-markdown',
      };
      return iconMap[fileType?.toLowerCase()] || 'mdi-file-outline';
    },
    getFileExtension(filename) {
      return filename.split('.').pop().toLowerCase();
    },
    formatFileSize(bytes) {
      if (!bytes || bytes === 0) return '0 B';
      const k = 1024;
      const sizes = ['B', 'KB', 'MB', 'GB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },
    formatDate(dateString) {
      if (!dateString) return '';
      return new Date(dateString).toLocaleString();
    },
    truncateText(text, maxLength) {
      if (!text || text.length <= maxLength) return text;
      return text.substring(0, maxLength) + '...';
    },
    triggerFileInput() {
      this.$refs.fileInput.click();
    },
    onFileSelected(event) {
      const files = Array.from(event.target.files);
      this.selectedFiles = [...this.selectedFiles, ...files];
    },
    onFileDrop(event) {
      const files = Array.from(event.dataTransfer.files);
      this.selectedFiles = [...this.selectedFiles, ...files];
    },
    removeFile(index) {
      this.selectedFiles.splice(index, 1);
    },
    async uploadFiles() {
      if (this.selectedFiles.length === 0) return;

      this.uploading = true;
      let successCount = 0;
      let failCount = 0;

      for (const file of this.selectedFiles) {
        try {
          const formData = new FormData();
          formData.append('file', file);
          formData.append('kb_id', this.kb.kb_id);

          const response = await axios.post('/api/kb/document/upload', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
          });

          if (response.data.status === 'ok') {
            successCount++;
          } else {
            failCount++;
          }
        } catch (error) {
          console.error('Error uploading file:', error);
          failCount++;
        }
      }

      this.uploading = false;
      this.selectedFiles = [];
      this.showUploadDialog = false;

      if (failCount === 0) {
        this.showSnackbar(this.tm('messages.uploadSuccess', { count: successCount }));
      } else {
        this.showSnackbar(
          this.tm('messages.uploadPartial', { success: successCount, fail: failCount }),
          'warning'
        );
      }

      this.loadDocuments();
    },
    async viewDocument(document) {
      this.currentDocument = document;
      this.showDetailDialog = true;
      this.detailTab = 'info'; // 重置为基本信息 Tab
      this.loadChunks(document.doc_id);
      this.loadMedia(document.doc_id);
    },
    async loadChunks(docId) {
      this.loadingChunks = true;
      try {
        const response = await axios.get('/api/kb/chunk/list', {
          params: { doc_id: docId },
        });
        if (response.data.status === 'ok') {
          this.chunks = response.data.data.items || [];
        }
      } catch (error) {
        console.error('Error loading chunks:', error);
      } finally {
        this.loadingChunks = false;
      }
    },
    async loadMedia(docId) {
      this.loadingMedia = true;
      try {
        const response = await axios.get('/api/kb/media/list', {
          params: { doc_id: docId },
        });
        if (response.data.status === 'ok') {
          this.mediaList = response.data.data.items || [];
        }
      } catch (error) {
        console.error('Error loading media:', error);
      } finally {
        this.loadingMedia = false;
      }
    },
    confirmDelete(document) {
      this.deleteTarget = document;
      this.showDeleteDialog = true;
    },
    async deleteDocument() {
      this.deleting = true;
      try {
        const response = await axios.post('/api/kb/document/delete', {
          doc_id: this.deleteTarget.doc_id,
        });

        if (response.data.status === 'ok') {
          this.showSnackbar(this.tm('messages.deleteSuccess'));
          this.showDeleteDialog = false;
          this.loadDocuments();
        } else {
          this.showSnackbar(response.data.message || this.tm('messages.deleteFailed'), 'error');
        }
      } catch (error) {
        console.error('Error deleting document:', error);
        this.showSnackbar(this.tm('messages.deleteError'), 'error');
      } finally {
        this.deleting = false;
      }
    },
    confirmDeleteChunk(chunk) {
      this.deleteChunkTarget = chunk;
      this.showDeleteChunkDialog = true;
    },
    async deleteChunk() {
      this.deletingChunk = true;
      try {
        const response = await axios.post('/api/kb/chunk/delete', {
          chunk_id: this.deleteChunkTarget.chunk_id,
        });

        if (response.data.status === 'ok') {
          this.showSnackbar(this.tm('messages.chunkDeleteSuccess') || '块删除成功');
          this.showDeleteChunkDialog = false;
          // 重新加载块列表
          if (this.currentDocument) {
            await this.loadChunks(this.currentDocument.doc_id);
            // 更新文档列表以反映新的块数量
            await this.loadDocuments();
          }
        } else {
          this.showSnackbar(response.data.message || this.tm('messages.chunkDeleteFailed') || '块删除失败', 'error');
        }
      } catch (error) {
        console.error('Error deleting chunk:', error);
        this.showSnackbar(this.tm('messages.chunkDeleteError') || '块删除出错', 'error');
      } finally {
        this.deletingChunk = false;
      }
    },
    confirmDeleteMedia(media) {
      this.deleteMediaTarget = media;
      this.showDeleteMediaDialog = true;
    },
    async deleteMedia() {
      this.deletingMedia = true;
      try {
        const response = await axios.post('/api/kb/media/delete', {
          media_id: this.deleteMediaTarget.media_id,
        });

        if (response.data.status === 'ok') {
          this.showSnackbar(this.tm('messages.mediaDeleteSuccess') || '多媒体删除成功');
          this.showDeleteMediaDialog = false;
          // 重新加载多媒体列表
          if (this.currentDocument) {
            await this.loadMedia(this.currentDocument.doc_id);
            // 更新文档列表以反映新的多媒体数量
            await this.loadDocuments();
          }
        } else {
          this.showSnackbar(response.data.message || this.tm('messages.mediaDeleteFailed') || '多媒体删除失败', 'error');
        }
      } catch (error) {
        console.error('Error deleting media:', error);
        this.showSnackbar(this.tm('messages.mediaDeleteError') || '多媒体删除出错', 'error');
      } finally {
        this.deletingMedia = false;
      }
    },
    getMediaIcon(mediaType) {
      const iconMap = {
        image: 'mdi-image',
        video: 'mdi-video',
        audio: 'mdi-music',
      };
      return iconMap[mediaType] || 'mdi-file';
    },
    showSnackbar(text, color = 'success') {
      this.snackbar.text = text;
      this.snackbar.color = color;
      this.snackbar.show = true;
    },
  },
};
</script>

<style scoped>
.upload-zone {
  border: 2px dashed #ccc;
  border-radius: 8px;
  padding: 48px 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
}

.upload-zone:hover {
  border-color: #5c6bc0;
  background-color: rgba(92, 107, 192, 0.05);
}

.chunk-card {
  transition: all 0.2s ease;
}

.chunk-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1) !important;
}

.chunk-content {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.9rem;
  line-height: 1.5;
  color: #666;
}
</style>
