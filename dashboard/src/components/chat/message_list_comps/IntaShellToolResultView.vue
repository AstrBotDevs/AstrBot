<!--
  IntaShellToolResultView
  ─────────────────────────────────────────────────────────────────────
  交互式 Shell(inta_shell)5 个工具的结果展示分发组件。

  工具组:
    - astrbot_inta_shell_start : 启动交互式 Shell 会话
    - astrbot_inta_shell_send  : 向活跃会话发送输入
    - astrbot_inta_shell_read  : 读取活跃会话的输出
    - astrbot_inta_shell_stop  : 终止会话
    - astrbot_inta_shell_list  : 列出所有活跃会话

  视觉设计:
    复用 ToolResultView 中 `.shell-result` 的容器风格(1px 边框 + 4px
    圆角 + 行间分隔线),通过 5 个内部 v-else-if 分支复用相同骨架。
    状态徽章(state chip)使用 GitHub 风格色板(绿/蓝/琥珀/灰/红)。

  Author: elecvoid243 | 2026-06-14
-->
<template>
    <div v-if="!parsed" class="result-raw">{{ result }}</div>

    <div v-else-if="!parsed.success" class="result-status error">
        <v-icon size="16">mdi-alert-circle</v-icon>
        <span>{{ parsed.error || "Unknown error" }}</span>
    </div>

    <!-- ── start ────────────────────────────────────────────── -->
    <div v-else-if="toolName === 'astrbot_inta_shell_start'" class="session-card">
        <div class="session-card-header">
            <v-icon size="14" class="header-icon">mdi-play-circle-outline</v-icon>
            <span class="header-title">{{ tm('intaShell.headers.start') }}</span>
            <SessionIdCopy v-if="parsed.session" :session-id="parsed.session.session_id" />
            <StateChip v-if="parsed.session" :state="parsed.session.state" />
        </div>
        <div v-if="parsed.session" class="session-card-body">
            <div class="meta-row">
                <span class="meta-label">{{ tm('intaShell.labels.command') }}</span>
                <code class="meta-value">{{ parsed.session.command }}</code>
            </div>
            <div class="meta-row">
                <span class="meta-label">{{ tm('intaShell.labels.pid') }}</span>
                <span class="meta-value-dim">{{ parsed.session.pid }}</span>
                <span v-if="parsed.session.created_at" class="meta-sep">·</span>
                <span v-if="parsed.session.created_at" class="meta-value-dim">
                    {{ tm('intaShell.labels.created') }}: {{ formatRelativeTime(parsed.session.created_at) }}
                </span>
            </div>
            <div v-if="hasInitialOutput" class="output-block">
                <span class="meta-label">{{ tm('intaShell.labels.initialOutput') }}</span>
                <pre class="output-value">{{ parsed.initial_output }}</pre>
            </div>
        </div>
    </div>

    <!-- ── send ─────────────────────────────────────────────── -->
    <div v-else-if="toolName === 'astrbot_inta_shell_send'" class="session-card">
        <div class="session-card-header">
            <v-icon size="14" class="header-icon">mdi-keyboard-outline</v-icon>
            <span class="header-title">{{ tm('intaShell.headers.send') }}</span>
            <SessionIdCopy v-if="parsed.session" :session-id="parsed.session.session_id" />
            <StateChip v-if="parsed.session" :state="parsed.session.state" />
        </div>
        <div v-if="parsed.session || parsed.message" class="session-card-body">
            <div v-if="parsed.message" class="meta-row">
                <span class="meta-label">{{ tm('intaShell.labels.message') }}</span>
                <span class="meta-value">{{ parsed.message }}</span>
            </div>
        </div>
    </div>

    <!-- ── read ─────────────────────────────────────────────── -->
    <div v-else-if="toolName === 'astrbot_inta_shell_read'" class="session-card">
        <div class="session-card-header">
            <v-icon size="14" class="header-icon">mdi-eye-outline</v-icon>
            <span class="header-title">{{ tm('intaShell.headers.read') }}</span>
            <SessionIdCopy v-if="parsed.session" :session-id="parsed.session.session_id" />
            <StateChip v-if="parsed.session" :state="parsed.session.state" />
        </div>
        <div v-if="parsed.session" class="session-card-body">
            <div class="meta-row">
                <span class="meta-label">{{ tm('intaShell.labels.command') }}</span>
                <code class="meta-value">{{ parsed.session.command }}</code>
            </div>
            <div class="output-block">
                <span class="meta-label">{{ tm('intaShell.labels.output') }}</span>
                <pre v-if="hasOutput" class="output-value">{{ parsed.output }}</pre>
                <span v-else class="empty-note">{{ tm('intaShell.labels.noOutput') }}</span>
            </div>
        </div>
    </div>

    <!-- ── stop ─────────────────────────────────────────────── -->
    <div v-else-if="toolName === 'astrbot_inta_shell_stop'" class="session-card">
        <div class="session-card-header">
            <v-icon size="14" class="header-icon">mdi-stop-circle-outline</v-icon>
            <span class="header-title">{{ tm('intaShell.headers.stop') }}</span>
            <SessionIdCopy v-if="parsed.session" :session-id="parsed.session.session_id" />
            <StateChip v-if="parsed.session" :state="parsed.session.state" />
        </div>
        <div v-if="parsed.session" class="session-card-body">
            <div v-if="parsed.message" class="meta-row">
                <span class="meta-label">{{ tm('intaShell.labels.message') }}</span>
                <span class="meta-value">{{ parsed.message }}</span>
            </div>
            <div v-if="parsed.session.exit_code !== null && parsed.session.exit_code !== undefined" class="meta-row">
                <span class="meta-label">{{ tm('intaShell.labels.exitCode') }}</span>
                <span
                    class="exit-code"
                    :class="parsed.session.exit_code === 0 ? 'success' : 'error'"
                >{{ parsed.session.exit_code }}</span>
            </div>
        </div>
    </div>

    <!-- ── list ─────────────────────────────────────────────── -->
    <div v-else-if="toolName === 'astrbot_inta_shell_list'" class="session-card">
        <div class="session-card-header">
            <v-icon size="14" class="header-icon">mdi-format-list-bulleted</v-icon>
            <span class="header-title">
                {{ tm('intaShell.headers.list', { count: parsed.count ?? 0 }) }}
            </span>
        </div>
        <div v-if="sessionsList.length" class="session-list">
            <div v-for="s in sessionsList" :key="s.session_id" class="session-list-item">
                <div class="session-list-line">
                    <SessionIdCopy :session-id="s.session_id" compact />
                    <StateChip :state="s.state" />
                    <span v-if="s.exit_code !== null && s.exit_code !== undefined"
                          class="exit-code-mini"
                          :class="s.exit_code === 0 ? 'success' : 'error'"
                    >exit {{ s.exit_code }}</span>
                </div>
                <code class="session-list-cmd">{{ s.command }}</code>
                <div class="session-list-meta">
                    <span class="meta-value-dim">pid {{ s.pid }}</span>
                    <span v-if="s.last_activity" class="meta-sep">·</span>
                    <span v-if="s.last_activity" class="meta-value-dim">
                        {{ formatRelativeTime(s.last_activity) }}
                    </span>
                </div>
            </div>
        </div>
        <div v-else class="session-card-body">
            <span class="empty-note">{{ tm('intaShell.labels.noSessions') }}</span>
        </div>
    </div>

    <!-- ── unknown tool name (shouldn't happen) ─────────────── -->
    <pre v-else class="result-raw">{{ result }}</pre>
</template>

<script setup lang="ts">
import { computed, h, defineComponent } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import {
    INTA_SHELL_ICONS,
    getSessionStateMeta,
    type SessionStateMeta,
} from "./inta_shell_tools/icons";
import {
    parseIntaShellResult,
    formatRelativeTime,
    type IntaShellSession,
} from "./inta_shell_tools/format";

const props = defineProps<{
    toolName: string;
    result: string;
    args?: Record<string, any>;
}>();

const { tm } = useModuleI18n("features/chat");

// ── Parse the JSON envelope once ─────────────────────────────────
const parsed = computed(() => parseIntaShellResult(props.result));

// ── Per-tool helpers ────────────────────────────────────────────
const hasInitialOutput = computed(() => {
    const out = parsed.value?.initial_output;
    return typeof out === "string" && out.trim().length > 0;
});

const hasOutput = computed(() => {
    const out = parsed.value?.output;
    return typeof out === "string" && out.length > 0;
});

const sessionsList = computed<IntaShellSession[]>(() => {
    return Array.isArray(parsed.value?.sessions) ? parsed.value!.sessions! : [];
});

// ── Inline sub-component: StateChip ─────────────────────────────
// 状态徽章:图标 + 标签 + 颜色 + (running 时) pulse 动画。
const StateChip = defineComponent({
    name: "StateChip",
    props: {
        state: { type: String, required: true },
    },
    setup(p) {
        return () => {
            const meta: SessionStateMeta = getSessionStateMeta(p.state);
            const label = tm(`intaShell.stateLabels.${meta.i18nKey}`);
            return h(
                "span",
                {
                    class: ["state-chip", { pulse: !!meta.pulse }],
                    style: { color: meta.color, borderColor: meta.color },
                    title: p.state,
                },
                [
                    h("i", {
                        class: ["mdi", meta.icon, "state-chip-icon"],
                        style: { color: meta.color },
                    }),
                    h("span", { class: "state-chip-label" }, label),
                ],
            );
        };
    },
});

// ── Inline sub-component: SessionIdCopy ─────────────────────────
// 可复制的 session_id。悬停/点击出现 📋 图标,点击后短暂显示 ✓。
const SessionIdCopy = defineComponent({
    name: "SessionIdCopy",
    props: {
        sessionId: { type: String, required: true },
        compact: { type: Boolean, default: false },
    },
    setup(p) {
        const copied = { value: false };
        const copy = async () => {
            try {
                if (navigator?.clipboard?.writeText) {
                    await navigator.clipboard.writeText(p.sessionId);
                } else {
                    // Fallback for older browsers / non-secure context
                    const ta = document.createElement("textarea");
                    ta.value = p.sessionId;
                    ta.style.position = "fixed";
                    ta.style.opacity = "0";
                    document.body.appendChild(ta);
                    ta.select();
                    document.execCommand("copy");
                    document.body.removeChild(ta);
                }
                copied.value = true;
                window.setTimeout(() => {
                    copied.value = false;
                }, 1200);
            } catch (err) {
                console.error("[IntaShell] failed to copy session id:", err);
            }
        };
        return () => {
            const short = p.sessionId.length > 12
                ? `${p.sessionId.slice(0, 8)}…`
                : p.sessionId;
            return h(
                "span",
                {
                    class: ["session-id", { compact: p.compact }],
                    onClick: copy,
                    title: p.sessionId,
                },
                [
                    h("code", { class: "session-id-text" }, short),
                    h(
                        "i",
                        {
                            class: [
                                "mdi",
                                copied.value ? "mdi-check" : "mdi-content-copy",
                                "session-id-copy",
                            ],
                        },
                    ),
                ],
            );
        };
    },
});

// 工具未识别时回退图标(在 ToolCallCard 已统一为 mdi-wrench,这里兜底)
void INTA_SHELL_ICONS;
</script>

<style scoped>
/* ── Card container (reuses .shell-result visual DNA) ──────── */
.session-card {
    border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
    border-radius: 4px;
    overflow: hidden;
    font-size: 12px;
    line-height: 1.55;
}

.session-card-header {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 8px;
    background: rgba(var(--v-theme-on-surface), 0.04);
    border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.header-icon {
    color: rgba(var(--v-theme-on-surface), 0.5);
    flex-shrink: 0;
}

.header-title {
    font-weight: 600;
    color: rgba(var(--v-theme-on-surface), 0.75);
    font-size: 11.5px;
}

.session-card-body {
    /* nothing by default; rows handle their own padding */
}

/* ── Meta rows (command / pid / message / etc.) ─────────────── */
.meta-row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 3px 8px;
    font-size: 11px;
    line-height: 1.55;
}

.meta-row + .meta-row {
    border-top: 1px solid rgba(var(--v-theme-on-surface), 0.05);
}

.meta-label {
    flex-shrink: 0;
    width: 64px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 11px;
    font-weight: 600;
    color: rgba(var(--v-theme-on-surface), 0.5);
    padding-right: 8px;
}

.meta-value {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 11px;
    color: rgba(var(--v-theme-on-surface), 0.8);
    word-break: break-all;
}

.meta-value-dim {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 11px;
    color: rgba(var(--v-theme-on-surface), 0.55);
}

.meta-sep {
    color: rgba(var(--v-theme-on-surface), 0.3);
    user-select: none;
}

/* ── Output block (stdout / initial_output / read output) ──── */
.output-block {
    padding: 3px 8px;
    border-top: 1px solid rgba(var(--v-theme-on-surface), 0.05);
}

.output-block .meta-label {
    display: block;
    width: auto;
    padding-right: 0;
    margin-bottom: 4px;
}

.output-value {
    flex: 1;
    margin: 0;
    padding: 8px 10px;
    border-radius: 4px;
    background: rgba(var(--v-theme-on-surface), 0.04);
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 11.5px;
    color: rgba(var(--v-theme-on-surface), 0.8);
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 240px;
    overflow-y: auto;
    overflow-x: auto;
}

.empty-note {
    display: block;
    padding: 8px 0;
    font-style: italic;
    color: rgba(var(--v-theme-on-surface), 0.45);
    font-size: 11px;
}

/* ── State chip ─────────────────────────────────────────────── */
.state-chip {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    margin-left: auto;
    padding: 1px 6px;
    border-radius: 9px;
    border: 1px solid;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 10.5px;
    font-weight: 600;
    line-height: 1;
    background: rgba(var(--v-theme-on-surface), 0.02);
    flex-shrink: 0;
}

.state-chip-icon {
    font-size: 11px;
}

.state-chip-label {
    text-transform: lowercase;
    letter-spacing: 0.02em;
}

.state-chip.pulse .state-chip-icon {
    animation: stateChipPulse 1.6s ease-in-out infinite;
}

@keyframes stateChipPulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.45; }
}

/* ── Session id (with copy button) ──────────────────────────── */
.session-id {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 1px 6px;
    border-radius: 3px;
    background: rgba(var(--v-theme-on-surface), 0.05);
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 10.5px;
    color: rgba(var(--v-theme-on-surface), 0.65);
    cursor: pointer;
    user-select: none;
    transition: background 0.15s;
    flex-shrink: 0;
    max-width: 140px;
    overflow: hidden;
}

.session-id:hover {
    background: rgba(var(--v-theme-on-surface), 0.1);
    color: rgba(var(--v-theme-on-surface), 0.85);
}

.session-id.compact {
    padding: 0 4px;
    font-size: 10px;
}

.session-id-text {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.session-id-copy {
    font-size: 11px;
    color: rgba(var(--v-theme-on-surface), 0.45);
    transition: color 0.15s;
}

.session-id:hover .session-id-copy {
    color: rgba(var(--v-theme-on-surface), 0.7);
}

/* ── Exit code badge ────────────────────────────────────────── */
.exit-code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 11px;
    font-weight: 600;
    padding: 1px 6px;
    border-radius: 3px;
}

.exit-code.success {
    background: rgba(70, 200, 70, 0.1);
    color: #2da44e;
}

.exit-code.error {
    background: rgba(255, 100, 100, 0.1);
    color: #cf222e;
}

.exit-code-mini {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 10px;
    font-weight: 600;
    padding: 0 5px;
    border-radius: 3px;
    flex-shrink: 0;
}

.exit-code-mini.success {
    background: rgba(70, 200, 70, 0.1);
    color: #2da44e;
}

.exit-code-mini.error {
    background: rgba(255, 100, 100, 0.1);
    color: #cf222e;
}

/* ── Session list (for list tool) ───────────────────────────── */
.session-list {
    max-height: 320px;
    overflow-y: auto;
}

.session-list-item {
    padding: 6px 8px;
    border-top: 1px solid rgba(var(--v-theme-on-surface), 0.05);
}

.session-list-item:first-child {
    border-top: none;
}

.session-list-line {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 3px;
}

.session-list-cmd {
    display: block;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 11px;
    color: rgba(var(--v-theme-on-surface), 0.75);
    background: rgba(var(--v-theme-on-surface), 0.03);
    padding: 2px 6px;
    border-radius: 3px;
    margin-bottom: 3px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.session-list-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 10.5px;
}
</style>
