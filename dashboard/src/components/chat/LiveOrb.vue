<template>
    <div class="live-orb-container" :class="{ 'dark': isDark }" :style="styleVars">
        <div class="live-orb"></div>
    </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue';

const props = defineProps<{
    energy: number; // 0.0 - 1.0
    mode: 'idle' | 'listening' | 'speaking' | 'processing';
    isDark?: boolean;
}>();

// 内部状态
const currentAngle = ref(Math.random() * 360);
const smoothedSpeed = ref(0.2); // 初始速度
const currentScale = ref(1.0);  // 当前缩放
let animationFrameId: number;

// 颜色配置
const colorConfigs = {
    idle: {
        c1: "rgba(100, 100, 255, 0.6)", // 柔和蓝
        c2: "rgba(200, 100, 255, 0.6)", // 柔和紫
        c3: "rgba(100, 200, 255, 0.6)", // 柔和青
    },
    listening: { // 用户说话 - 活跃的蓝色系
        c1: "rgba(60, 130, 246, 0.8)",  // 亮蓝
        c2: "rgba(34, 211, 238, 0.8)",  // 青色
        c3: "rgba(147, 51, 234, 0.8)",  // 紫色
    },
    speaking: { // Bot 说话 - 活跃的紫红色系
        c1: "rgba(236, 72, 153, 0.8)",  // 粉红
        c2: "rgba(168, 85, 247, 0.8)",  // 紫色
        c3: "rgba(244, 63, 94, 0.8)",   // 玫瑰红
    },
    processing: { // 处理中 - 优雅的青/白/紫流转
        c1: "rgba(255, 255, 255, 0.6)", // 纯净白
        c2: "rgba(168, 85, 247, 0.6)",  // 神秘紫
        c3: "rgba(34, 211, 238, 0.6)",  // 智慧青
    }
};

// 动画逻辑
const animate = () => {
    // 基础速度
    let targetSpeed = 0.1; // idle - 非常慢的流动
    if (props.mode === 'processing') targetSpeed = 0.3; // 思考时稍微活跃
    else if (props.mode === 'listening') targetSpeed = 0.2; // 倾听时轻微波动
    else if (props.mode === 'speaking') targetSpeed = 0.4; // 说话时稍快
    
    // 能量影响速度：能量越高转得越快，但也减弱影响系数
    targetSpeed += (props.energy * 0.4);

    // 速度平滑插值 (Lerp)，避免旋转速度突变
    smoothedSpeed.value += (targetSpeed - smoothedSpeed.value) * 0.05;
    
    // 让角度无限累加，不要取模
    currentAngle.value = currentAngle.value + smoothedSpeed.value;
    
    // 计算目标缩放
    let targetScale = 1.0;
    const e = Math.max(0, Math.min(1, props.energy));
    targetScale += e * 0.15; // 基础能量缩放

    // Processing 模式下的呼吸效果
    if (props.mode === 'processing') {
        const breathing = (Math.sin(Date.now() / 800 * Math.PI) + 1) * 0.03;
        targetScale += breathing;
    }

    // 缩放平滑插值
    currentScale.value += (targetScale - currentScale.value) * 0.1;

    animationFrameId = requestAnimationFrame(animate);
};

onMounted(() => {
    animationFrameId = requestAnimationFrame(animate);
});

onBeforeUnmount(() => {
    cancelAnimationFrame(animationFrameId);
});

const styleVars = computed(() => {
    const baseSize = 250; 
    const blurAmount = Math.max(baseSize * 0.04, 10);
    const contrastAmount = Math.max(baseSize * 0.003, 1.2);
    const colors = colorConfigs[props.mode] || colorConfigs.idle;

    return {
        '--size': `${baseSize}px`,
        '--scale': currentScale.value,
        '--angle': `${currentAngle.value}deg`,
        '--c1': colors.c1,
        '--c2': colors.c2,
        '--c3': colors.c3,
        '--blur-amount': `${blurAmount}px`,
        '--contrast-amount': contrastAmount,
    } as Record<string, string | number>;
});

</script>

<style scoped>
/* 注册 CSS 变量以支持动画插值 */
@property --c1 {
    syntax: "<color>";
    inherits: true;
    initial-value: rgba(0,0,0,0);
}
@property --c2 {
    syntax: "<color>";
    inherits: true;
    initial-value: rgba(0,0,0,0);
}
@property --c3 {
    syntax: "<color>";
    inherits: true;
    initial-value: rgba(0,0,0,0);
}

/* --angle 不需要注册为 property 也能在 JS 中更新，但注册更规范 */
@property --angle {
    syntax: "<angle>";
    inherits: true;
    initial-value: 0deg;
}

.live-orb-container {
    width: var(--size);
    height: var(--size);
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    transform: scale(var(--scale));
    /* 增加 transition 时间，让缩放更柔和 */
    transition: transform 0.2s ease-out, 
                --c1 1s ease,
                --c2 1s ease,
                --c3 1s ease;
}

.live-orb {
    width: 100%;
    height: 100%;
    display: grid;
    grid-template-areas: "stack";
    overflow: hidden;
    border-radius: 50%;
    position: relative;
    background: radial-gradient(
        circle,
        rgba(0, 0, 0, 0.05) 0%,
        rgba(0, 0, 0, 0.02) 30%,
        transparent 70%
    );
    transition: all 0.5s ease;
}

.dark .live-orb {
    background: radial-gradient(
        circle,
        rgba(255, 255, 255, 0.1) 0%,
        rgba(255, 255, 255, 0.05) 30%,
        transparent 70%
    );
}

.live-orb::before {
    content: "";
    display: block;
    grid-area: stack;
    width: 100%;
    height: 100%;
    border-radius: 50%;
    /* 使用 CSS 变量，这里的颜色会自动跟随父容器的 transition */
    background:
        /* 层1：慢速逆时针 - 基底 */
        conic-gradient(
            from calc(var(--angle) * -0.5 + 45deg) at 40% 55%,
            var(--c3) 0deg,
            transparent 60deg 300deg,
            var(--c3) 360deg
        ),
        /* 层2：中速顺时针 - 纹理 */
        conic-gradient(
            from calc(var(--angle) * 0.8) at 60% 45%,
            var(--c2) 0deg,
            transparent 45deg 315deg,
            var(--c2) 360deg
        ),
        /* 层3：快速逆时针 - 扰动 */
        conic-gradient(
            from calc(var(--angle) * -1.2 + 120deg) at 35% 65%,
            var(--c1) 0deg,
            transparent 80deg 280deg,
            var(--c1) 360deg
        ),
        /* 层4：慢速顺时针 - 补色 */
        conic-gradient(
            from calc(var(--angle) * 0.6 + 200deg) at 65% 35%,
            var(--c2) 0deg,
            transparent 50deg 310deg,
            var(--c2) 360deg
        ),
        /* 层5：微弱的旋转底纹 */
        conic-gradient(
            from calc(var(--angle) * 0.3 + 90deg) at 50% 50%,
            var(--c1) 0deg,
            transparent 120deg 240deg,
            var(--c1) 360deg
        ),
        /* 核心高光 - 稍微偏离中心 */
        radial-gradient(
            ellipse 120% 100% at 45% 55%,
            var(--c3) 0%,
            transparent 50%
        );
    
    filter: blur(var(--blur-amount)) contrast(var(--contrast-amount)) saturate(1.5);
    /* 移除 animation，改用 JS 驱动 --angle */
    transform: translateZ(0);
    will-change: transform, background;
    opacity: 0.8;
}

.live-orb::after {
    content: "";
    display: block;
    grid-area: stack;
    width: 100%;
    height: 100%;
    border-radius: 50%;
    background: radial-gradient(
        circle at 45% 55%,
        rgba(255, 255, 255, 0.4) 0%,
        rgba(255, 255, 255, 0.1) 30%,
        transparent 60%
    );
    mix-blend-mode: overlay;
    pointer-events: none;
}
</style>
