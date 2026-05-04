import { ref, onBeforeUnmount } from 'vue';
import axios from 'axios';

interface VADOptions {
    onSpeechStart?: () => void;
    onSpeechRealStart?: () => void;
    onSpeechEnd: (audio: Float32Array) => void;
    onVADMisfire?: () => void;
    onFrameProcessed?: (probabilities: { isSpeech: number; notSpeech: number }, frame: Float32Array) => void;
    positiveSpeechThreshold?: number;
    negativeSpeechThreshold?: number;
    redemptionMs?: number;
    preSpeechPadMs?: number;
    minSpeechMs?: number;
    submitUserSpeechOnPause?: boolean;
    model?: 'v5' | 'legacy';
    baseAssetPath?: string;
    onnxWASMBasePath?: string;
}

interface VADInstance {
    start(): void;
    pause(): void;
    listening: boolean;
}

// 声明全局 vad 对象类型
declare global {
    interface Window {
        vad: {
            MicVAD: {
                new(options: VADOptions): Promise<VADInstance>;
            };
        };
    }
}

/**
 * 使用 VAD (Voice Activity Detection) 进行录音的 composable
 * VAD 会自动检测用户何时开始和停止说话，无需手动控制
 */
export function useVADRecording() {
    const isRecording = ref(false);
    const isSpeaking = ref(false);
    const audioEnergy = ref(0); // 0-1 之间的能量值
    const vadInstance = ref<VADInstance | null>(null);
    const isInitialized = ref(false);
    const onSpeechStartCallback = ref<(() => void) | null>(null);
    const onSpeechEndCallback = ref<((audio: Float32Array) => void) | null>(null);

    // Live Mode 不需要上传音频，直接通过 WebSocket 实时发送

    // 初始化 VAD
    async function initVAD() {
        if (!window.vad) {
            console.error('VAD library not loaded. Please ensure the scripts are included in index.html');
            return;
        }

        try {
            vadInstance.value = await (window.vad.MicVAD as any).new({
                onSpeechStart: () => {
                    console.log('[VAD] Speech started');
                    isSpeaking.value = true;
                    // 调用开始说话回调
                    if (onSpeechStartCallback.value) {
                        onSpeechStartCallback.value();
                    }
                },
                onSpeechRealStart: () => {
                    console.log('[VAD] Real speech started');
                },
                onSpeechEnd: (audio: Float32Array) => {
                    console.log('[VAD] Speech ended, audio length:', audio.length);
                    isSpeaking.value = false;
                    // 调用语音结束回调，传递原始音频数据
                    if (onSpeechEndCallback.value) {
                        onSpeechEndCallback.value(audio);
                    }
                },
                onVADMisfire: () => {
                    console.log('[VAD] VAD misfire - speech segment too short');
                    isSpeaking.value = false;
                },
                onFrameProcessed: (probabilities: { isSpeech: number; notSpeech: number }, frame: Float32Array) => {
                    // 计算 RMS (Root Mean Square) 作为能量
                    let sum = 0;
                    for (let i = 0; i < frame.length; i++) {
                        sum += frame[i] * frame[i];
                    }
                    const rms = Math.sqrt(sum / frame.length);
                    // 简单的归一化及平滑处理，根据经验 RMS 通常较小
                    // 放大系数可以根据实际情况调整
                    const targetEnergy = Math.min(rms * 5, 1);
                    audioEnergy.value = audioEnergy.value * 0.8 + targetEnergy * 0.2;
                },
                // VAD 配置参数
                positiveSpeechThreshold: 0.3,
                negativeSpeechThreshold: 0.25,
                redemptionMs: 1400,
                preSpeechPadMs: 800,
                minSpeechMs: 400,
                submitUserSpeechOnPause: false,
                model: 'v5',
                baseAssetPath: 'https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.29/dist/',
                onnxWASMBasePath: 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.22.0/dist/'
            });

            isInitialized.value = true;
            console.log('VAD initialized successfully');
        } catch (error) {
            console.error('Failed to initialize VAD:', error);
            isInitialized.value = false;
        }
    }

    // 开始录音（启动 VAD）
    async function startRecording(
        onSpeechStart: () => void,
        onSpeechEnd: (audio: Float32Array) => void
    ) {
        // 存储回调函数
        onSpeechStartCallback.value = onSpeechStart;
        onSpeechEndCallback.value = onSpeechEnd;

        if (!isInitialized.value) {
            await initVAD();
        }

        if (vadInstance.value) {
            vadInstance.value.start();
            isRecording.value = true;
            console.log('[VAD] Started');
        }
    }

    // 停止录音（暂停 VAD）
    function stopRecording() {
        if (vadInstance.value) {
            vadInstance.value.pause();
            isRecording.value = false;
            isSpeaking.value = false;
            onSpeechStartCallback.value = null;
            onSpeechEndCallback.value = null;
            console.log('[VAD] Stopped');
        }
    }

    // 清理资源
    onBeforeUnmount(() => {
        if (vadInstance.value && isRecording.value) {
            stopRecording();
        }
    });

    return {
        isRecording,
        isSpeaking,  // 用户是否正在说话
        audioEnergy, // 当前音频能量
        startRecording,
        stopRecording
    };
}
