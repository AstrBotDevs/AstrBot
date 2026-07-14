// Author: spcode-assistant
// Date: 2026-07-11
//
// Component spec for InteractiveChoiceBox — v1.2 ignores-state title fix.
//
// Background: the v1.0 `is-ignored` header only rendered the
// "已忽略" label + `part.prompt` (muted), deliberately skipping
// `part.title`. This was a regression — the user lost the original
// choice-box subject when a later user message passed it over. v1.2
// adds a `part.title` span (with full-text :title tooltip) to the
// ignored header so the skipped box's topic stays visible.
//
// These tests pin:
//   1. ignored + title  → both title and prompt spans render with :title
//   2. ignored + no title → only prompt span renders (no empty span)
//   3. pending baseline  → the pre-existing title/prompt path still works

import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import type { InteractiveChoicePart } from "@/composables/parseInteractiveChoice";

// Mock the Pinia store: the only method InteractiveChoiceBox touches
// at render time is `getSubmissionState`, and for these tests we want
// it to return null (i.e. "this part has no submission yet"). Pulling
// in the real store would also require createPinia() + happy-dom
// localStorage and trigger unwanted hydrate side effects.
vi.mock("@/stores/interactiveChoice", () => ({
  useInteractiveChoiceStore: () => ({
    getSubmissionState: () => null,
    markSubmitted: vi.fn(),
  }),
}));

// i18n init happens in vitest.setup.ts; useModuleI18n('features/chat')
// reads real zh-CN strings, so the "已忽略" label and the
// "已选择/已输入" submitted labels render real text.

// Import AFTER vi.mock so the mocked store is in place.
import InteractiveChoiceBox from "./InteractiveChoiceBox.vue";

const UMO = "webchat:test!umo";

function makePart(
  overrides: Partial<InteractiveChoicePart> = {},
): InteractiveChoicePart {
  return {
    type: "interactive_choice",
    request_id: "req-1",
    prompt: "请选择重命名方式",
    options: [
      { id: "A", label: "git mv", description: "保留历史" },
      { id: "B", label: "文件系统 mv", description: "可能丢历史" },
    ],
    ...overrides,
  };
}

function mountBox(props: { part: InteractiveChoicePart; isIgnored?: boolean }) {
  return mount(InteractiveChoiceBox, {
    props: {
      umo: UMO,
      ...props,
    },
    // pending 分支里有 v-btn(自由输入的提交按钮)。本 spec 只在
    // ignored / pending 状态断言,无需 v-btn 真行为;给个 stub
    // 避免 Vue 控制台抛 "Failed to resolve component: v-btn" 警告。
    global: {
      stubs: {
        "v-btn": { template: "<button><slot /></button>" },
      },
    },
  });
}

describe("InteractiveChoiceBox — ignored header (v1.2)", () => {
  it("renders both title and prompt spans when both are present", () => {
    const wrapper = mountBox({
      part: makePart({
        title: "重命名 PATCH 文件",
        prompt: "用 git mv 还是文件系统 mv?",
      }),
      isIgnored: true,
    });

    const header = wrapper.find(".choice-header--ignored");
    expect(header.exists()).toBe(true);

    // title 节点存在并显示原文
    const title = header.find(".choice-title--ignored");
    expect(title.exists()).toBe(true);
    expect(title.text()).toBe("重命名 PATCH 文件");
    // v1.2:title 节点的 :title 属性绑了原文,hover 可看全量
    expect(title.attributes("title")).toBe("重命名 PATCH 文件");

    // prompt 节点也存在并显示原文
    const prompt = header.find(".choice-prompt--muted");
    expect(prompt.exists()).toBe(true);
    expect(prompt.text()).toBe("用 git mv 还是文件系统 mv?");
    expect(prompt.attributes("title")).toBe("用 git mv 还是文件系统 mv?");

    // 上下文标签 "已忽略" 仍存在(回归保护:v1.2 改的是 ignored header
    // 内部,不该影响外部的"已忽略"标签)
    expect(header.find(".choice-ignored-label").exists()).toBe(true);
  });

  it("does not render a title span when part.title is missing", () => {
    // v1.2 的修复要保持向后兼容:旧 plugin 可能不传 title(v0.3
    // wire-format 是必填 title 的,但 v1.0 改成了可选),此时不能
    // 凭空渲染一个空 span,会让 header 多一个 0 高度节点。
    const wrapper = mountBox({
      part: makePart({ title: undefined, prompt: "仅 prompt" }),
      isIgnored: true,
    });

    const header = wrapper.find(".choice-header--ignored");
    expect(header.exists()).toBe(true);
    // 没有 title 字段 → .choice-title--ignored 节点整体不渲染
    expect(header.find(".choice-title--ignored").exists()).toBe(false);

    // prompt 节点仍然渲染
    const prompt = header.find(".choice-prompt--muted");
    expect(prompt.exists()).toBe(true);
    expect(prompt.text()).toBe("仅 prompt");
  });

  it("does not render the ignored header when isIgnored is false", () => {
    // 烟雾测试:没 isIgnored → 走 pending/submitted 分支,不会
    // 出现 .choice-header--ignored 节点。
    const wrapper = mountBox({
      part: makePart({ title: "未忽略的 title" }),
      isIgnored: false,
    });
    expect(wrapper.find(".choice-header--ignored").exists()).toBe(false);
  });
});
