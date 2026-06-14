const bridge = window.AstrBotPluginPage;
const state = {
  context: null,
  sseId: null,
};

const $ = (selector) => document.querySelector(selector);
const output = $("#output");
const eventList = $("#event-list");

function text(key, fallback) {
  return bridge.t(key, fallback);
}

function writeOutput(label, value) {
  output.textContent = JSON.stringify(
    {
      label,
      value,
      context: bridge.getContext(),
      locale: bridge.getLocale(),
      i18nLocales: Object.keys(bridge.getI18n()),
    },
    null,
    2,
  );
}

function renderContext() {
  const context = bridge.getContext() || {};
  state.context = context;
  document.title = text("pages.bridge-lab.title", "Bridge Lab");
  document.documentElement.lang = bridge.getLocale();
  $("#locale-chip").textContent = `${text("pages.bridge-lab.locale", "Locale")}: ${bridge.getLocale()}`;
  $("#theme-chip").textContent = `${text("pages.bridge-lab.theme", "Theme")}: ${
    context.isDark
      ? text("pages.bridge-lab.dark", "Dark")
      : text("pages.bridge-lab.light", "Light")
  }`;
  $("#plugin-name").textContent = context.pluginName || "-";
  $("#page-name").textContent = context.pageName || "-";
  $("#display-name").textContent = context.displayName || "-";
  $("#page-title").textContent = context.pageTitle || "-";

  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.getAttribute("data-i18n");
    node.textContent = text(key, node.textContent);
  });
}

async function callGet() {
  const result = await bridge.apiGet("echo/demo-item", {
    limit: $("#limit-input").value,
    tag: $("#tag-input").value,
  });
  writeOutput("apiGet", result);
}

async function callPost() {
  const result = await bridge.apiPost("settings/save", {
    enabled: $("#enabled-input").checked,
    threshold: Number($("#threshold-input").value),
    note: $("#note-input").value,
  });
  writeOutput("apiPost", result);
}

async function uploadFile() {
  const file = $("#file-input").files?.[0];
  if (!file) {
    writeOutput("upload", {
      error: text("pages.bridge-lab.noFile", "Choose a file first."),
    });
    return;
  }
  const result = await bridge.upload("files/import", file);
  writeOutput("upload", result);
}

async function downloadFile() {
  const result = await bridge.download(
    "files/export",
    { format: "json" },
    "plugin-page-demo-export.json",
  );
  writeOutput("download", result);
}

async function startSse() {
  if (state.sseId) {
    await bridge.unsubscribeSSE(state.sseId);
    state.sseId = null;
  }
  eventList.replaceChildren();
  state.sseId = await bridge.subscribeSSE(
    "events",
    {
      onOpen() {
        appendEvent("open", {});
      },
      onMessage(event) {
        appendEvent("message", {
          raw: event.raw,
          parsed: event.parsed,
          lastEventId: event.lastEventId,
        });
      },
      onError() {
        appendEvent("error", {});
      },
    },
    { count: 5, delay_ms: 400 },
  );
  writeOutput("subscribeSSE", { subscriptionId: state.sseId });
}

async function stopSse() {
  if (!state.sseId) {
    return;
  }
  const closedId = state.sseId;
  await bridge.unsubscribeSSE(closedId);
  state.sseId = null;
  appendEvent("closed", { subscriptionId: closedId });
  writeOutput("unsubscribeSSE", {
    subscriptionId: closedId,
    message: text("pages.bridge-lab.sseClosed", "SSE closed"),
  });
}

async function callError() {
  try {
    await bridge.apiGet("error");
  } catch (error) {
    writeOutput("error", {
      message: error.message,
    });
  }
}

function appendEvent(type, value) {
  const item = document.createElement("li");
  const code = document.createElement("code");
  code.textContent = JSON.stringify({ type, value });
  item.append(code);
  eventList.append(item);
}

function bindActions() {
  $("#refresh-context").addEventListener("click", () => {
    renderContext();
    writeOutput("getContext", {
      message: text("pages.bridge-lab.contextChanged", "Context updated"),
      context: bridge.getContext(),
    });
  });
  $("#call-get").addEventListener("click", () => void callGet());
  $("#call-post").addEventListener("click", () => void callPost());
  $("#upload-file").addEventListener("click", () => void uploadFile());
  $("#download-file").addEventListener("click", () => void downloadFile());
  $("#start-sse").addEventListener("click", () => void startSse());
  $("#stop-sse").addEventListener("click", () => void stopSse());
  $("#call-error").addEventListener("click", () => void callError());
}

window.addEventListener("beforeunload", () => {
  if (state.sseId) {
    void bridge.unsubscribeSSE(state.sseId);
  }
});

await bridge.ready();
bindActions();
renderContext();
bridge.onContext(() => {
  renderContext();
  writeOutput("onContext", {
    message: text("pages.bridge-lab.contextChanged", "Context updated"),
  });
});
writeOutput("ready", {
  message: text("pages.bridge-lab.ready", "bridge.ready() completed"),
});
