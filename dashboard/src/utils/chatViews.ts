import type { InjectionKey } from "vue";
import type { MessagePart } from "@/composables/useMessages";
import { fetchWithAuth } from "@/api/http";

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

export type ViewActionHandler = (
  id: string,
  input: ViewActionInput,
) => Promise<ViewReceipt>;
export const viewActionKey: InjectionKey<ViewActionHandler> =
  Symbol("chat-view-action");

export const workbenchChatKey: InjectionKey<(input: {
  mode: "fill" | "send";
  text: string;
  sessionId: string | null;
}) => Promise<{ sessionId: string | null }>> = Symbol("workbench-chat");

export interface WorkbenchView {
  plugin_name: string;
  display_name: string;
  name: string;
  title: string;
  description: string;
}

export interface WorkbenchTab {
  page?: WorkbenchView;
  launcher?: boolean;
  part: MessagePart;
  action?: ViewActionHandler;
}

export const workbenchKey: InjectionKey<
  | {
      open: (
        part: MessagePart,
        action?: ViewActionHandler,
        automatic?: "history" | "live",
      ) => void;
    }
  | undefined
> = Symbol("chat-workbench");

/** Keep streaming chat output after the action receipt resolves the SDK call. */
export function streamViewAction(
  viewId: string,
  input: ViewActionInput,
  onPayload: (payload: any) => void,
  onEnd: () => void,
): Promise<ViewReceipt> {
  return new Promise((resolve, reject) => {
    let acknowledged = false;
    const receive = (payload: any) => {
      if (payload.type === "ui_action_result") {
        acknowledged = true;
        resolve(payload.data);
      } else {
        onPayload(payload);
      }
    };
    void (async () => {
      try {
        const response = await fetchWithAuth(
          `/api/v1/chat/views/${encodeURIComponent(viewId)}/actions`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(input),
          },
        );
        if (
          !response.headers.get("content-type")?.includes("text/event-stream")
        ) {
          const result = await response.json();
          if (!response.ok)
            throw Object.assign(
              new Error(result.message || "View action failed."),
              {
                code:
                  response.status === 422 ? "INVALID_INPUT" : "ACTION_FAILED",
              },
              result,
            );
          acknowledged = true;
          resolve(result);
          return;
        }
        if (!response.ok || !response.body)
          throw new Error("View action stream unavailable.");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let pending = "";
        try {
          while (true) {
            const { value, done } = await reader.read();
            pending += decoder.decode(value, { stream: !done });
            pending = pending.replace(/\r\n/g, "\n");
            let boundary: number;
            while ((boundary = pending.indexOf("\n\n")) >= 0) {
              const frame = pending.slice(0, boundary);
              pending = pending.slice(boundary + 2);
              const data = frame
                .split("\n")
                .filter((line) => line.startsWith("data:"))
                .map((line) => line.slice(5).trimStart())
                .join("\n");
              if (data && data !== "[DONE]") receive(JSON.parse(data));
            }
            if (done) break;
          }
        } finally {
          reader.releaseLock();
        }
        if (!acknowledged) {
          const status = await fetchWithAuth(
            `/api/v1/chat/views/${encodeURIComponent(
              viewId,
            )}/actions/${encodeURIComponent(input.interaction_id)}`,
          );
          const outcome = await status.json();
          if (status.ok) resolve(outcome);
          else
            throw Object.assign(
              new Error(outcome.message || "The action outcome is unknown."),
              outcome,
            );
        }
      } catch (error) {
        if (!acknowledged) reject(error);
        else
          onPayload({ type: "error", data: String((error as Error).message) });
      } finally {
        onEnd();
      }
    })();
  });
}
