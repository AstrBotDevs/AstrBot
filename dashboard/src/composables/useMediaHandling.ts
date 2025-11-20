import { ref } from 'vue';
import axios from 'axios';

export function useMediaHandling() {
    const stagedImagesName = ref<string[]>([]);
    const stagedImagesUrl = ref<string[]>([]);
    const stagedAudioUrl = ref<string>('');
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
            const response = await axios.post('/api/chat/post_image', formData, {
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

    function clearStaged() {
        stagedImagesName.value = [];
        stagedImagesUrl.value = [];
        stagedAudioUrl.value = '';
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
        getMediaFile,
        processAndUploadImage,
        handlePaste,
        removeImage,
        removeAudio,
        clearStaged,
        cleanupMediaCache
    };
}
