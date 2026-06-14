/**
 * inta_shell 工具结果的解析与格式化工具。
 *
 * - parseIntaShellResult:从工具返回的 JSON 字符串解析出标准化对象。
 *   注意 inta_shell 的成功响应是扁平的 `{success, ...}`(不嵌套 data),
 *   失败响应是 `{success:false, error}`,与 spcode 工具不同。
 * - formatRelativeTime:把 unix 时间戳格式化为"5s ago / 2m ago"等相对时间。
 *
 * Author: elecvoid243 | 2026-06-14
 */

export interface IntaShellSession {
    session_id: string;
    command: string;
    pid: number;
    state: string;
    exit_code: number | null;
    error_message: string | null;
    created_at: number | null;
    last_activity: number | null;
}

export interface ParsedIntaShellResult {
    success: boolean;
    /** start / read 工具:启动时的初始输出或读取到的输出。 */
    initial_output?: string;
    output?: string;
    /** 多数工具携带的 session 信息;stop / read / start 都会附带。 */
    session?: IntaShellSession;
    /** send / stop 工具的简短成功消息。 */
    message?: string;
    /** list 工具:活跃会话列表。 */
    sessions?: IntaShellSession[];
    /** list 工具:会话总数。 */
    count?: number;
    /** 失败时的错误描述。 */
    error?: string;
}

/**
 * 解析 inta_shell 工具返回的 JSON 字符串。
 * 返回 null 表示解析失败,调用方应降级为 result-raw 渲染。
 */
export function parseIntaShellResult(raw: string): ParsedIntaShellResult | null {
    if (!raw) return null;
    const text = raw.trim();
    if (!text) return null;
    try {
        const parsed = JSON.parse(text);
        if (parsed && typeof parsed === "object") {
            return parsed as ParsedIntaShellResult;
        }
        return null;
    } catch {
        return null;
    }
}

/**
 * 把 unix 时间戳格式化为相对时间。
 * - < 60s: "Ns ago"
 * - < 60m: "Nm ago"
 * - < 24h: "Nh ago"
 * - 否则:返回本地日期字符串
 * 入参为 null/undefined/0/非有限数时返回 "—"。
 */
export function formatRelativeTime(
    ts: number | null | undefined,
    now: number = Date.now() / 1000,
): string {
    if (ts === null || ts === undefined) return "—";
    if (!Number.isFinite(ts) || ts <= 0) return "—";
    const diff = Math.max(0, now - ts);
    if (diff < 5) return "just now";
    if (diff < 60) return `${Math.floor(diff)}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    try {
        return new Date(ts * 1000).toLocaleString();
    } catch {
        return "—";
    }
}
