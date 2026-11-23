import type { InjectionKey } from "vue";
import { fetchWithAuth } from "@/api/http";
import type { MessagePart } from "@/composables/useMessages";
import { readSseStream } from "@/utils/sse";

export interface ViewActionInput {
  action_id: string;
  interaction_id: string;
  expected_revision: number;
  data: unknown;
}

export interface ViewReceipt {
  snapshot?: { data: Record<string, unknown>; revision: number };
  error?: { code: string; message: string } | null;
}

export type ViewActionHandler = (id: string, input: ViewActionInput) => Promise<ViewReceipt>;
export const viewActionKey: InjectionKey<ViewActionHandler> = Symbol("chat-view-action");

export const workbenchChatKey: InjectionKey<
  (input: { mode: "fill" | "send"; text: string; sessionId: string | null }) => Promise<{ sessionId: string | null }>
> = Symbol("workbench-chat");

export interface WorkbenchView {
  plugin_name: string;
  display_name: string;
  name: string;
  title: string;
  description: string;
  i18n?: Record<string, unknown>;
}

export interface WorkbenchTab {
  page?: WorkbenchView;
  launcher?: boolean;
  part: MessagePart;
  action?: ViewActionHandler;
}

export const workbenchKey: InjectionKey<
  | {
      open: (part: MessagePart, action?: ViewActionHandler, automatic?: "history" | "live") => void;
    }
  | undefined
> = Symbol("chat-workbench");

/** Keep streaming chat output after the action receipt resolves the SDK call. */
export function streamViewAction(
  viewId: string,
  input: ViewActionInput,
  onPayload: (payload: any) => void,
  onEnd: () => void,
  signal?: AbortSignal,
): Promise<ViewReceipt> {
  return new Promise((resolve, reject) => {
    let acknowledged = false;
    const checkCancelled = () => {
      if (signal?.aborted) {
        throw signal.reason ?? new DOMException("The view action was cancelled.", "AbortError");
      }
    };
    const receive = (payload: any) => {
      checkCancelled();
      if (payload.type === "ui_action_result") {
        acknowledged = true;
        resolve(payload.data);
      } else {
        onPayload(payload);
      }
    };
    void (async () => {
      try {
        checkCancelled();
        const response = await fetchWithAuth("/api/v1/chat/views/" + encodeURIComponent(viewId) + "/actions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(input),
          signal,
        });
        checkCancelled();
        if (!response.headers.get("content-type")?.includes("text/event-stream")) {
          const result = await response.json();
          checkCancelled();
          if (!response.ok) {
            throw Object.assign(
              new Error(result.message || "View action failed."),
              { code: response.status === 422 ? "INVALID_INPUT" : "ACTION_FAILED" },
              result,
            );
          }
          acknowledged = true;
          resolve(result);
          return;
        }
        if (!response.ok || !response.body) {
          throw new Error("View action stream unavailable.");
        }
        await readSseStream(response.body, receive, signal);
        checkCancelled();
        if (!acknowledged) {
          const status = await fetchWithAuth(
            "/api/v1/chat/views/" + encodeURIComponent(viewId) + "/actions/" + encodeURIComponent(input.interaction_id),
            { signal },
          );
          const outcome = await status.json();
          checkCancelled();
          if (status.ok) resolve(outcome);
          else {
            throw Object.assign(new Error(outcome.message || "The action outcome is unknown."), outcome);
          }
        }
      } catch (error) {
        if (!acknowledged) reject(error);
        else if (!signal?.aborted) {
          onPayload({ type: "error", data: String((error as Error).message) });
        }
      } finally {
        onEnd();
      }
    })().catch((error) => {
      console.error("View action stream cleanup failed:", error);
    });
  });
}
