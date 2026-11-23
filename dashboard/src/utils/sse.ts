export type SsePayload = Record<string, unknown>;

/**
 * Read JSON SSE frames until EOF, cancellation, or the chat terminal event.
 * A terminal event closes the reader even if the server keeps the socket open.
 */
export async function readSseStream(
  body: ReadableStream<Uint8Array>,
  onPayload: (payload: SsePayload) => void,
  signal?: AbortSignal,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  let data: string[] = [];

  const abort = () => {
    void reader.cancel(signal?.reason).catch(() => {});
  };
  signal?.addEventListener("abort", abort, { once: true });

  function checkAborted() {
    if (signal?.aborted) {
      throw signal.reason ?? new DOMException("The stream was cancelled.", "AbortError");
    }
  }

  function dispatch(): boolean {
    if (!data.length) return false;
    const frame = data.join("\n");
    data = [];
    if (!frame) return false;
    let value: unknown;
    try {
      value = frame === "[DONE]" ? { type: "end" } : JSON.parse(frame);
    } catch (error) {
      console.error("Failed to parse SSE payload:", error);
      return false;
    }
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    const payload = value as SsePayload;
    onPayload(payload);
    checkAborted();
    return (payload.type || payload.t) === "end";
  }

  try {
    checkAborted();
    while (true) {
      const { value, done } = await reader.read();
      checkAborted();
      pending += decoder.decode(value, { stream: !done });
      while (true) {
        const boundary = pending.search(/[\r\n]/);
        if (boundary < 0) break;
        const newline = pending[boundary];
        // A CR at a chunk boundary may be the first half of CRLF.
        if (!done && newline === "\r" && boundary === pending.length - 1) break;
        const line = pending.slice(0, boundary);
        const width = newline === "\r" && pending[boundary + 1] === "\n" ? 2 : 1;
        pending = pending.slice(boundary + width);
        if (line === "") {
          if (dispatch()) return;
        } else if (line.startsWith("data:")) {
          const field = line.slice(5);
          data.push(field.startsWith(" ") ? field.slice(1) : field);
        }
      }
      // An incomplete final frame is not an SSE event.
      if (done) return;
    }
  } finally {
    signal?.removeEventListener("abort", abort);
    try {
      await reader.cancel();
    } catch {
      // The body may already have failed or been cancelled.
    } finally {
      reader.releaseLock();
    }
  }
}
