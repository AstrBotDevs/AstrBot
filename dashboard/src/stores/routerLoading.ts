import { defineStore } from 'pinia';
import { ref } from 'vue';

export const useRouterLoadingStore = defineStore('routerLoading', () => {
    const isLoading = ref(false);
    const progress = ref(0);
    let progressInterval: ReturnType<typeof setInterval> | null = null;

    function start() {
        isLoading.value = true;
        progress.value = 0;

        if (progressInterval) {
            clearInterval(progressInterval);
        }

        let currentProgress = 0;
        progressInterval = setInterval(() => {
            if (currentProgress < 80) {
                // 快速阶段：0-80%
                currentProgress += Math.random() * 20 + 10;
                if (currentProgress > 80) {
                    currentProgress = 80;
                }
            } else if (currentProgress < 90) {
                // 缓慢阶段：80-90%
                currentProgress += Math.random() * 3 + 1;
                if (currentProgress > 90) {
                    currentProgress = 90;
                }
            }
            progress.value = Math.min(currentProgress, 90);
        }, 50);
    }

    function finish() {
        // 清理interval
        if (progressInterval) {
            clearInterval(progressInterval);
            progressInterval = null;
        }

        // 快速完成到100%
        progress.value = 100;

        // 延迟隐藏，让用户看到100%
        setTimeout(() => {
            isLoading.value = false;
            progress.value = 0;
        }, 300);
    }

    return {
        isLoading,
        progress,
        start,
        finish
    };
});

