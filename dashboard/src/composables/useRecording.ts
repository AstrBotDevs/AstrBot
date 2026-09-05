import { ref } from 'vue';

export function useRecording() {
    const isRecording = ref(false);
    const audioChunks = ref<Blob[]>([]);
    const mediaRecorder = ref<MediaRecorder | null>(null);

    function getSupportedMimeType(): string {
        const candidates = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/ogg;codecs=opus',
            'audio/ogg',
            'audio/mp4',
            'audio/wav'
        ];

        if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported) {
            return '';
        }

        return candidates.find(type => MediaRecorder.isTypeSupported(type)) || '';
    }

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
        const id = crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
        return `${id}.${extension}`;
    }

    async function startRecording(onStart?: (label: string) => void) {
        try {
            if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
                throw new Error('Audio recording is not supported in this browser');
            }

            mediaRecorder.value?.stream.getTracks().forEach(track => track.stop());
            audioChunks.value = [];

            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mimeType = getSupportedMimeType();
            mediaRecorder.value = new MediaRecorder(
                stream,
                mimeType ? { mimeType } : undefined
            );
            
            mediaRecorder.value.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunks.value.push(event.data);
                }
            };
            
            mediaRecorder.value.start();
            isRecording.value = true;
            
            if (onStart) {
                onStart('录音中...');
            }
        } catch (error) {
            console.error('Failed to start recording:', error);
            isRecording.value = false;
            throw error;
        }
    }

    async function stopRecording(onStop?: (label: string) => void): Promise<File> {
        return new Promise((resolve, reject) => {
            const recorder = mediaRecorder.value;
            if (!recorder) {
                reject(new Error('No media recorder'));
                return;
            }

            isRecording.value = false;
            if (onStop) {
                onStop('聊天输入框');
            }

            recorder.onstop = () => {
                const mimeType = getRecordingMimeType();
                const audioBlob = new Blob(audioChunks.value, { type: mimeType });
                audioChunks.value = [];
                recorder.stream.getTracks().forEach(track => track.stop());
                if (mediaRecorder.value === recorder) {
                    mediaRecorder.value = null;
                }

                if (!audioBlob.size) {
                    reject(new Error('Recording is empty'));
                    return;
                }

                const filename = getRecordingFilename(mimeType);
                const audioFile = new File([audioBlob], filename, {
                    type: mimeType,
                    lastModified: Date.now()
                });
                resolve(audioFile);
            };

            recorder.onerror = (event) => {
                recorder.stream.getTracks().forEach(track => track.stop());
                if (mediaRecorder.value === recorder) {
                    mediaRecorder.value = null;
                }
                reject(event);
            };

            try {
                recorder.stop();
            } catch (error) {
                recorder.stream.getTracks().forEach(track => track.stop());
                if (mediaRecorder.value === recorder) {
                    mediaRecorder.value = null;
                }
                reject(error);
            }
        });
    }

    return {
        isRecording,
        startRecording,
        stopRecording
    };
}
