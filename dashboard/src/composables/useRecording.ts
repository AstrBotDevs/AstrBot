import { ref } from 'vue';
import axios from '@/utils/request';

export function useRecording() {
    const isRecording = ref(false);
    const audioChunks = ref<Blob[]>([]);
    const mediaRecorder = ref<MediaRecorder | null>(null);

    function getRecordingMimeType(): string {
        const chunkType = audioChunks.value.find(chunk => chunk.type)?.type;
        return chunkType || mediaRecorder.value?.mimeType || 'audio/webm';
    }

    function getRecordingFilename(mimeType: string): string {
        const extensionMap: Record<string, string> = {
            'audio/webm': 'webm',
            'audio/webm;codecs=opus': 'webm',
            'audio/ogg': 'ogg',
            'audio/ogg;codecs=opus': 'ogg',
            'audio/mp4': 'm4a',
            'audio/mpeg': 'mp3',
            'audio/wav': 'wav'
        };
        const normalizedMimeType = mimeType.toLowerCase();
        const extension = extensionMap[normalizedMimeType] || normalizedMimeType.split('/')[1]?.split(';')[0] || 'webm';
        return `${crypto.randomUUID()}.${extension}`;
    }

    async function startRecording(onStart?: (label: string) => void) {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder.value = new MediaRecorder(stream);
            
            mediaRecorder.value.ondataavailable = (event) => {
                audioChunks.value.push(event.data);
            };
            
            mediaRecorder.value.start();
            isRecording.value = true;
            
            if (onStart) {
                onStart('录音中...');
            }
        } catch (error) {
            console.error('Failed to start recording:', error);
        }
    }

    async function stopRecording(onStop?: (label: string) => void): Promise<string> {
        return new Promise((resolve, reject) => {
            if (!mediaRecorder.value) {
                reject('No media recorder');
                return;
            }

            isRecording.value = false;
            if (onStop) {
                onStop('聊天输入框');
            }

            mediaRecorder.value.stop();
            mediaRecorder.value.onstop = async () => {
                const mimeType = getRecordingMimeType();
                const audioBlob = new Blob(audioChunks.value, { type: mimeType });
                const filename = getRecordingFilename(mimeType);
                audioChunks.value = [];

                mediaRecorder.value?.stream.getTracks().forEach(track => track.stop());

                const formData = new FormData();
                formData.append('file', audioBlob, filename);

                try {
                    const response = await axios.post('/api/chat/post_file', formData, {
                        headers: {
                            'Content-Type': 'multipart/form-data'
                        }
                    });

                    const attachmentId = response.data.data.attachment_id;
                    console.log('Audio uploaded:', attachmentId);
                    resolve(attachmentId);
                } catch (err) {
                    console.error('Error uploading audio:', err);
                    reject(err);
                }
            };
        });
    }

    return {
        isRecording,
        startRecording,
        stopRecording
    };
}
