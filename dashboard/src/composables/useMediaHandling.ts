import { ref } from 'vue';
import axios from 'axios';

export interface StagedFileInfo {
    filename: string;
    original_name: string;
    url: string;  // blob URL for preview
}

export function useMediaHandling() {
    const stagedImagesName = ref<string[]>([]);
    const stagedImagesUrl = ref<string[]>([]);
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

            const img = response.data.data.filename;
            stagedImagesName.value.push(img);
            stagedImagesUrl.value.push(URL.createObjectURL(file));
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

            const serverFilename = response.data.data.filename;
            stagedFiles.value.push({
                filename: serverFilename,
                original_name: file.name,
                url: URL.createObjectURL(file)
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
        const urlToRevoke = stagedImagesUrl.value[index];
        if (urlToRevoke && urlToRevoke.startsWith('blob:')) {
            URL.revokeObjectURL(urlToRevoke);
        }

        stagedImagesName.value.splice(index, 1);
        stagedImagesUrl.value.splice(index, 1);
    }

    function removeAudio() {
        stagedAudioUrl.value = '';
    }

    function removeFile(index: number) {
        const fileToRemove = stagedFiles.value[index];
        if (fileToRemove && fileToRemove.url.startsWith('blob:')) {
            URL.revokeObjectURL(fileToRemove.url);
        }
        stagedFiles.value.splice(index, 1);
    }

    function clearStaged() {
        stagedImagesName.value = [];
        stagedImagesUrl.value = [];
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

    return {
        stagedImagesName,
        stagedImagesUrl,
        stagedAudioUrl,
        stagedFiles,
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
