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

import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import type { InteractiveChoicePart } from "@/composables/parseInteractiveChoice";

// Stateful mock of the Pinia store. Mirrors the real
// `useInteractiveChoiceStore` surface that InteractiveChoiceBox
// reads (getSubmissionState / isCancelled) and writes (markSubmitted
// / markCancelled) during render. Backed by internal Maps so the
// "submission wins over cancelled" race test can sequence
// markSubmitted then markCancelled against the same UMO + rid and
// observe the priority at the rendered class binding.
//
// Why stateful instead of vi.fn().mockReturnValue(): a fresh
// per-test spy is annoying to reset (`mockReturnValue` between
// `beforeEach` blocks has surprising behaviour with reactive reads)
// and the existing tests need the same "no submission by default"
// behaviour, which a Map-backed `?? null` fallback gives for free.
const storeMock = vi.hoisted(() => {
  type Submission = {
    kind: "option" | "input";
    optionId?: string;
    freeText?: string;
  };
  const submissions = new Map<string, Submission>();
  const cancelled = new Map<string, boolean>();
  return {
    getSubmissionState(umo: string, rid: string): Submission | null {
      return submissions.get(`${umo}::${rid}`) ?? null;
    },
    markSubmitted(
      umo: string,
      rid: string,
      kind: Submission["kind"],
      payload: { optionId?: string; freeText?: string } = {},
    ): void {
      submissions.set(`${umo}::${rid}`, { kind, ...payload });
    },
    isCancelled(umo: string, rid: string): boolean {
      return cancelled.get(`${umo}::${rid}`) ?? false;
    },
    markCancelled(umo: string, rid: string): void {
      cancelled.set(`${umo}::${rid}`, true);
    },
    _reset(): void {
      submissions.clear();
      cancelled.clear();
    },
  };
});

vi.mock("@/stores/interactiveChoice", () => ({
  useInteractiveChoiceStore: () => storeMock,
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

function mountBox(props: {
  part: InteractiveChoicePart;
  isIgnored?: boolean;
  umo?: string;
}) {
  const { part, isIgnored, umo } = props;
  return mount(InteractiveChoiceBox, {
    props: {
      umo: umo ?? UMO,
      part,
      isIgnored,
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

beforeEach(() => {
  storeMock._reset();
});

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

// ---------------------------------------------------------------------------
// Task F4: fifth box state `cancelled` (v1.2 spec §4.4 + §5.1).
//
// State priority binding (spec §5.1):
//   submissionState  >  cancelledState  >  props.isIgnored  >  pending
//
// Why submission wins over cancelled: race safety. If the user
// clicks an option at T=timeout−1, the local submission intent is
// honest (UI shows "已选择 X"). The server's cancellation arrives
// a frame later (or after a network outage). The UI must NOT lie
// about what the user chose — flipping to "已取消" would discard
// the user's click.
//
// These 5 tests pin:
//   1. baseline →  is-pending class (no state overrides)
//   2. cancelled only →  is-cancelled class
//   3. submission wins over cancelled (race safety)
//   4. cancelled template branch renders the icon + i18n label
//      and does NOT render the pending option buttons / input
//   5. pending template branch does NOT render the cancelled UI
// ---------------------------------------------------------------------------

describe("InteractiveChoiceBox — cancelled state (v1.2)", () => {
  it("applies is-pending class when no state overrides", () => {
    const wrapper = mountBox({
      part: makePart({ title: "未提交的 title" }),
    });
    expect(wrapper.find(".interactive-choice-box.is-pending").exists()).toBe(
      true,
    );
    expect(wrapper.find(".interactive-choice-box.is-cancelled").exists()).toBe(
      false,
    );
    expect(wrapper.find(".interactive-choice-box.is-submitted").exists()).toBe(
      false,
    );
  });

  it("applies is-cancelled class when cancelledStates[umo][rid] is true", () => {
    const umo = "webchat:FriendMessage:webchat!alice!sess";
    storeMock.markCancelled(umo, "req-1");

    const wrapper = mountBox({
      part: makePart({ title: "已取消的 title" }),
      umo,
    });
    expect(wrapper.find(".interactive-choice-box.is-cancelled").exists()).toBe(
      true,
    );
    expect(wrapper.find(".interactive-choice-box.is-pending").exists()).toBe(
      false,
    );
    expect(wrapper.find(".interactive-choice-box.is-submitted").exists()).toBe(
      false,
    );
  });

  it("submission wins over cancelled (race safety: T=timeout-1)", () => {
    const umo = "webchat:FriendMessage:webchat!alice!sess";
    // Simulate: user clicked option A at T=timeout-1, then the
    // server's `interactive_choice_resolved {reason: "cancelled"}`
    // event arrives. Per spec §5.1, the UI must keep showing the
    // user's submitted choice (UI honesty over server truth).
    storeMock.markSubmitted(umo, "req-1", "option", { optionId: "A" });
    storeMock.markCancelled(umo, "req-1");

    const wrapper = mountBox({
      part: makePart({ title: "已选择 A" }),
      umo,
    });
    expect(wrapper.find(".interactive-choice-box.is-submitted").exists()).toBe(
      true,
    );
    expect(wrapper.find(".interactive-choice-box.is-cancelled").exists()).toBe(
      false,
    );
  });

  it("renders cancelled header (icon + i18n label) when state is 'cancelled'", () => {
    const umo = "webchat:FriendMessage:webchat!alice!sess";
    storeMock.markCancelled(umo, "req-1");

    const wrapper = mountBox({
      part: makePart({ title: "超时未回" }),
      umo,
    });
    // New v1.2 contract: `.choice-header--cancelled` + i18n label
    expect(wrapper.find(".choice-header--cancelled").exists()).toBe(true);
    expect(wrapper.find(".choice-cancelled-label").exists()).toBe(true);
    // Cancelled boxes are non-interactive → pending UI must NOT render
    expect(wrapper.find(".choice-options").exists()).toBe(false);
    expect(wrapper.find(".choice-input-row").exists()).toBe(false);
  });

  it("does NOT render the cancelled UI when state is 'pending'", () => {
    const wrapper = mountBox({
      part: makePart({ title: "待回答" }),
    });
    expect(wrapper.find(".choice-header--cancelled").exists()).toBe(false);
    expect(wrapper.find(".choice-cancelled-label").exists()).toBe(false);
  });
});
