(function attachAstrBotPluginPageBridge() {
  const CHANNEL = "astrbot-plugin-page";
  const SELF_ORIGIN = window.location.origin;
  const pendingRequests = new Map();
  const sseHandlers = new Map();
  const contextHandlers = new Set();
  let requestCounter = 0;
  let subscriptionCounter = 0;
  let context = null;
  let parentOrigin = null;
  let resolveReady;
  const readyPromise = new Promise((resolve) => {
    resolveReady = resolve;
  });

  function getTargetOrigin() {
    if (
      typeof parentOrigin === "string" &&
      parentOrigin &&
      parentOrigin !== "null"
    ) {
      return parentOrigin;
    }
    if (SELF_ORIGIN !== "null") {
      return SELF_ORIGIN;
    }
    return "*";
  }

  function isAllowedParentOrigin(origin) {
    if (typeof origin !== "string" || !origin) {
      return false;
    }
    if (parentOrigin) {
      return origin === parentOrigin;
    }
    if (SELF_ORIGIN === "null") {
      return true;
    }
    return origin === SELF_ORIGIN;
  }

  function send(kind, payload) {
    window.parent.postMessage(
      {
        channel: CHANNEL,
        kind,
        ...(payload || {}),
      },
      getTargetOrigin(),
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

  function getByPath(source, key) {
    if (!source || typeof source !== "object" || !key) {
      return undefined;
    }

    return String(key)
      .split(".")
      .reduce((current, part) => {
        if (!current || typeof current !== "object" || !(part in current)) {
          return undefined;
        }
        return current[part];
      }, source);
  }

  function translate(key, fallback) {
    const locale = context?.locale;
    const messages = context?.i18n;
    const locales = [locale, "zh-CN", "en-US"].filter(Boolean);
    let value;
    for (const candidateLocale of locales) {
      value = getByPath(messages?.[candidateLocale], key);
      if (value !== undefined && value !== null) {
        break;
      }
    }
    if (value === undefined || value === null) {
      return fallback || "";
    }
    return typeof value === "string" ? value : String(value);
  }

  function notifyContextHandlers() {
    contextHandlers.forEach((handler) => {
      try {
        handler(context);
      } catch (error) {
        console.error("AstrBotPluginPage context handler failed:", error);
      }
    });
  }

  function applyContext(nextContext) {
    if (!nextContext || typeof nextContext !== "object") {
      return;
    }
    context = {
      ...(context || {}),
      ...nextContext,
    };
    if (resolveReady) {
      resolveReady(context);
      resolveReady = null;
    }
    notifyContextHandlers();
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window.parent) {
      return;
    }
    if (!isAllowedParentOrigin(event.origin)) {
      return;
    }
    if (!parentOrigin) {
      parentOrigin = event.origin;
    }

    const message = event.data;
    if (!message || message.channel !== CHANNEL) {
      return;
    }

    if (message.kind === "context") {
      applyContext(message.context);
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
        pending.reject(
          new Error(message.error || "Plugin bridge request failed."),
        );
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

  window.AstrBotPluginPage = {
    ready() {
      return readyPromise;
    },
    getContext() {
      return context;
    },
    getLocale() {
      return context?.locale || "zh-CN";
    },
    getI18n() {
      return context?.i18n || {};
    },
    t(key, fallback) {
      return translate(key, fallback);
    },
    onContext(handler) {
      if (typeof handler !== "function") {
        return () => {};
      }
      contextHandlers.add(handler);
      if (context) {
        handler(context);
      }
      return () => {
        contextHandlers.delete(handler);
      };
    },
    __setInitialContext(nextContext) {
      applyContext(nextContext);
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
