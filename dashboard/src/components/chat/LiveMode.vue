<template>
    <div class="live-mode-container">
        <div class="header-controls">
            <v-btn icon="mdi-close" @click="handleClose" flat variant="text" />
            <v-btn :icon="isCodeMode ? 'mdi-code-tags-check' : 'mdi-code-tags'" @click="toggleCodeMode" flat
                variant="text" :color="isCodeMode ? 'primary' : ''" />
            <v-btn :icon="isNervousMode ? 'mdi-emoticon-confused' : 'mdi-emoticon-confused-outline'"
                @click="toggleNervousMode" flat variant="text" :color="isNervousMode ? 'primary' : ''" />
        </div>

        <span style="color: gray; padding-left: 16px;">We're developing Astr Live Mode on ChatUI & Desktop right now. Stay tuned!</span>

        <div class="live-mode-content">
            <div class="center-circle-container" @click="handleCircleClick">
                <!-- 爆炸效果层 -->
                <div v-if="isExploding" class="explosion-wave"></div>

                <SiriOrb :energy="orbEnergy" :mode="isActive ? orbMode : 'idle'" :is-dark="isDark"
                    :code-mode="isCodeMode" :nervous-mode="isNervousMode" class="siri-orb" />
            </div>
            <div class="status-text">
                {{ statusText }}
            </div>
            <div class="messages-container" v-if="messages.length > 0">
                <div v-for="(msg, index) in messages" :key="index" class="message-item" :class="msg.type">
                    <div class="message-content">
                        {{ msg.text }}
                    </div>
                </div>
            </div>

            <div class="metrics-container" v-if="Object.keys(metrics).length > 0">
                <span v-if="metrics.wav_assemble_time">WAV Assemble: {{ (metrics.wav_assemble_time * 1000).toFixed(0)
                    }}ms</span>
                <span v-if="metrics.llm_ttft">LLM First Token Latency: {{ (metrics.llm_ttft * 1000).toFixed(0)
                    }}ms</span>
                <span v-if="metrics.llm_total_time">LLM Total Latency: {{ (metrics.llm_total_time * 1000).toFixed(0)
                    }}ms</span>
                <span v-if="metrics.tts_first_frame_time">TTS First Frame Latency: {{ (metrics.tts_first_frame_time *
                    1000).toFixed(0) }}ms</span>
                <span v-if="metrics.tts_total_time">TTS Total Larency: {{ (metrics.tts_total_time * 1000).toFixed(0)
                    }}ms</span>
                <span v-if="metrics.speak_to_first_frame">Speak -> First TTS Frame: {{ (metrics.speak_to_first_frame *
                    1000).toFixed(0) }}ms</span>
                <span v-if="metrics.wav_to_tts_total_time">Speak -> End: {{ (metrics.wav_to_tts_total_time *
                    1000).toFixed(0) }}ms</span>
                <span v-if="metrics.stt">STT Provider: {{ metrics.stt }}</span>
                <span v-if="metrics.tts">TTS Provider: {{ metrics.tts }}</span>
                <span v-if="metrics.chat_model">Chat Model: {{ metrics.chat_model }}</span>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount, watch } from 'vue';
import { useTheme } from 'vuetify';
import { useVADRecording } from '@/composables/useVADRecording';
import SiriOrb from './LiveOrb.vue';

const emit = defineEmits<{
    'close': [];
}>();

const theme = useTheme();
const isDark = computed(() => theme.global.current.value.dark);

// 使用 VAD Recording composable
const vadRecording = useVADRecording();

// 状态
const isActive = ref(false);  // Live Mode 是否激活
const isExploding = ref(false); // 是否正在展示爆炸动画
const isCodeMode = ref(false); // 是否开启代码模式
const isNervousMode = ref(false); // 是否开启紧张模式
// 使用 VAD 提供的 isSpeaking 状态
const isSpeaking = computed(() => vadRecording.isSpeaking.value);
const isListening = ref(false);  // 是否在监听
const isProcessing = ref(false);  // 是否在处理

// WebSocket
let ws: WebSocket | null = null;

// 音频相关
let audioContext: AudioContext | null = null;
let analyser: AnalyserNode | null = null;
const botEnergy = ref(0);
let energyLoopId: number;
let isPlaying = ref(false); // UI 状态：是否正在播放

// 音频播放队列管理
const rawAudioQueue: Uint8Array[] = []; // 待解码队列
const audioBufferQueue: AudioBuffer[] = []; // 待播放队列
let isDecoding = false;
let isPlayingAudio = false; // 内部状态：是否正在播放音频
let currentSource: AudioBufferSourceNode | null = null;


// 消息历史
const messages = ref<Array<{ type: 'user' | 'bot', text: string }>>([]);

interface LiveMetrics {
    wav_assemble_time?: number;
    speak_to_first_frame?: number;
    llm_ttft?: number;
    llm_total_time?: number;
    tts_first_frame_time?: number;
    tts_total_time?: number;
    wav_to_tts_total_time?: number;
    stt?: string;
    tts?: string;
    chat_model?: string;
}
const metrics = ref<LiveMetrics>({});

// 当前语音片段标记
let currentStamp = '';

const statusText = computed(() => {
    if (!isActive.value) return 'Astr Live';
    if (isProcessing.value) return '正在处理...';
    if (isSpeaking.value) return '正在说话...';
    if (isListening.value) return '正在听...';
    return '准备就绪';
});

const getIcon = computed(() => {
    if (!isActive.value) return 'mdi-microphone';
    if (isSpeaking.value) return 'mdi-account-voice';
    if (isProcessing.value) return 'mdi-loading';
    return 'mdi-check';
});

const getIconColor = computed(() => {
    if (!isActive.value) return isDark.value ? 'white' : 'black';
    if (isSpeaking.value) return 'success';
    if (isProcessing.value) return 'warning';
    return 'primary';
});

const orbEnergy = computed(() => {
    if (isPlaying.value) return botEnergy.value;
    if (isSpeaking.value || isListening.value) return vadRecording.audioEnergy.value;
    return 0;
});

const orbMode = computed(() => {
    if (isProcessing.value) return 'processing';
    if (isPlaying.value) return 'speaking';
    if (isSpeaking.value || isListening.value) return 'listening';
    return 'idle';
});

async function handleCircleClick() {
    if (!isActive.value) {
        // 触发爆炸动画
        isExploding.value = true;
        setTimeout(() => {
            isExploding.value = false;
        }, 1000);

        await startLiveMode();
    } else {
        await stopLiveMode();
    }
}

async function startLiveMode() {
    try {
        // 1. 建立 WebSocket 连接
        await connectWebSocket();

        // 2. 初始化音频上下文（用于播放回复音频）
        audioContext = new AudioContext({ sampleRate: 16000 });
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;
        analyser.smoothingTimeConstant = 0.5;

        // 启动能量更新循环
        updateBotEnergy();

        // 3. 启动 VAD 录音
        await vadRecording.startRecording(
            // onSpeechStart 回调
            () => {
                console.log('[Live Mode] VAD 检测到开始说话');
                isListening.value = false;
                currentStamp = generateStamp();

                // 发送开始说话消息
                if (ws && ws.readyState === WebSocket.OPEN) {
                    metrics.value = {}; // Reset metrics
                    ws.send(JSON.stringify({
                        t: 'start_speaking',
                        stamp: currentStamp
                    }));
                }
            },
            // onSpeechEnd 回调
            (audio: Float32Array) => {
                console.log('[Live Mode] VAD 检测到语音结束，音频长度:', audio.length);

                // 将完整音频转换为 PCM16 并发送
                if (ws && ws.readyState === WebSocket.OPEN) {
                    const pcm16 = new Int16Array(audio.length);
                    for (let i = 0; i < audio.length; i++) {
                        const s = Math.max(-1, Math.min(1, audio[i]));
                        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                    }

                    // Base64 编码（分块处理以避免堆栈溢出）
                    const uint8 = new Uint8Array(pcm16.buffer);
                    let base64 = '';
                    const chunkSize = 0x8000; // 32KB chunks
                    for (let i = 0; i < uint8.length; i += chunkSize) {
                        const chunk = uint8.subarray(i, Math.min(i + chunkSize, uint8.length));
                        base64 += String.fromCharCode.apply(null, Array.from(chunk));
                    }
                    base64 = btoa(base64);

                    // 发送完整音频
                    ws.send(JSON.stringify({
                        t: 'speaking_part',
                        data: base64
                    }));

                    // 发送结束说话消息
                    ws.send(JSON.stringify({
                        t: 'end_speaking',
                        stamp: currentStamp
                    }));

                    isProcessing.value = true;
                }
            }
        );

        isActive.value = true;
        isListening.value = true;

    } catch (error) {
        console.error('启动 Live Mode 失败:', error);
        alert('启动失败，请检查麦克风权限或网络连接');
        await stopLiveMode();
    }
}

async function stopLiveMode() {
    cancelAnimationFrame(energyLoopId);

    // 停止 VAD 录音
    vadRecording.stopRecording();

    // 停止音频播放
    stopAudioPlayback();

    // 关闭音频上下文
    if (audioContext) {
        await audioContext.close();
        audioContext = null;
    }

    // 关闭 WebSocket
    if (ws) {
        ws.close();
        ws = null;
    }

    isActive.value = false;
    isListening.value = false;
    isProcessing.value = false;
}

function connectWebSocket(): Promise<void> {
    return new Promise((resolve, reject) => {
        // 获取存储的 token
        const token = localStorage.getItem('token');
        if (!token) {
            reject(new Error('未登录，请先登录'));
            return;
        }

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//localhost:6185/api/live_chat/ws?token=${encodeURIComponent(token)}`;

        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log('[Live Mode] WebSocket 连接成功');
            resolve();
        };

        ws.onerror = (error) => {
            console.error('[Live Mode] WebSocket 错误:', error);
            reject(error);
        };

        ws.onmessage = handleWebSocketMessage;

        ws.onclose = () => {
            console.log('[Live Mode] WebSocket 连接关闭');
        };

        // 超时处理
        setTimeout(() => {
            if (ws?.readyState !== WebSocket.OPEN) {
                reject(new Error('WebSocket 连接超时'));
            }
        }, 5000);
    });
}

// 这些函数不再需要，VAD 库会自动处理语音检测和音频上传

function handleWebSocketMessage(event: MessageEvent) {
    try {
        const message = JSON.parse(event.data);
        const msgType = message.t;

        switch (msgType) {
            case 'user_msg':
                messages.value.push({
                    type: 'user',
                    text: message.data.text
                });
                break;

            case 'bot_text_chunk':
                messages.value.push({
                    type: 'bot',
                    text: message.data.text
                });
                break;

            case 'bot_msg':
                messages.value.push({
                    type: 'bot',
                    text: message.data.text
                });
                isProcessing.value = false;
                isListening.value = true;
                break;

            case 'response':
                // 音频数据
                playAudioChunk(message.data);
                break;

            case 'stop_play':
                // 停止播放
                stopAudioPlayback();
                break;

            case 'end':
                // 处理完成
                isProcessing.value = false;
                isListening.value = true;
                break;

            case 'error':
                console.error('[Live Mode] 错误:', message.data);
                alert('处理出错: ' + message.data);
                isProcessing.value = false;
                isListening.value = true;
                break;

            case 'metrics':
                metrics.value = { ...metrics.value, ...message.data };
                break;
        }
    } catch (error) {
        console.error('[Live Mode] 处理消息失败:', error);
    }
}

function playAudioChunk(base64Data: string) {
    if (!audioContext) return;

    try {
        // 解码 base64
        const binaryString = atob(base64Data);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        // 放入待解码队列
        rawAudioQueue.push(bytes);

        // 触发解码处理
        processRawAudioQueue();

    } catch (error) {
        console.error('[Live Mode] 接收音频数据失败:', error);
    }
}

async function processRawAudioQueue() {
    if (isDecoding || rawAudioQueue.length === 0) return;

    isDecoding = true;

    try {
        while (rawAudioQueue.length > 0) {
            const bytes = rawAudioQueue.shift();
            if (!bytes || !audioContext) continue;

            try {
                // 解码
                const audioBuffer = await audioContext.decodeAudioData(bytes.buffer as ArrayBuffer);
                audioBufferQueue.push(audioBuffer);

                // 如果当前没有播放，立即开始播放
                if (!isPlayingAudio) {
                    playNextAudio();
                }
            } catch (err) {
                console.error('[Live Mode] 解码音频失败:', err);
            }
        }
    } finally {
        isDecoding = false;
        // 如果在解码过程中又有新数据进来，继续处理
        if (rawAudioQueue.length > 0) {
            processRawAudioQueue();
        }
    }
}

function playNextAudio() {
    if (audioBufferQueue.length === 0) {
        isPlayingAudio = false;
        isPlaying.value = false;
        return;
    }

    if (!audioContext) return;

    isPlayingAudio = true;
    isPlaying.value = true;

    try {
        const audioBuffer = audioBufferQueue.shift();
        if (!audioBuffer) return;

        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;

        // 连接到分析器
        if (analyser) {
            source.connect(analyser);
            analyser.connect(audioContext.destination);
        } else {
            source.connect(audioContext.destination);
        }

        currentSource = source;
        source.start();

        source.onended = () => {
            currentSource = null;
            playNextAudio();
        };

    } catch (error) {
        console.error('[Live Mode] 播放音频失败:', error);
        isPlayingAudio = false;
        isPlaying.value = false;
        playNextAudio(); // 尝试播放下一个
    }
}

function stopAudioPlayback() {
    // 停止当前播放源
    if (currentSource) {
        try {
            currentSource.stop();
            currentSource.disconnect();
        } catch (e) {
            // ignore
        }
        currentSource = null;
    }

    // 清空队列
    rawAudioQueue.length = 0;
    audioBufferQueue.length = 0;

    // 重置状态
    isPlayingAudio = false;
    isPlaying.value = false;
    isDecoding = false;
}

function generateStamp(): string {
    return `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

function updateBotEnergy() {
    if (analyser && isPlaying.value) {
        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        analyser.getByteFrequencyData(dataArray);

        let sum = 0;
        // 只计算低频到中频部分，通常人声集中在这里
        const range = Math.floor(dataArray.length * 0.7);
        for (let i = 0; i < range; i++) {
            sum += dataArray[i];
        }
        const average = sum / range;
        // 归一化并放大一点
        botEnergy.value = Math.min(1, (average / 255) * 2.0);
    } else {
        botEnergy.value = Math.max(0, botEnergy.value - 0.1);
    }

    if (isActive.value) {
        energyLoopId = requestAnimationFrame(updateBotEnergy);
    }
}

function handleClose() {
    stopLiveMode();
    emit('close');
}

function toggleCodeMode() {
    isCodeMode.value = !isCodeMode.value;
}

function toggleNervousMode() {
    isNervousMode.value = !isNervousMode.value;
}

// 监听用户打断
watch(isSpeaking, (newVal) => {
    if (newVal && isPlaying.value) {
        // 用户在播放时开始说话，发送打断信号
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ t: 'interrupt' }));
        }
        // 本地立即停止播放
        stopAudioPlayback();
    }
});

onBeforeUnmount(() => {
    stopLiveMode();
});
</script>

<style scoped>
.live-mode-container {
    display: flex;
    flex-direction: column;
    height: 100%;
    width: 100%;
    background: linear-gradient(135deg, rgba(103, 58, 183, 0.05) 0%, rgba(63, 81, 181, 0.05) 100%);
}

.header-controls {
    display: flex;
    padding: 8px;
    gap: 8px;
}

.live-mode-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    position: relative;
    padding: 40px;
}

.center-circle-container {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 40px;
    cursor: pointer;
    /* 给一个最小尺寸，避免在加载或切换时跳动 */
    min-width: 250px;
    min-height: 250px;
}

.siri-orb {
    /* 移除绝对定位，让 Orb 自然占据空间 */
    z-index: 10;
    position: relative;
}

.orb-overlay {
    position: absolute;
    /* 绝对定位，覆盖在 Orb 上 */
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    z-index: 20;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    width: 100%;
    height: 100%;
}

.explosion-wave {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 150px;
    height: 150px;
    border-radius: 50%;
    opacity: 0.8;
    background: radial-gradient(circle, transparent 50%, rgba(125, 80, 201, 0.8) 70%, transparent 100%);
    animation: explode 3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    filter: blur(30px);
    z-index: 0;
    pointer-events: none;
}

@keyframes explode {
    0% {
        transform: translate(-50%, -50%) scale(1);
        opacity: 0.8;
    }

    100% {
        transform: translate(-50%, -50%) scale(50);
        opacity: 0;
    }
}

.status-text {
    font-size: 24px;
    color: var(--v-theme-on-surface);
    margin-bottom: 40px;
    font-family: 'Outfit', sans-serif;
}

.messages-container {
    position: absolute;
    bottom: 40px;
    left: 40px;
    right: 40px;
    max-height: 300px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.message-item {
    color: rgb(var(--v-theme-on-surface));
    display: flex;
    align-items: flex-end;
    align-self: flex-end;
    gap: 12px;
}

.message-content {
    flex: 1;
    word-wrap: break-word;
}

.metrics-container {
    position: absolute;
    bottom: 10px;
    left: 10px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
    color: rgba(var(--v-theme-on-surface), 0.6);
    z-index: 100;
}
</style>
