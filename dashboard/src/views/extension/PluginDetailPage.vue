<script setup>
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import axios from "axios";
import DOMPurify from "dompurify";
import MarkdownIt from "markdown-it";
import defaultPluginIcon from "@/assets/images/plugin_icon.png";
import { usePluginI18n } from "@/utils/pluginI18n";
import PluginPlatformChip from "@/components/shared/PluginPlatformChip.vue";

const props = defineProps({
  plugin: {
    type: Object,
    required: true,
  },
  marketPlugin: {
    type: Object,
    default: null,
  },
  sourceTab: {
    type: String,
    default: "installed",
  },
  state: {
    type: Object,
    required: true,
  },
});

const { tm, router } = props.state;
const { pluginName, pluginDesc: resolvePluginDesc } = usePluginI18n();

const markdown = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  breaks: false,
});

markdown.enable(["table", "strikethrough"]);

const MARKDOWN_SANITIZE_OPTIONS = {
  ALLOWED_TAGS: [
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "br",
    "hr",
    "ul",
    "ol",
    "li",
    "blockquote",
    "pre",
    "code",
    "a",
    "img",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "strong",
    "em",
    "del",
    "s",
    "div",
    "span",
  ],
  ALLOWED_ATTR: ["href", "src", "alt", "title", "target", "rel", "align"],
};

const readmeLoading = ref(false);
const readmeError = ref("");
const readmeEmpty = ref(false);
const renderedReadme = ref("");
const changelogLoading = ref(false);
const changelogError = ref("");
const changelogEmpty = ref(false);
const renderedChangelog = ref("");
const expandedCommandGroups = ref(new Set());
const logoLoadFailed = ref(false);
const detailPageRef = ref(null);
const isHeaderStuck = ref(false);
const pluginDetail = ref(null);

const pluginData = computed(() => pluginDetail.value || props.plugin);
const displayName = computed(() => pluginName(pluginData.value));
const detailSourceTab = computed(() =>
  props.sourceTab === "market" ? "market" : "installed",
);
const isMarketDetail = computed(() => detailSourceTab.value === "market");
const detailParentTitle = computed(() =>
  isMarketDetail.value
    ? tm("tabs.market")
    : tm("titles.installedAstrBotPlugins"),
);

const pluginDesc = computed(() => {
  const plugin = pluginData.value || {};
  const desc =
    plugin.desc ||
    plugin.description ||
    props.marketPlugin?.desc ||
    props.marketPlugin?.description ||
    "";
  return String(resolvePluginDesc(plugin, desc) || "").trim();
});

const logoSrc = computed(() => {
  const logo = pluginData.value?.logo || props.marketPlugin?.logo || "";
  if (logoLoadFailed.value) {
    return defaultPluginIcon;
  }
  return typeof logo === "string" && logo.trim().length
    ? logo
    : defaultPluginIcon;
});

const authorDisplay = computed(() => {
  const plugin = pluginData.value || {};
  const marketPlugin = props.marketPlugin || {};
  const author =
    plugin.author ||
    marketPlugin.author ||
    plugin.author_name ||
    marketPlugin.author_name ||
    plugin.owner ||
    marketPlugin.owner;

  if (Array.isArray(author)) {
    return author.join(", ");
  }
  if (author && typeof author === "object") {
    return author.name || "";
  }
  return typeof author === "string" ? author.trim() : "";
});

const categoryDisplay = computed(() => {
  const rawCategory =
    pluginData.value?.category || props.marketPlugin?.category || "";
  const category = String(rawCategory || "").trim();
  if (!category) return "";

  const normalized = category.toLowerCase().replace(/\s+/g, "_");
  const label = tm(`market.categories.${normalized}`);
  return label === `market.categories.${normalized}` ? category : label;
});

const authorWebsite = computed(() => {
  const plugin = pluginData.value || {};
  const marketPlugin = props.marketPlugin || {};
  return (
    plugin.social_link ||
    marketPlugin.social_link ||
    plugin.author_url ||
    marketPlugin.author_url ||
    plugin.homepage ||
    marketPlugin.homepage ||
    ""
  );
});

const repoUrl = computed(
  () => pluginData.value?.repo || props.marketPlugin?.repo || "",
);

const firstPresentValue = (...values) =>
  values.find(
    (value) =>
      value !== undefined &&
      value !== null &&
      value !== "" &&
      (!Array.isArray(value) || value.length > 0),
  );

const versionDisplay = computed(() =>
  String(
    firstPresentValue(pluginData.value?.version, props.marketPlugin?.version) ||
      "",
  ).trim(),
);

const starsDisplay = computed(() => {
  const value = firstPresentValue(
    pluginData.value?.stars,
    props.marketPlugin?.stars,
  );
  return value === undefined ? "" : String(value);
});

const tagsDisplay = computed(() => {
  const tags = firstPresentValue(
    pluginData.value?.tags,
    props.marketPlugin?.tags,
  );
  if (!Array.isArray(tags)) return [];
  return tags.filter((tag) => typeof tag === "string" && tag.trim().length > 0);
});

const astrbotVersionDisplay = computed(() =>
  String(
    firstPresentValue(
      pluginData.value?.astrbot_version,
      props.marketPlugin?.astrbot_version,
    ) || "",
  ).trim(),
);

const supportPlatformsDisplay = computed(() => {
  const platforms = firstPresentValue(
    pluginData.value?.support_platforms,
    props.marketPlugin?.support_platforms,
  );
  if (!Array.isArray(platforms)) return [];
  return platforms.filter((platform) => typeof platform === "string");
});

const infoRows = computed(() => {
  const rows = [
    {
      label: tm("detail.info.version"),
      value: versionDisplay.value,
      optional: true,
    },
    { label: tm("detail.info.author"), value: authorDisplay.value },
    {
      label: tm("detail.info.category"),
      value: categoryDisplay.value,
      optional: true,
    },
    {
      label: tm("detail.info.stars"),
      value: starsDisplay.value,
      optional: true,
    },
    {
      label: tm("detail.info.tags"),
      value: tagsDisplay.value,
      kind: "tags",
      optional: true,
    },
    {
      label: tm("detail.info.astrbotVersion"),
      value: astrbotVersionDisplay.value,
      optional: true,
    },
    {
      label: tm("detail.info.supportPlatforms"),
      value: supportPlatformsDisplay.value,
      kind: "platforms",
      optional: true,
    },
    {
      label: tm("detail.info.authorWebsite"),
      value: authorWebsite.value,
      href: authorWebsite.value,
      optional: true,
    },
    {
      label: tm("detail.info.repository"),
      value: repoUrl.value,
      href: repoUrl.value,
      optional: true,
    },
  ];

  return rows.filter(
    (row) =>
      !row.optional ||
      (Array.isArray(row.value) ? row.value.length > 0 : row.value),
  );
});

const normalizeHandlerList = (source) => {
  if (!source || typeof source !== "object") return [];
  if (Array.isArray(source.handlers)) {
    return source.handlers.filter(
      (handler) => handler && typeof handler === "object",
    );
  }
  if (Array.isArray(source.command_handlers)) {
    return source.command_handlers.filter(
      (handler) => handler && typeof handler === "object",
    );
  }
  if (Array.isArray(source.commands)) {
    return source.commands
      .filter(
        (command) =>
          command &&
          (typeof command === "string" || typeof command === "object"),
      )
      .map((command) =>
        typeof command === "string"
          ? { cmd: command, type: "指令" }
          : { type: command.type || "指令", ...command },
      );
  }
  return [];
};

const componentGroupOrder = [
  "page",
  "skill",
  "command",
  "llm_tool",
  "listener",
  "hook",
];

const componentGroupIcons = {
  page: "mdi-monitor-dashboard",
  skill: "mdi-lightning-bolt",
  command: "mdi-console-line",
  llm_tool: "mdi-tools",
  listener: "mdi-broadcast",
  hook: "mdi-hook",
};

const getLegacyHandlerGroupKey = (handler) => {
  const type = String(handler?.type || "").trim();
  const eventType = String(handler?.event_type || "").trim();
  const eventTypeH = String(handler?.event_type_h || "").trim();

  if (["指令", "指令组", "正则匹配"].includes(type)) {
    return "command";
  }
  if (eventType === "OnCallingFuncToolEvent" || eventTypeH === "函数工具") {
    return "llm_tool";
  }
  if (type === "事件监听器") {
    return "listener";
  }
  return "hook";
};

const getComponentGroupKey = (component) => {
  const type = String(
    component?.type || component?.component_type || "",
  ).trim();
  if (componentGroupOrder.includes(type)) return type;
  return getLegacyHandlerGroupKey(component);
};

const normalizeComponent = (component, fallbackType = "") => {
  const type = fallbackType || getComponentGroupKey(component);
  const normalized = { ...component, type };
  if (component?.type && component.type !== type && !normalized.display_type) {
    normalized.display_type = component.type;
  }
  return normalized;
};

const normalizeComponentList = (source) => {
  if (!source || typeof source !== "object") return [];
  const { components } = source;

  if (
    components &&
    typeof components === "object" &&
    !Array.isArray(components)
  ) {
    return componentGroupOrder.flatMap((key) =>
      Array.isArray(components[key])
        ? components[key]
            .filter((component) => component && typeof component === "object")
            .map((component) => normalizeComponent(component, key))
        : [],
    );
  }

  if (Array.isArray(components)) {
    return components
      .filter((component) => component && typeof component === "object")
      .map((component) => normalizeComponent(component));
  }

  return normalizeHandlerList(source).map((handler) => ({
    ...handler,
    type: getLegacyHandlerGroupKey(handler),
  }));
};

const components = computed(() => {
  const pluginComponents = normalizeComponentList(pluginData.value);
  if (pluginComponents.length > 0) return pluginComponents;
  return normalizeComponentList(props.marketPlugin);
});

const groupedComponentSections = computed(() => {
  const groups = new Map(componentGroupOrder.map((key) => [key, []]));

  components.value.forEach((component) => {
    const key = getComponentGroupKey(component);
    groups.get(key)?.push(component);
  });

  return componentGroupOrder
    .map((key) => ({
      key,
      title: tm(`detail.handlerGroups.${key}`),
      icon: componentGroupIcons[key],
      components: groups.get(key) || [],
    }))
    .filter((group) => group.components.length > 0);
});

const getHandlerCommand = (handler) =>
  String(
    handler?.name ||
      handler?.cmd ||
      handler?.handler_name ||
      tm("status.unknown"),
  ).trim();

const getHandlerDisplayName = (handler, groupKey) => {
  if (handler?.name) {
    return handler.name;
  }
  if (["llm_tool", "listener"].includes(groupKey)) {
    return handler?.handler_name || handler?.cmd || tm("status.unknown");
  }
  return handler?.cmd || handler?.handler_name || tm("status.unknown");
};

const getHandlerTiming = (handler) =>
  String(handler?.event_type_h || handler?.event_type || "").trim();

const isCommandGroupExpanded = (key) => expandedCommandGroups.value.has(key);

const toggleCommandGroup = (key) => {
  const next = new Set(expandedCommandGroups.value);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  expandedCommandGroups.value = next;
};

const getComponentDescription = (component) =>
  String(
    component?.description || component?.desc || tm("status.unknown"),
  ).trim();

const openComponentPage = (component) => {
  const targetPluginName = component?.plugin_name || pluginData.value?.name;
  const targetPageName = component?.page_name || component?.name;
  if (!targetPluginName || !targetPageName) return;
  router.push({
    name: "PluginPage",
    params: {
      pluginName: targetPluginName,
      pageName: targetPageName,
    },
  });
};

const getCommandRowKey = (component, path) =>
  component?.handler_full_name || component?.path || path.join(" ");

const buildCommandComponentRows = (commandComponents) => {
  const rows = [];

  const appendRows = (component, path = [], depth = 0) => {
    const name = getHandlerCommand(component);
    const nextPath = [...path, name];
    const key = getCommandRowKey(component, nextPath);
    const children = Array.isArray(component?.subcommands)
      ? component.subcommands.filter(
          (child) => child && typeof child === "object",
        )
      : [];

    rows.push({
      kind:
        children.length > 0 ? "group" : depth > 0 ? "subCommand" : "handler",
      key,
      component,
      displayCommand: name,
      children,
      depth,
    });

    if (!children.length || !isCommandGroupExpanded(key)) return;
    children.forEach((child) => appendRows(child, nextPath, depth + 1));
  };

  commandComponents.forEach((component) => appendRows(component));
  return rows;
};

const openExternal = (url) => {
  if (!url) return;
  window.open(url, "_blank", "noopener,noreferrer");
};

const goBack = () => {
  router.push({ name: "Extensions", hash: `#${detailSourceTab.value}` });
};

const renderMarkdown = (source) => {
  const normalizedSource = String(source || "")
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'");
  const rawHtml = markdown.render(normalizedSource);
  const cleanHtml = DOMPurify.sanitize(rawHtml, MARKDOWN_SANITIZE_OPTIONS);
  const container = document.createElement("div");
  container.innerHTML = cleanHtml;

  container.querySelectorAll("a").forEach((link) => {
    const href = link.getAttribute("href") || "";
    if (href.startsWith("http") || href.startsWith("//")) {
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noopener noreferrer");
    }
  });

  return container.innerHTML;
};

const updateHeaderStuckState = () => {
  const scrollTop =
    document.scrollingElement?.scrollTop ||
    document.documentElement.scrollTop ||
    window.scrollY ||
    0;
  isHeaderStuck.value = scrollTop > 0;
};

const scrollToHashTarget = async () => {
  if (window.location.hash !== "#plugin-components") return;
  await nextTick();
  document.getElementById("plugin-components")?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
};

const fetchPluginDetail = async () => {
  pluginDetail.value = null;
  if (isMarketDetail.value || !props.plugin?.name) return;

  try {
    const res = await axios.get("/api/plugin/detail", {
      params: { name: props.plugin.name },
    });
    if (res.data.status === "ok" && res.data.data) {
      pluginDetail.value = res.data.data;
      await scrollToHashTarget();
    }
  } catch (err) {
    console.debug("Failed to fetch plugin detail:", err);
  }
};

const getDocumentUrl = (fieldName) => {
  const plugin = pluginData.value || {};
  const marketPlugin = props.marketPlugin || {};
  return String(plugin[fieldName] || marketPlugin[fieldName] || "").trim();
};

const fetchRemoteMarkdown = async (url) => {
  const res = await axios.get(url, {
    responseType: "text",
    transformResponse: [(data) => data],
  });
  return typeof res.data === "string" ? res.data : String(res.data || "");
};

const fetchReadme = async () => {
  const plugin = pluginData.value || {};
  if (!plugin?.name) return;

  readmeLoading.value = true;
  readmeError.value = "";
  readmeEmpty.value = false;
  renderedReadme.value = "";

  if (isMarketDetail.value) {
    const readmeUrl = getDocumentUrl("readme_url");
    if (!readmeUrl) {
      readmeEmpty.value = true;
      readmeLoading.value = false;
      return;
    }

    try {
      const content = await fetchRemoteMarkdown(readmeUrl);
      if (!content.trim()) {
        readmeEmpty.value = true;
        return;
      }
      renderedReadme.value = renderMarkdown(content);
    } catch (err) {
      readmeError.value = err?.message || String(err);
    } finally {
      readmeLoading.value = false;
    }
    return;
  }

  const inlineReadme =
    plugin.readme ||
    plugin.README ||
    plugin.readme_content ||
    plugin.docs ||
    props.marketPlugin?.readme ||
    props.marketPlugin?.README ||
    props.marketPlugin?.readme_content ||
    props.marketPlugin?.docs ||
    "";

  if (inlineReadme) {
    renderedReadme.value = renderMarkdown(inlineReadme);
    readmeLoading.value = false;
    return;
  }

  try {
    const res = await axios.get("/api/plugin/readme", {
      params: { name: plugin.name },
    });

    if (res.data.status !== "ok") {
      readmeError.value = res.data.message || tm("messages.operationFailed");
      return;
    }

    const content = res.data.data?.content || "";
    if (!content) {
      readmeEmpty.value = true;
      return;
    }

    renderedReadme.value = renderMarkdown(content);
  } catch (err) {
    readmeError.value = err?.message || String(err);
  } finally {
    readmeLoading.value = false;
  }
};

const fetchChangelog = async () => {
  const plugin = pluginData.value || {};
  if (!plugin?.name) return;

  changelogLoading.value = true;
  changelogError.value = "";
  changelogEmpty.value = false;
  renderedChangelog.value = "";

  if (isMarketDetail.value) {
    const changelogUrl = getDocumentUrl("changelog_url");
    if (!changelogUrl) {
      changelogEmpty.value = true;
      changelogLoading.value = false;
      return;
    }

    try {
      const content = await fetchRemoteMarkdown(changelogUrl);
      if (!content.trim()) {
        changelogEmpty.value = true;
        return;
      }
      renderedChangelog.value = renderMarkdown(content);
    } catch (err) {
      changelogError.value = err?.message || String(err);
    } finally {
      changelogLoading.value = false;
    }
    return;
  }

  try {
    const res = await axios.get("/api/plugin/changelog", {
      params: { name: plugin.name },
    });

    if (res.data.status !== "ok") {
      changelogError.value =
        res.data.message || tm("messages.operationFailed");
      return;
    }

    const content = res.data.data?.content || "";
    if (!content) {
      changelogEmpty.value = true;
      return;
    }

    renderedChangelog.value = renderMarkdown(content);
  } catch (err) {
    changelogError.value = err?.message || String(err);
  } finally {
    changelogLoading.value = false;
  }
};

const showDocsSection = computed(
  () => !isMarketDetail.value || !!getDocumentUrl("readme_url"),
);

const showChangelogSection = computed(
  () => !isMarketDetail.value || !!getDocumentUrl("changelog_url"),
);

watch(
  () => [
    props.plugin?.name,
    props.sourceTab,
    props.marketPlugin?.readme_url,
    props.marketPlugin?.changelog_url,
  ],
  async () => {
    logoLoadFailed.value = false;
    await fetchPluginDetail();
    fetchReadme();
    fetchChangelog();
    scrollToHashTarget();
  },
  { immediate: true },
);

onMounted(() => {
  updateHeaderStuckState();
  scrollToHashTarget();
  window.addEventListener("scroll", updateHeaderStuckState, { passive: true });
  document.addEventListener("scroll", updateHeaderStuckState, {
    capture: true,
    passive: true,
  });
});

onBeforeUnmount(() => {
  window.removeEventListener("scroll", updateHeaderStuckState);
  document.removeEventListener("scroll", updateHeaderStuckState, {
    capture: true,
  });
});
</script>

<template>
  <div ref="detailPageRef" class="plugin-detail-page">
    <div
      class="detail-header"
      :class="{ 'detail-header--stuck': isHeaderStuck }"
    >
      <h2 class="detail-title">
        <button class="detail-title__parent" type="button" @click="goBack">
          {{ detailParentTitle }}
        </button>
        <v-icon icon="mdi-chevron-right" size="24" class="mx-1" />
        <span class="detail-title__current">{{ displayName }}</span>
      </h2>
    </div>

    <v-card class="plugin-summary-card rounded-lg" variant="outlined">
      <v-card-text class="plugin-summary-card__body">
        <img
          :src="logoSrc"
          :alt="displayName"
          class="plugin-summary-card__icon"
          @error="logoLoadFailed = true"
        />
        <h1 class="plugin-summary-card__title">{{ displayName }}</h1>
        <p v-if="pluginDesc" class="plugin-summary-card__desc">
          {{ pluginDesc }}
        </p>
      </v-card-text>
    </v-card>

    <section
      v-if="groupedComponentSections.length"
      id="plugin-components"
      class="detail-section"
    >
      <h3 class="detail-section__title">{{ tm("detail.contents") }}</h3>
      <div class="handler-groups">
        <div
          v-for="group in groupedComponentSections"
          :key="group.key"
          class="handler-group"
        >
          <div class="handler-group__title">
            <v-icon :icon="group.icon" size="20" />
            {{ group.title }}
            <span class="handler-group__count">{{
              group.components.length
            }}</span>
          </div>
          <v-card class="rounded-lg handler-card" variant="outlined">
            <v-table
              v-if="group.key === 'command'"
              class="detail-info-table detail-handler-table"
            >
              <tbody>
                <tr
                  v-for="item in buildCommandComponentRows(group.components)"
                  :key="item.key"
                  :class="{
                    'command-row--group': item.kind === 'group',
                    'command-row--sub': item.kind === 'subCommand',
                  }"
                >
                  <td
                    class="detail-info-table__label detail-handler-table__name"
                  >
                    <div
                      class="command-cell"
                      :style="{ paddingLeft: `${item.depth * 18}px` }"
                    >
                      <v-btn
                        v-if="item.kind === 'group'"
                        icon
                        variant="text"
                        size="x-small"
                        class="command-cell__toggle"
                        @click="toggleCommandGroup(item.key)"
                      >
                        <v-icon size="18">
                          {{
                            isCommandGroupExpanded(item.key)
                              ? "mdi-chevron-down"
                              : "mdi-chevron-right"
                          }}
                        </v-icon>
                      </v-btn>
                      <span
                        v-else-if="item.kind === 'subCommand'"
                        class="command-cell__indent"
                      ></span>
                      <code
                        :class="{
                          'command-code--group': item.kind === 'group',
                          'command-code--sub': item.kind === 'subCommand',
                        }"
                      >
                        {{ item.displayCommand }}
                      </code>
                    </div>
                  </td>
                  <td>
                    <div class="handler-row__desc">
                      <template v-if="item.kind === 'group'">
                        <span>{{
                          getComponentDescription(item.component)
                        }}</span>
                        <span class="handler-row__timing">
                          {{
                            tm("detail.subCommandsCount", {
                              count: item.children.length,
                            })
                          }}
                        </span>
                      </template>
                      <template v-else>
                        {{ getComponentDescription(item.component) }}
                      </template>
                    </div>
                  </td>
                </tr>
              </tbody>
            </v-table>

            <v-table v-else class="detail-info-table detail-handler-table">
              <tbody>
                <tr
                  v-for="component in group.components"
                  :key="
                    component.handler_full_name ||
                    component.path ||
                    component.name ||
                    component.handler_name ||
                    component.cmd
                  "
                >
                  <td
                    class="detail-info-table__label detail-handler-table__name"
                  >
                    <div>
                      {{ getHandlerDisplayName(component, group.key) }}
                    </div>
                  </td>
                  <td>
                    <div class="handler-row__desc">
                      <span
                        v-if="
                          group.key === 'hook' && getHandlerTiming(component)
                        "
                        class="handler-row__timing"
                      >
                        {{ getHandlerTiming(component) }}
                      </span>
                      <span>{{ getComponentDescription(component) }}</span>
                      <v-btn
                        v-if="group.key === 'page'"
                        color="primary"
                        size="small"
                        variant="tonal"
                        prepend-icon="mdi-open-in-new"
                        class="ml-2"
                        @click="openComponentPage(component)"
                      >
                        {{ tm("buttons.openPage") }}
                      </v-btn>
                    </div>
                  </td>
                </tr>
              </tbody>
            </v-table>
          </v-card>
        </div>
      </div>
    </section>

    <section class="detail-section">
      <h3 class="detail-section__title">{{ tm("detail.info.title") }}</h3>
      <v-card class="rounded-lg" variant="outlined">
        <v-table class="detail-info-table">
          <tbody>
            <tr v-for="row in infoRows" :key="row.label">
              <td class="detail-info-table__label">{{ row.label }}</td>
              <td>
                <v-btn
                  v-if="row.action"
                  color="primary"
                  variant="text"
                  density="comfortable"
                  prepend-icon="mdi-book-open-page-variant"
                  @click="row.action"
                >
                  {{ row.actionText }}
                </v-btn>
                <div v-else-if="row.kind === 'tags'" class="detail-tags">
                  <v-chip
                    v-for="tag in row.value"
                    :key="tag"
                    :color="tag === 'danger' ? 'error' : 'primary'"
                    label
                    size="small"
                    variant="tonal"
                  >
                    {{ tag === "danger" ? tm("tags.danger") : tag }}
                  </v-chip>
                </div>
                <div v-else-if="row.kind === 'platforms'" class="detail-tags">
                  <PluginPlatformChip :platforms="row.value" />
                </div>
                <button
                  v-else-if="row.href"
                  class="detail-link"
                  type="button"
                  @click="openExternal(row.href)"
                >
                  <span>{{ row.value }}</span>
                  <v-icon icon="mdi-open-in-new" size="16" />
                </button>
                <span v-else>{{ row.value || tm("status.unknown") }}</span>
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-card>
    </section>

    <section v-if="showDocsSection" class="detail-section">
      <h3 class="detail-section__title">{{ tm("detail.docsTitle") }}</h3>
      <v-card class="rounded-lg docs-card" variant="outlined">
        <v-card-text>
          <div v-if="readmeLoading" class="docs-state">
            <v-progress-circular indeterminate color="primary" />
          </div>
          <v-alert v-else-if="readmeError" type="error" variant="tonal">
            {{ readmeError }}
          </v-alert>
          <div v-else-if="readmeEmpty" class="text-medium-emphasis">
            {{ tm("detail.docsEmpty") }}
          </div>
          <div v-else class="docs-markdown" v-html="renderedReadme"></div>
        </v-card-text>
      </v-card>
    </section>

    <section v-if="showChangelogSection" class="detail-section">
      <h3 class="detail-section__title">
        {{ tm("detail.changelogTitle") }}
      </h3>
      <v-card class="rounded-lg docs-card" variant="outlined">
        <v-card-text>
          <div v-if="changelogLoading" class="docs-state">
            <v-progress-circular indeterminate color="primary" />
          </div>
          <v-alert v-else-if="changelogError" type="error" variant="tonal">
            {{ changelogError }}
          </v-alert>
          <div v-else-if="changelogEmpty" class="text-medium-emphasis">
            {{ tm("detail.changelogEmpty") }}
          </div>
          <div v-else class="docs-markdown" v-html="renderedChangelog"></div>
        </v-card-text>
      </v-card>
    </section>
  </div>
</template>

<style scoped>
.plugin-detail-page {
  margin: 0 auto;
  max-width: 1040px;
  padding: 16px 24px 32px;
  width: 100%;
}

.detail-header {
  align-items: center;
  display: flex;
  gap: 8px;
  isolation: isolate;
  margin-bottom: 28px;
  padding: 10px 0;
  position: sticky;
  top: calc(var(--v-layout-top, 64px));
  z-index: 20;
}

.detail-header--stuck::before {
  background: rgb(var(--v-theme-surface));
  box-shadow: 0 1px 0 rgba(var(--v-border-color), var(--v-border-opacity));
  content: "";
  inset: 0 calc(50% - 50vw);
  position: absolute;
  z-index: -1;
}

.detail-title {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  font-size: 1.5rem;
  font-weight: 700;
  gap: 2px;
  letter-spacing: 0;
  margin: 0;
  min-width: 0;
}

.detail-title__parent {
  background: transparent;
  border: 0;
  color: inherit;
  cursor: pointer;
  font: inherit;
  padding: 0;
}

.detail-title__parent:hover {
  color: rgb(var(--v-theme-primary));
}

.detail-title__current {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plugin-summary-card {
  background: rgb(var(--v-theme-surface));
  color: rgba(var(--v-theme-on-surface), 0.9);
}

.plugin-summary-card__body {
  align-items: flex-start;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 24px;
}

.plugin-summary-card__icon {
  border-radius: 16px;
  height: 72px;
  object-fit: cover;
  width: 72px;
}

.plugin-summary-card__title {
  font-size: 1.75rem;
  font-weight: 700;
  letter-spacing: 0;
  line-height: 1.25;
  margin: 0;
}

.plugin-summary-card__desc {
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 0.9rem;
  line-height: 1.6;
  margin: 0;
  max-width: 760px;
}

.detail-section {
  margin-top: 28px;
}

.detail-section__title {
  font-size: 1.25rem;
  font-weight: 700;
  margin: 0 0 12px;
}

.handler-row__desc {
  align-items: baseline;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 0px;
  line-height: 1.5;
  font-size: 13px;
  overflow-wrap: anywhere;
}

.handler-row__timing {
  color: rgba(var(--v-theme-on-surface), 0.54);
  flex-shrink: 0;
  font-size: 0.85rem;
  font-weight: 600;
}

.handler-groups {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.handler-group__title {
  align-items: center;
  display: flex;
  font-size: 0.95rem;
  font-weight: 700;
  gap: 8px;
  margin-bottom: 8px;
}

.handler-group__count {
  color: rgba(var(--v-theme-on-surface), 0.48);
  font-size: 0.85rem;
  font-weight: 600;
}

.handler-card,
.handler-card :deep(.v-table),
.handler-card :deep(tbody),
.handler-card :deep(tr),
.handler-card :deep(td) {
  background: rgb(var(--v-theme-surface));
}

.detail-info-table__label {
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-weight: 600;
  width: 200px;
}

.detail-handler-table :deep(table) {
  table-layout: fixed;
}

.detail-handler-table__name {
  width: 220px;
}

.detail-handler-table__name div {
  color: rgba(var(--v-theme-on-surface), 0.72);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.command-cell {
  align-items: center;
  display: flex;
  min-width: 0;
}

.command-cell__toggle {
  flex-shrink: 0;
  margin-right: 4px;
}

.command-cell__indent {
  flex-shrink: 0;
  margin-left: 28px;
}

.command-cell code {
  background-color: rgba(var(--v-theme-primary), 0.1);
  border-radius: 4px;
  font-size: 0.9em;
  overflow: hidden;
  padding: 2px 6px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.command-cell code.command-code--group {
  background-color: rgba(var(--v-theme-info), 0.12);
}

.command-cell code.command-code--sub {
  background-color: rgba(var(--v-theme-secondary), 0.1);
  color: rgb(var(--v-theme-secondary));
}

.detail-link {
  align-items: center;
  color: rgb(var(--v-theme-primary));
  display: inline-flex;
  gap: 6px;
  max-width: 100%;
}

.detail-link span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.docs-card {
  background: rgb(var(--v-theme-surface));
  color: rgba(var(--v-theme-on-surface), 0.9);
}

.docs-state {
  align-items: center;
  display: flex;
  justify-content: center;
  min-height: 160px;
}

.docs-markdown {
  color: rgba(var(--v-theme-on-surface), 0.9);
  font-size: 0.95rem;
  line-height: 1.65;
}

.docs-markdown :deep(h1),
.docs-markdown :deep(h2),
.docs-markdown :deep(h3),
.docs-markdown :deep(h4),
.docs-markdown :deep(h5),
.docs-markdown :deep(h6) {
  color: rgba(var(--v-theme-on-surface), 0.9);
  font-weight: 700;
  line-height: 1.3;
  margin: 1.4em 0 0.6em;
}

.docs-markdown :deep(h1:first-child),
.docs-markdown :deep(h2:first-child),
.docs-markdown :deep(h3:first-child) {
  margin-top: 0;
}

.docs-markdown :deep(p),
.docs-markdown :deep(ul),
.docs-markdown :deep(ol),
.docs-markdown :deep(blockquote),
.docs-markdown :deep(pre),
.docs-markdown :deep(table) {
  margin-bottom: 1em;
}

.docs-markdown :deep(ul),
.docs-markdown :deep(ol) {
  list-style-position: inside;
  padding-left: 0;
}

.docs-markdown :deep(li) {
  margin: 0.25em 0;
}

.docs-markdown :deep(a) {
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
}

.docs-markdown :deep(a:hover) {
  text-decoration: underline;
}

.docs-markdown :deep(pre) {
  background: rgba(var(--v-theme-on-surface), 0.06);
  border-radius: 8px;
  overflow-x: auto;
  padding: 12px;
}

.docs-markdown :deep(code) {
  background: rgba(var(--v-theme-on-surface), 0.06);
  border-radius: 4px;
  font-size: 0.9em;
  padding: 0.15em 0.35em;
}

.docs-markdown :deep(pre code) {
  background: transparent;
  padding: 0;
}

.docs-markdown :deep(blockquote) {
  border-left: 4px solid rgba(var(--v-border-color), var(--v-border-opacity));
  color: rgba(var(--v-theme-on-surface), 0.62);
  padding-left: 12px;
}

.docs-markdown :deep(img) {
  max-width: 100%;
}

.docs-markdown :deep(table) {
  border-collapse: collapse;
  display: block;
  overflow-x: auto;
  width: 100%;
}

.docs-markdown :deep(th),
.docs-markdown :deep(td) {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding: 6px 10px;
}

.docs-markdown :deep(th) {
  background: rgba(var(--v-theme-on-surface), 0.06);
}

@media (max-width: 700px) {
  .plugin-detail-page {
    padding-left: 16px;
    padding-right: 16px;
  }

  .detail-info-table__label {
    width: 120px;
  }

  .detail-handler-table__name {
    width: 140px;
  }
}
</style>
