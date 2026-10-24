const bridge = window.AstrBotPluginView;
const context = await bridge.ready();
const $ = (id) => document.getElementById(id);
const zh = {
  title: "子代理",
  description: "配置专家模板，查看任务执行进度。",
  refresh: "刷新",
  create: "创建专家",
  edit: "编辑",
  editTitle: "编辑专家",
  experts: "专家模板",
  progress: "执行进度",
  expertHint: "主 Agent 可以按任务选择专家，使用对应的人格、模型和工具。",
  expertCount: "个专家",
  progressHint:
    "查看委派任务和执行记录。追加指令或取消任务，请通过主 Agent 操作。",
  workers: "子代理",
  detail: "执行记录",
  empty: "还没有委派任务。可以让主 Agent 把一项任务交给子代理执行。",
  select: "选择一个子代理查看执行记录。",
  noHistory: "尚未记录完整执行步骤。",
  turn: "轮次",
  steps: "步已完成",
  result: "结果",
  error: "错误",
  updated: "更新于",
  retry: "无法加载数据，请刷新重试。",
  loading: "正在加载专家…",
  noExperts: "还没有专家模板",
  noExpertsHint: "为常用任务配置一个专家，主 Agent 就能按需委派。",
  noDescription: "尚未填写用途说明",
  enabled: "启用专家",
  enabledHint: "启用后，主 Agent 可通过 spawn_agent 选择此模板。",
  enabledState: "已启用",
  disabledState: "已停用",
  enable: "启用",
  disable: "停用",
  name: "名称",
  nameHint: "使用小写字母开头，可包含数字和下划线。",
  provider: "模型提供商",
  unresolvedProvider: "尚未确定",
  providerHint: "留空时跟随主 Agent 当前使用的模型。",
  followMain: "跟随主 Agent",
  summary: "用途说明",
  summaryPlaceholder: "描述专家擅长的任务，帮助主 Agent 选择。",
  persona: "人格",
  personaHint: "选择人格后，提示词和工具继承人格配置。",
  customPersona: "自定义提示词与工具",
  prompt: "系统提示词",
  promptPlaceholder: "说明专家的职责、约束和输出要求。",
  tools: "工具",
  toolsCustom: "选择工具",
  toolsAll: "全部可用工具",
  toolsNone: "不使用工具",
  toolHint: "子代理只使用已启用且有权限的工具。",
  searchTools: "搜索工具",
  noTools: "暂无可选工具",
  inherited: "继承人格工具：",
  unavailable: "当前不可用",
  custom: "自定义人格",
  toolCount: "个工具",
  save: "保存专家",
  saving: "保存中…",
  saved: "专家已保存",
  deleted: "专家已删除",
  cancel: "取消",
  close: "关闭",
  delete: "删除",
  deleteTitle: "删除专家",
  deleteHint: "已经启动的任务会继续执行。",
  deleteQuestion: "确定删除专家",
  invalidName:
    "名称须以小写字母开头，仅包含小写字母、数字和下划线，最多 64 个字符。",
  duplicateName: "专家名称不能重复。",
  busy: "正在保存，请稍候。",
  pending: "排队中",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  timed_out: "超时",
  interrupted: "已中断",
};
const en = {
  title: "Subagents",
  description: "Configure expert templates and inspect delegated work.",
  refresh: "Refresh",
  create: "Create expert",
  edit: "Edit",
  editTitle: "Edit expert",
  experts: "Expert templates",
  progress: "Worker progress",
  expertHint:
    "Main can choose an expert with its own persona, model, and tools.",
  expertCount: "experts",
  progressHint:
    "Inspect tasks and execution records. Send instructions or cancel tasks through main.",
  workers: "Workers",
  detail: "Execution record",
  empty: "No delegated tasks yet. Ask main to delegate a task to a worker.",
  select: "Select a worker to inspect its record.",
  noHistory: "No completed steps recorded yet.",
  turn: "Turn",
  steps: "completed steps",
  result: "Result",
  error: "Error",
  updated: "Updated",
  retry: "Could not load data. Refresh to retry.",
  loading: "Loading experts…",
  noExperts: "No expert templates yet",
  noExpertsHint:
    "Create an expert for a recurring task so main can delegate to it.",
  noDescription: "No description yet",
  enabled: "Enable expert",
  enabledHint: "Enabled templates are available to main through spawn_agent.",
  enabledState: "Enabled",
  disabledState: "Disabled",
  enable: "Enable",
  disable: "Disable",
  name: "Name",
  nameHint:
    "Start with a lowercase letter; use letters, numbers, and underscores.",
  provider: "Model provider",
  unresolvedProvider: "Not resolved",
  providerHint: "Leave unset to use main’s current model.",
  followMain: "Follow main",
  summary: "Description",
  summaryPlaceholder: "Describe the tasks this expert handles.",
  persona: "Persona",
  personaHint: "Selecting a persona inherits its prompt and tools.",
  customPersona: "Custom prompt and tools",
  prompt: "System prompt",
  promptPlaceholder:
    "Describe responsibilities, constraints, and expected output.",
  tools: "Tools",
  toolsCustom: "Choose tools",
  toolsAll: "All available tools",
  toolsNone: "No tools",
  toolHint: "Workers only use enabled tools they are permitted to access.",
  searchTools: "Search tools",
  noTools: "No tools available",
  inherited: "Inherited tools: ",
  unavailable: "Unavailable",
  custom: "Custom persona",
  toolCount: "tools",
  save: "Save expert",
  saving: "Saving…",
  saved: "Expert saved",
  deleted: "Expert deleted",
  cancel: "Cancel",
  close: "Close",
  delete: "Delete",
  deleteTitle: "Delete expert",
  deleteHint: "Tasks already started will continue.",
  deleteQuestion: "Delete expert",
  invalidName:
    "Use up to 64 lowercase letters, numbers, and underscores, starting with a letter.",
  duplicateName: "Expert names must be unique.",
  busy: "Saving. Please wait.",
  pending: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
  timed_out: "Timed out",
  interrupted: "Interrupted",
};
let english = String(context.locale || navigator.language).startsWith("en");
let t = english ? en : zh;
let experts = [];
let options = { providers: [], personas: [], tools: [] };
let expertLoading = false;
let expertsLoaded = false;
let mutationPending = false;
let activeTab = "experts";
let editingIndex = -1;
let deletingIndex = -1;
let draft = null;
let selected = null;
let progressLoading = false;
let timer;

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text != null) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function applyContext(next) {
  const theme =
    typeof next.isDark === "boolean"
      ? next.isDark
        ? "dark"
        : "light"
      : next.theme;
  if (["light", "dark"].includes(theme))
    document.documentElement.dataset.theme = theme;
  english = String(next.locale || navigator.language).startsWith("en");
  t = english ? en : zh;
  document.documentElement.lang = english ? "en" : "zh-CN";
  document.title = t.title;
  for (const element of document.querySelectorAll("[data-i18n]"))
    element.textContent = t[element.dataset.i18n];
  for (const element of document.querySelectorAll("[data-i18n-placeholder]"))
    element.placeholder = t[element.dataset.i18nPlaceholder];
  for (const element of document.querySelectorAll("[data-i18n-aria]"))
    element.setAttribute("aria-label", t[element.dataset.i18nAria]);
  $("editor-title").textContent = editingIndex < 0 ? t.create : t.editTitle;
  renderExperts();
}

function showError(exception, target = $("error")) {
  target.textContent = exception.message || t.retry;
  target.hidden = false;
}

function showNotice(message) {
  $("notice").textContent = message;
  $("notice").hidden = false;
  $("error").hidden = true;
}

function action(text, handler, className = "text", actionName = "") {
  const button = node("button", text, `button ${className}`);
  button.type = "button";
  button.disabled = mutationPending || !expertsLoaded;
  button.dataset.action = actionName;
  button.addEventListener("click", handler);
  return button;
}

function switchTab(tab) {
  activeTab = tab;
  for (const name of ["experts", "progress"]) {
    $(`tab-${name}`).setAttribute("aria-selected", String(name === tab));
    $(`tab-${name}`).tabIndex = name === tab ? 0 : -1;
    $(`panel-${name}`).hidden = name !== tab;
  }
  $("create").hidden = tab !== "experts";
  if (tab === "progress") refreshProgress();
}

function renderExperts() {
  const container = $("experts");
  container.replaceChildren();
  $("expert-count").textContent = expertsLoaded
    ? `${experts.length} ${t.expertCount}`
    : "—";
  if (!expertsLoaded) {
    container.append(node("p", t.loading, "card padded empty"));
    return;
  }
  if (!experts.length) {
    const empty = node("div", null, "card empty empty-card");
    empty.append(
      node("h3", t.noExperts),
      node("p", t.noExpertsHint),
      action(t.create, () => openEditor(-1), "tonal", "create"),
    );
    container.append(empty);
    return;
  }
  experts.forEach((expert, index) => {
    const card = node("article", null, "card expert-card");
    const top = node("div", null, "expert-top");
    const state = node(
      "span",
      expert.enabled !== false ? t.enabledState : t.disabledState,
      "state",
    );
    state.dataset.state = expert.enabled !== false ? "enabled" : "disabled";
    top.append(node("strong", expert.name, "expert-name"), state);
    const meta = node("div", null, "expert-meta");
    meta.append(
      node("span", expert.persona_id || t.custom),
      node("span", expert.provider_id || t.followMain),
    );
    if (!expert.persona_id)
      meta.append(
        node(
          "span",
          expert.tools === null
            ? t.toolsAll
            : `${(expert.tools || []).length} ${t.toolCount}`,
        ),
      );
    const actions = node("div", null, "expert-actions");
    actions.append(
      action(
        expert.enabled !== false ? t.disable : t.enable,
        async () => {
          try {
            await persistExperts(
              experts.map((item, i) =>
                i === index
                  ? { ...item, enabled: item.enabled === false }
                  : item,
              ),
            );
            showNotice(t.saved);
          } catch (exception) {
            showError(exception);
          }
        },
        "text",
        "toggle",
      ),
      action(t.edit, () => openEditor(index), "text", "edit"),
      action(
        t.delete,
        () => {
          deletingIndex = index;
          $(
            "delete-message",
          ).textContent = `${t.deleteQuestion} “${expert.name}”?`;
          $("delete-dialog").showModal();
        },
        "text",
        "delete",
      ),
    );
    card.append(
      top,
      node(
        "p",
        expert.public_description || t.noDescription,
        "expert-description",
      ),
      meta,
      actions,
    );
    container.append(card);
  });
}

function fillSelect(select, items, emptyLabel, current, label) {
  select.replaceChildren();
  const empty = node("option", emptyLabel);
  empty.dataset.i18n =
    select.id === "expert-provider" ? "followMain" : "customPersona";
  empty.value = "";
  select.append(empty);
  for (const item of items) {
    const option = node("option", label(item));
    option.value = item.id;
    select.append(option);
  }
  if (current && !items.some((item) => item.id === current)) {
    const missing = node("option", `${current} (${t.unavailable})`);
    missing.value = current;
    select.append(missing);
  }
  select.value = current || "";
}

function renderTools(selectedTools) {
  const list = $("tool-options");
  list.replaceChildren();
  const all = [...options.tools];
  for (const name of selectedTools)
    if (!all.some((tool) => tool.name === name))
      all.push({ name, description: t.unavailable });
  for (const tool of all) {
    const row = node("label", null, "tool-option");
    const checkbox = node("input");
    checkbox.type = "checkbox";
    checkbox.value = tool.name;
    checkbox.checked = selectedTools.includes(tool.name);
    const text = node("span", tool.name);
    text.append(node("small", tool.description));
    row.append(checkbox, text);
    row.dataset.search = `${tool.name} ${tool.description}`.toLowerCase();
    list.append(row);
  }
  if (!all.length) list.append(node("p", t.noTools, "empty"));
}

function readTools() {
  if ($("expert-tool-mode").value === "all") return null;
  if ($("expert-tool-mode").value === "none") return [];
  return [...$("tool-options").querySelectorAll("input:checked")].map(
    (item) => item.value,
  );
}

function updatePersona() {
  const persona = options.personas.find(
    (item) => item.id === $("expert-persona").value,
  );
  const inherited = Boolean($("expert-persona").value);
  $("expert-prompt").disabled = inherited;
  $("expert-tool-mode").disabled = inherited;
  if (inherited) {
    $("expert-tool-mode").value =
      persona?.tools === null
        ? "all"
        : persona?.tools?.length
        ? "custom"
        : "none";
    $("expert-prompt").value = persona?.prompt || "";
    $("tool-picker").hidden = true;
    $("inherited-tools").hidden = false;
    $("inherited-tools").textContent =
      t.inherited +
      (persona
        ? persona.tools === null
          ? t.toolsAll
          : persona.tools?.join(", ") || t.toolsNone
        : t.unavailable);
  } else {
    $("expert-prompt").value = draft.system_prompt;
    $("expert-tool-mode").value =
      draft.tools === null ? "all" : draft.tools.length ? "custom" : "none";
    $("tool-picker").hidden = $("expert-tool-mode").value !== "custom";
    $("inherited-tools").hidden = true;
    renderTools(draft.tools || []);
  }
}

function openEditor(index) {
  if (mutationPending || expertLoading || !expertsLoaded) return;
  editingIndex = index;
  const source = index >= 0 ? experts[index] : {};
  draft = {
    name: source.name || "",
    enabled: source.enabled !== false,
    public_description: source.public_description || "",
    persona_id: source.persona_id || "",
    provider_id: source.provider_id || "",
    system_prompt: source.system_prompt || "",
    tools: source.tools === null ? null : [...(source.tools || [])],
  };
  $("editor-title").textContent = index < 0 ? t.create : t.editTitle;
  $("expert-name").value = draft.name;
  $("expert-description").value = draft.public_description;
  $("expert-enabled").checked = draft.enabled;
  fillSelect(
    $("expert-provider"),
    options.providers,
    t.followMain,
    draft.provider_id,
    (item) => `${item.id}${item.model ? ` · ${item.model}` : ""}`,
  );
  fillSelect(
    $("expert-persona"),
    options.personas,
    t.customPersona,
    draft.persona_id,
    (item) => item.id,
  );
  $("tool-search").value = "";
  $("form-error").hidden = true;
  updatePersona();
  $("editor").showModal();
  $("expert-name").focus();
}

async function loadExperts() {
  if (expertLoading || mutationPending) return;
  expertLoading = true;
  $("create").disabled = true;
  try {
    const response = await bridge.apiGet("experts");
    if (!Array.isArray(response.agents)) throw new Error(t.retry);
    experts = response.agents;
    expertsLoaded = true;
    options = {
      providers: response.providers || [],
      personas: response.personas || [],
      tools: response.tools || [],
    };
    renderExperts();
    $("error").hidden = true;
  } catch (exception) {
    showError(exception);
    if (!expertsLoaded)
      $("experts").replaceChildren(node("p", t.retry, "card padded empty"));
  } finally {
    expertLoading = false;
    $("create").disabled = !expertsLoaded;
  }
}

async function persistExperts(list) {
  if (mutationPending) throw new Error(t.busy);
  mutationPending = true;
  $("save-expert").disabled =
    $("confirm-delete").disabled =
    $("create").disabled =
      true;
  $("save-expert").textContent = t.saving;
  renderExperts();
  try {
    const response = await bridge.apiPost("experts", { agents: list });
    if (!Array.isArray(response.agents)) throw new Error(t.retry);
    experts = response.agents;
  } finally {
    mutationPending = false;
    $("save-expert").disabled =
      $("confirm-delete").disabled =
      $("create").disabled =
        false;
    $("save-expert").textContent = t.save;
    renderExperts();
  }
}

function renderRecord(worker) {
  $("detail").replaceChildren(
    node("h3", worker.name),
    node("p", worker.agent_id, "identity"),
    node(
      "p",
      `${t.provider}：${worker.provider_id || t.unresolvedProvider}`,
      "identity",
    ),
  );
  for (const [label, content] of [
    [t.error, worker.error],
    [t.result, worker.result],
  ]) {
    if (!content) continue;
    const row = node("div", null, "record");
    row.append(node("div", label, "record-label"), node("pre", content));
    $("detail").append(row);
  }
  if (!worker.messages?.length)
    $("detail").append(node("p", t.noHistory, "empty"));
  for (const message of worker.messages || []) {
    const row = node("div", null, "record");
    const content =
      typeof message.content === "string"
        ? message.content
        : JSON.stringify(message.content, null, 2);
    row.append(
      node("div", message.role || message.type || "checkpoint", "record-label"),
      node("pre", content),
    );
    if (message.tool_calls)
      row.append(node("pre", JSON.stringify(message.tool_calls, null, 2)));
    $("detail").append(row);
  }
}

async function refreshDetail(id) {
  const response = await bridge.apiGet("runtime", { agent_id: id });
  if (!Array.isArray(response.agents)) throw new Error(t.retry);
  if (selected === id && response.agents[0]) renderRecord(response.agents[0]);
}

async function refreshProgress() {
  if (progressLoading) return;
  progressLoading = true;
  try {
    const response = await bridge.apiGet("runtime");
    if (!Array.isArray(response.agents)) throw new Error(t.retry);
    const focused = document.activeElement?.dataset?.id;
    $("workers").replaceChildren();
    if (!response.agents.length)
      $("workers").append(node("p", t.empty, "empty"));
    if (
      selected &&
      !response.agents.some((worker) => worker.agent_id === selected)
    )
      selected = null;
    for (const worker of response.agents) {
      const button = node("button", null, "worker");
      button.type = "button";
      button.dataset.id = worker.agent_id;
      button.setAttribute("aria-pressed", String(worker.agent_id === selected));
      const top = node("div", null, "worker-top");
      const state = node("span", t[worker.state] || worker.state, "state");
      state.dataset.state = worker.state;
      top.append(node("strong", worker.name), state);
      button.append(
        top,
        node(
          "small",
          `${t.provider}：${worker.provider_id || t.unresolvedProvider}`,
        ),
        node(
          "small",
          `${t.turn} ${worker.turn_id} · ${worker.completed_steps} ${t.steps}`,
        ),
        node("small", worker.session),
      );
      button.addEventListener("click", async () => {
        selected = worker.agent_id;
        for (const item of $("workers").children)
          item.setAttribute(
            "aria-pressed",
            String(item.dataset.id === selected),
          );
        renderRecord(worker);
        try {
          await refreshDetail(selected);
        } catch (exception) {
          showError(exception);
        }
      });
      $("workers").append(button);
      if (focused === worker.agent_id) button.focus();
    }
    if (selected) await refreshDetail(selected);
    else $("detail").replaceChildren(node("p", t.select, "empty"));
    if (activeTab === "progress") $("error").hidden = true;
    $("updated").textContent = `${
      t.updated
    } ${new Date().toLocaleTimeString()}`;
  } catch (exception) {
    showError(exception);
  } finally {
    progressLoading = false;
  }
}

$("tab-experts").addEventListener("click", () => switchTab("experts"));
$("tab-progress").addEventListener("click", () => switchTab("progress"));
for (const name of ["experts", "progress"])
  $(`tab-${name}`).addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const target =
      event.key === "Home"
        ? "experts"
        : event.key === "End"
        ? "progress"
        : name === "experts"
        ? "progress"
        : "experts";
    switchTab(target);
    $(`tab-${target}`).focus();
  });
$("create").addEventListener("click", () => openEditor(-1));
$("refresh").addEventListener("click", async () => {
  $("notice").hidden = true;
  $("error").hidden = true;
  if (activeTab === "experts") await loadExperts();
  else await refreshProgress();
});
for (const id of ["close-editor", "cancel-editor"])
  $(id).addEventListener("click", () => {
    if (!mutationPending) $("editor").close();
  });
$("editor").addEventListener("cancel", (event) => {
  if (mutationPending) event.preventDefault();
});
$("cancel-delete").addEventListener("click", () => {
  if (!mutationPending) $("delete-dialog").close();
});
$("delete-dialog").addEventListener("cancel", (event) => {
  if (mutationPending) event.preventDefault();
});
$("expert-persona").addEventListener("change", () => {
  if (!draft.persona_id) {
    draft.system_prompt = $("expert-prompt").value;
    draft.tools = readTools();
  }
  draft.persona_id = $("expert-persona").value;
  updatePersona();
});
$("expert-tool-mode").addEventListener("change", () => {
  $("tool-picker").hidden = $("expert-tool-mode").value !== "custom";
});
$("tool-search").addEventListener("input", () => {
  const query = $("tool-search").value.trim().toLowerCase();
  for (const item of $("tool-options").children)
    item.hidden = !String(item.dataset.search || "").includes(query);
});
$("expert-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("form-error").hidden = true;
  const name = $("expert-name").value.trim();
  if (!/^[a-z][a-z0-9_]{0,63}$/.test(name)) {
    showError(new Error(t.invalidName), $("form-error"));
    return;
  }
  if (
    experts.some((item, index) => index !== editingIndex && item.name === name)
  ) {
    showError(new Error(t.duplicateName), $("form-error"));
    return;
  }
  const persona = $("expert-persona").value;
  const item = {
    name,
    enabled: $("expert-enabled").checked,
    public_description: $("expert-description").value.trim(),
    persona_id: persona || null,
    provider_id: $("expert-provider").value || null,
    system_prompt: persona ? draft.system_prompt : $("expert-prompt").value,
    tools: persona ? draft.tools : readTools(),
  };
  const next = experts.map((expert, index) =>
    index === editingIndex ? item : expert,
  );
  if (editingIndex < 0) next.push(item);
  try {
    await persistExperts(next);
    $("editor").close();
    showNotice(t.saved);
  } catch (exception) {
    showError(exception, $("form-error"));
  }
});
$("confirm-delete").addEventListener("click", async () => {
  try {
    await persistExperts(experts.filter((_, index) => index !== deletingIndex));
    $("delete-dialog").close();
    showNotice(t.deleted);
  } catch (exception) {
    $("delete-dialog").close();
    showError(exception);
  }
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refreshProgress();
});
bridge.onContext(applyContext);
await Promise.all([loadExperts(), refreshProgress()]);
async function poll() {
  clearTimeout(timer);
  if (!document.hidden) await refreshProgress();
  timer = setTimeout(poll, 3000);
}
timer = setTimeout(poll, 3000);
