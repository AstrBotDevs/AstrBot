declare module "event-source-polyfill" {
  export class EventSourcePolyfill extends EventSource {
    constructor(
      url: string,
      options?: EventSourceInit & { headers?: Record<string, string> },
    );
  }
}
