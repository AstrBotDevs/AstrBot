(function attachAstrBotPluginWebUIBridge() {
  const CHANNEL = "astrbot-plugin-webui";
  const TARGET_ORIGIN = window.location.origin;
  const pendingRequests = new Map();
  const sseHandlers = new Map();
  let requestCounter = 0;
  let subscriptionCounter = 0;
  let context = null;
  let resolveReady;
  const readyPromise = new Promise((resolve) => {
    resolveReady = resolve;
  });

  function send(kind, payload) {
    window.parent.postMessage(
      {
        channel: CHANNEL,
        kind,
        ...(payload || {}),
      },
      TARGET_ORIGIN,
    );
  }

  function makeRequest(action, payload) {
    return new Promise((resolve, reject) => {
      requestCounter += 1;
      const requestId = `plugin_req_${requestCounter}`;
      pendingRequests.set(requestId, { resolve, reject });
      send("request", {
        requestId,
        action,
        ...(payload || {}),
      });
    });
  }

  function parseMaybeJson(value) {
    if (typeof value !== "string") {
      return value;
    }
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window.parent) {
      return;
    }
    if (event.origin !== TARGET_ORIGIN) {
      return;
    }

    const message = event.data;
    if (!message || message.channel !== CHANNEL) {
      return;
    }

    if (message.kind === "context") {
      context = message.context || null;
      if (resolveReady) {
        resolveReady(context);
        resolveReady = null;
      }
      return;
    }

    if (message.kind === "response") {
      const pending = pendingRequests.get(message.requestId);
      if (!pending) {
        return;
      }
      pendingRequests.delete(message.requestId);
      if (message.ok) {
        pending.resolve(message.data);
      } else {
        pending.reject(new Error(message.error || "Plugin bridge request failed."));
      }
      return;
    }

    if (message.kind === "sse_message") {
      const handlers = sseHandlers.get(message.subscriptionId);
      if (handlers?.onMessage) {
        handlers.onMessage({
          raw: message.data,
          parsed: parseMaybeJson(message.data),
          lastEventId: message.lastEventId,
        });
      }
      return;
    }

    if (message.kind === "sse_state") {
      const handlers = sseHandlers.get(message.subscriptionId);
      if (message.state === "open" && handlers?.onOpen) {
        handlers.onOpen();
      }
      if (message.state === "error" && handlers?.onError) {
        handlers.onError();
      }
    }
  });

  window.AstrBotPluginWebUI = {
    ready() {
      return readyPromise;
    },
    getContext() {
      return context;
    },
    apiGet(endpoint, params) {
      return makeRequest("api:get", { endpoint, params });
    },
    apiPost(endpoint, body) {
      return makeRequest("api:post", { endpoint, body });
    },
    upload(endpoint, file) {
      return makeRequest("files:upload", {
        endpoint,
        file,
        fileName: file?.name || "upload.bin",
      });
    },
    download(endpoint, params, filename) {
      return makeRequest("files:download", { endpoint, params, filename });
    },
    async subscribeSSE(endpoint, handlers, params) {
      subscriptionCounter += 1;
      const subscriptionId = `plugin_sse_${subscriptionCounter}`;
      sseHandlers.set(subscriptionId, handlers || {});
      try {
        await makeRequest("sse:subscribe", {
          endpoint,
          params,
          subscriptionId,
        });
        return subscriptionId;
      } catch (error) {
        sseHandlers.delete(subscriptionId);
        throw error;
      }
    },
    async unsubscribeSSE(subscriptionId) {
      sseHandlers.delete(subscriptionId);
      return makeRequest("sse:unsubscribe", { subscriptionId });
    },
  };

  send("ready");
})();
