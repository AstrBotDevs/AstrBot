import { ref, computed } from 'vue';
import axios from 'axios';

export interface StagedFileInfo {
    attachment_id: string;
    filename: string;
    original_name: string;
    url: string;  // blob URL for preview
    type: string;  // image, record, file, video
}

export function useMediaHandling() {
    const stagedAudioUrl = ref<string>('');
    const stagedFiles = ref<StagedFileInfo[]>([]);
    const mediaCache = ref<Record<string, string>>({});

    async function getMediaFile(filename: string): Promise<string> {
        if (mediaCache.value[filename]) {
            return mediaCache.value[filename];
        }

        try {
            const response = await axios.get('/api/chat/get_file', {
                params: { filename },
                responseType: 'blob'
            });

            const blobUrl = URL.createObjectURL(response.data);
            mediaCache.value[filename] = blobUrl;
            return blobUrl;
        } catch (error) {
            console.error('Error fetching media file:', error);
            return '';
        }
    }

    async function processAndUploadImage(file: File) {
        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await axios.post('/api/chat/post_file', formData, {
                headers: {
                    'Content-Type': 'multipart/form-data'
                }
            });

            const { attachment_id, filename, type } = response.data.data;
            stagedFiles.value.push({
                attachment_id,
                filename,
                original_name: file.name,
                url: URL.createObjectURL(file),
                type
            });
        } catch (err) {
            console.error('Error uploading image:', err);
        }
    }

    async function processAndUploadFile(file: File) {
        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await axios.post('/api/chat/post_file', formData, {
                headers: {
                    'Content-Type': 'multipart/form-data'
                }
            });

            const { attachment_id, filename, type } = response.data.data;
            stagedFiles.value.push({
                attachment_id,
                filename,
                original_name: file.name,
                url: URL.createObjectURL(file),
                type
            });
        } catch (err) {
            console.error('Error uploading file:', err);
        }
    }

    async function handlePaste(event: ClipboardEvent) {
        const items = event.clipboardData?.items;
        if (!items) return;

        for (let i = 0; i < items.length; i++) {
            if (items[i].type.indexOf('image') !== -1) {
                const file = items[i].getAsFile();
                if (file) {
                    await processAndUploadImage(file);
                }
            }
        }
    }

    function removeImage(index: number) {
        // 找到第 index 个图片类型的文件
        let imageCount = 0;
        for (let i = 0; i < stagedFiles.value.length; i++) {
            if (stagedFiles.value[i].type === 'image') {
                if (imageCount === index) {
                    const fileToRemove = stagedFiles.value[i];
                    if (fileToRemove.url.startsWith('blob:')) {
                        URL.revokeObjectURL(fileToRemove.url);
                    }
                    stagedFiles.value.splice(i, 1);
                    return;
                }
                imageCount++;
            }
        }
    }

    function removeAudio() {
        stagedAudioUrl.value = '';
    }

    function removeFile(index: number) {
        // 找到第 index 个非图片类型的文件
        let fileCount = 0;
        for (let i = 0; i < stagedFiles.value.length; i++) {
            if (stagedFiles.value[i].type !== 'image') {
                if (fileCount === index) {
                    const fileToRemove = stagedFiles.value[i];
                    if (fileToRemove.url.startsWith('blob:')) {
                        URL.revokeObjectURL(fileToRemove.url);
                    }
                    stagedFiles.value.splice(i, 1);
                    return;
                }
                fileCount++;
            }
        }
    }

    function clearStaged() {
        stagedAudioUrl.value = '';
        // 清理文件的 blob URLs
        stagedFiles.value.forEach(file => {
            if (file.url.startsWith('blob:')) {
                URL.revokeObjectURL(file.url);
            }
        });
        stagedFiles.value = [];
    }

    function cleanupMediaCache() {
        Object.values(mediaCache.value).forEach(url => {
            if (url.startsWith('blob:')) {
                URL.revokeObjectURL(url);
            }
        });
        mediaCache.value = {};
    }

    // 计算属性：获取图片的 URL 列表（用于预览）
    const stagedImagesUrl = computed(() => 
        stagedFiles.value.filter(f => f.type === 'image').map(f => f.url)
    );

    // 计算属性：获取非图片文件列表
    const stagedNonImageFiles = computed(() => 
        stagedFiles.value.filter(f => f.type !== 'image')
    );

    return {
        stagedImagesUrl,
        stagedAudioUrl,
        stagedFiles,
        stagedNonImageFiles,
        getMediaFile,
        processAndUploadImage,
        processAndUploadFile,
        handlePaste,
        removeImage,
        removeAudio,
        removeFile,
        clearStaged,
        cleanupMediaCache
    };
}
