(function attachAstrBotPluginPageBridge() {
  const CHANNEL = "astrbot-plugin-page";
  const SELF_ORIGIN = window.location.origin;
  const pendingRequests = new Map();
  const sseHandlers = new Map();
  const contextHandlers = new Set();
  const viewHandlers = new Set();
  let viewBusy = false;
  let sizeObserver;
  let bridgeSession;
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

  function send(kind, payload, transfer) {
    window.parent.postMessage(
      {
        channel: CHANNEL,
        ...(bridgeSession ? { session: bridgeSession } : {}),
        kind,
        ...(payload || {}),
      },
      getTargetOrigin(),
      transfer || [],
    );
  }

  function makeRequest(action, payload, transfer) {
    return new Promise((resolve, reject) => {
      if (context?.target === "chat_message" && action !== "view:action") {
        reject(
          Object.assign(
            new Error("This capability is unavailable in chat views."),
            {
              code: "UNSUPPORTED_CAPABILITY",
            },
          ),
        );
        return;
      }
      requestCounter += 1;
      const requestId = `plugin_req_${requestCounter}`;
      pendingRequests.set(requestId, { resolve, reject });
      try {
        send(
          "request",
          {
            requestId,
            action,
            ...(payload || {}),
          },
          transfer,
        );
      } catch (error) {
        pendingRequests.delete(requestId);
        reject(error);
      }
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
    const previousView = context?.view;
    const viewChanged =
      nextContext.view &&
      (!previousView || nextContext.view.revision >= previousView.revision);
    context = {
      ...(context || {}),
      ...nextContext,
      ...(nextContext.view
        ? {
            view: viewChanged
              ? structuredClone(nextContext.view)
              : previousView,
          }
        : {}),
    };
    if (typeof nextContext.isDark === "boolean") {
      document.documentElement.setAttribute(
        "data-theme",
        nextContext.isDark ? "dark" : "light",
      );
    }
    const colors = context.themeColors || {};
    const dark = context.isDark === true;
    // Match the host scheme so transparent iframes do not get an opaque canvas.
    document.documentElement.style.setProperty(
      "color-scheme",
      dark ? "dark" : "light",
    );
    const tokens = {
      primary: colors.primary || (dark ? "#5ba4d4" : "#3c96ca"),
      secondary: colors.secondary || (dark ? "#4a95c4" : "#2f86bd"),
      "on-primary": colors["on-primary"] || "#ffffff",
      text:
        colors.primaryText ||
        colors["on-surface"] ||
        (dark ? "#e8eaed" : "#1b1c1d"),
      "text-secondary":
        colors.secondaryText || (dark ? "#ffffffdd" : "#000000aa"),
      background: colors.background || (dark ? "#1a1a1a" : "#ffffff"),
      surface: colors.surface || (dark ? "#242424" : "#ffffff"),
      border: colors.border || (dark ? "#333333ee" : "#d0d0d0"),
      error: colors.error || (dark ? "#ff4d4f" : "#f44336"),
    };
    for (const [name, value] of Object.entries(tokens)) {
      document.documentElement.style.setProperty(
        `--astrbot-color-${name}`,
        value,
      );
    }
    if (viewChanged) {
      for (const handler of viewHandlers) {
        try {
          handler(structuredClone(context.view));
        } catch (error) {
          console.error("Plugin view subscriber failed:", error);
        }
      }
    }
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
    const message = event.data;
    if (!message || message.channel !== CHANNEL) {
      return;
    }
    if (bridgeSession && message.session !== bridgeSession) return;
    if (!parentOrigin) parentOrigin = event.origin;

    if (message.kind === "context") {
      if (!bridgeSession && message.session) bridgeSession = message.session;
      applyContext(message.context);
      return;
    }

    if (message.kind === "response") {
      const pending = pendingRequests.get(message.requestId);
      if (!pending) {
        return;
      }
      pendingRequests.delete(message.requestId);
      if (message.snapshot) applyContext({ view: message.snapshot });
      if (message.ok) {
        pending.resolve(message.data);
      } else {
        pending.reject(
          Object.assign(
            new Error(
              message.error?.message ||
                message.error ||
                "Plugin bridge request failed.",
            ),
            typeof message.error === "object" ? message.error : {},
          ),
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
          eventType: message.eventType || "message",
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
      if (message.state === "closed" || message.state === "error") {
        sseHandlers.delete(message.subscriptionId);
        if (message.state === "closed" && handlers?.onClose) {
          handlers.onClose();
        } else if (message.state === "error" && handlers?.onError) {
          handlers.onError();
        }
      }
    }
  });

  window.AstrBotPluginView = {
    async ready() {
      await readyPromise;
      if (
        context?.target === "chat_message" &&
        window.ResizeObserver &&
        !sizeObserver
      ) {
        if (document.readyState === "loading") {
          await new Promise((resolve) =>
            document.addEventListener("DOMContentLoaded", resolve, {
              once: true,
            }),
          );
        }
        if (!sizeObserver) {
          let previousHeight;
          sizeObserver = new window.ResizeObserver(() => {
            const margins = window.getComputedStyle(document.body);
            const height = Math.ceil(
              document.body.getBoundingClientRect().height +
                parseFloat(margins.marginTop) +
                parseFloat(margins.marginBottom),
            );
            if (height === previousHeight) return;
            previousHeight = height;
            send("resize", { height });
          });
          sizeObserver.observe(document.body);
        }
      }
      return context;
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
    view: {
      subscribe(handler) {
        if (context?.target !== "chat_message" || !context.view) {
          throw Object.assign(
            new Error(
              "No chat view snapshot is available. Await bridge.ready() first.",
            ),
            {
              code: "UNSUPPORTED_CAPABILITY",
            },
          );
        }
        viewHandlers.add(handler);
        handler(structuredClone(context.view));
        return () => viewHandlers.delete(handler);
      },
      async action(actionId, data = null) {
        await readyPromise;
        if (context?.target !== "chat_message" || !context.view) {
          throw Object.assign(
            new Error("View actions require a chat message."),
            { code: "UNSUPPORTED_CAPABILITY" },
          );
        }
        if (viewBusy) {
          throw Object.assign(new Error("An action is already pending."), {
            code: "ACTION_IN_PROGRESS",
          });
        }
        viewBusy = true;
        try {
          const id =
            crypto.randomUUID?.() ||
            Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) =>
              byte.toString(16).padStart(2, "0"),
            ).join("");
          await makeRequest("view:action", {
            input: {
              action_id: actionId,
              interaction_id: id,
              expected_revision: context.view.revision,
              data,
            },
          });
        } finally {
          viewBusy = false;
        }
      },
    },
    apiGet(endpoint, params) {
      return makeRequest("api:get", { endpoint, params });
    },
    apiPost(endpoint, body) {
      return makeRequest("api:post", { endpoint, body });
    },
    async upload(endpoint, file) {
      if (!file || typeof file.arrayBuffer !== "function") {
        throw new Error("Missing uploaded file payload.");
      }
      const fileBuffer = await file.arrayBuffer();
      return makeRequest(
        "files:upload",
        {
          endpoint,
          fileName: file?.name || "upload.bin",
          fileType: file?.type || "application/octet-stream",
          fileLastModified:
            typeof file?.lastModified === "number" ? file.lastModified : null,
          fileBuffer,
        },
        [fileBuffer],
      );
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

  // "Views" is the preferred naming; AstrBotPluginPage stays as an alias.
  window.AstrBotPluginPage = window.AstrBotPluginView;

  send("ready");
})();
