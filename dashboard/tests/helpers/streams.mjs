export function createSseStream({ newline = "\n" } = {}) {
  let controller;
  let closed = false;
  const encoder = new TextEncoder();
  const stats = { cancelled: 0 };
  const body = new ReadableStream({
    start(value) {
      controller = value;
    },
    cancel() {
      stats.cancelled++;
      closed = true;
    },
  });
  return {
    body,
    stats,
    response: new Response(body, { headers: { "content-type": "text/event-stream" } }),
    send: (payload) => controller.enqueue(encoder.encode(`data: ${JSON.stringify(payload)}${newline}${newline}`)),
    close: () => {
      if (!closed) {
        closed = true;
        controller.close();
      }
    },
    fail: (error) => {
      if (!closed) {
        closed = true;
        controller.error(error);
      }
    },
  };
}

export class TestWebSocket extends EventTarget {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances = [];
  readyState = TestWebSocket.CONNECTING;
  sent = [];
  constructor(url) {
    super();
    this.url = url;
    TestWebSocket.instances.push(this);
  }
  open() {
    this.readyState = TestWebSocket.OPEN;
    this.dispatchEvent(new Event("open"));
  }
  send(data) {
    this.sent.push(JSON.parse(data));
  }
  receive(data) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(data) }));
  }
  close() {
    this.readyState = TestWebSocket.CLOSED;
    this.onclose?.(new Event("close"));
  }
}
