/**
 * inta_shell (interactive shell) 工具的图标常量与状态元数据。
 *
 * 镜像 spcode_tools/icons.ts 的结构,集中维护 5 个 inta_shell 工具的
 * mdi 图标以及会话状态(state)的语义映射(标签、颜色、图标)。
 *
 * Author: elecvoid243 | 2026-06-14
 */

export const INTA_SHELL_ICONS: Record<string, string> = {
    astrbot_inta_shell_start: "mdi-play-circle-outline",
    astrbot_inta_shell_send: "mdi-keyboard-outline",
    astrbot_inta_shell_read: "mdi-eye-outline",
    astrbot_inta_shell_stop: "mdi-stop-circle-outline",
    astrbot_inta_shell_list: "mdi-format-list-bulleted",
};

/** inta_shell 工具的合法名称集合。 */
export const INTA_SHELL_TOOL_NAMES: ReadonlySet<string> = new Set(
    Object.keys(INTA_SHELL_ICONS),
);

/** 已知会话状态(对应 session_models.py 中的 InteractiveSessionState)。 */
export type SessionState =
    | "running"
    | "waiting_input"
    | "output_ready"
    | "terminated"
    | "error";

/** 状态元数据:中文标签 / mdi 图标 / 主题色(沿用 GitHub 风格色板)。 */
export interface SessionStateMeta {
    /** i18n key 的尾段,与 intaShell.stateLabels 配合。 */
    i18nKey: string;
    icon: string;
    color: string;
    /** 是否使用 pulse 动画(仅 running)。 */
    pulse?: boolean;
}

export const SESSION_STATE_META: Record<SessionState, SessionStateMeta> = {
    running: {
        i18nKey: "running",
        icon: "mdi-circle-medium",
        color: "#2da44e",
        pulse: true,
    },
    waiting_input: {
        i18nKey: "waitingInput",
        icon: "mdi-cursor-text",
        color: "#0969da",
    },
    output_ready: {
        i18nKey: "outputReady",
        icon: "mdi-message-text-outline",
        color: "#bf8700",
    },
    terminated: {
        i18nKey: "terminated",
        icon: "mdi-check",
        color: "#6e7781",
    },
    error: {
        i18nKey: "error",
        icon: "mdi-alert-circle",
        color: "#cf222e",
    },
};

/** 取状态元数据;未知状态回退到 terminated(中性灰)。 */
export function getSessionStateMeta(
    state: string | null | undefined,
): SessionStateMeta {
    if (state && state in SESSION_STATE_META) {
        return SESSION_STATE_META[state as SessionState];
    }
    return SESSION_STATE_META.terminated;
}
