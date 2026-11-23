import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import { VTextField } from "vuetify/components";
import { initI18n, useI18n } from "../src/i18n/composables.ts";

const api = vi.hoisted(() => ({
  cron: { list: vi.fn() },
  bot: { stats: vi.fn() },
  session: { activeUmos: vi.fn() },
  conversation: { filterOptions: vi.fn() },
}));

vi.mock("@/api/v1", () => ({
  cronApi: api.cron,
  botApi: api.bot,
  sessionApi: api.session,
  conversationApi: api.conversation,
}));

import DailyQuote from "../src/components/shared/DailyQuote.vue";
import CronJobPage from "../src/views/CronJobPage.vue";

const ok = (data) => ({ data: { status: "ok", data } });
const taskNames = (wrapper) =>
  wrapper
    .findAll(".task-list .outlined-action-list-item__title")
    .map((row) => row.text())
    .sort();

describe("Cron search with the installed Vuetify text field", () => {
  beforeEach(async () => {
    api.cron.list.mockResolvedValue(
      ok([
        { job_id: "alpha", name: "Alpha task", note: "First delivery", enabled: true, session: "bot:GroupMessage:a" },
        { job_id: "beta", name: "Beta task", note: "Local task", enabled: true, session: "" },
        {
          job_id: "gamma",
          name: "Gamma task",
          note: "ALPHA in the note",
          enabled: true,
          session: "bot:GroupMessage:b",
        },
        { job_id: "delta", name: "Delta task", note: "Another local task", enabled: true, session: "" },
      ]),
    );
    api.bot.stats.mockResolvedValue(ok({ platforms: [] }));
    api.session.activeUmos.mockResolvedValue(ok({ umos: [], umo_infos: [] }));
    api.conversation.filterOptions.mockResolvedValue(ok({ bots: [] }));
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe = vi.fn();
        unobserve = vi.fn();
        disconnect = vi.fn();
      },
    );
    vi.stubGlobal("visualViewport", {
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      width: 1024,
      height: 768,
      offsetTop: 0,
      offsetLeft: 0,
      pageTop: 0,
      pageLeft: 0,
      scale: 1,
    });
    await initI18n("en-US");
  });

  async function mountCron() {
    const renderError = vi.fn();
    const wrapper = mount(CronJobPage, {
      attachTo: document.body,
      global: {
        plugins: [createPinia(), createVuetify({ components })],
        config: { errorHandler: renderError },
      },
    });
    await flushPromises();
    expect(renderError).not.toHaveBeenCalled();
    const search = wrapper.findAllComponents(VTextField).find((field) => field.props("clearable"));
    expect(search).toBeDefined();
    return { wrapper, search, renderError };
  }

  async function clickSearchClear(search, renderError) {
    await search.find(".v-field__clearable .v-icon").trigger("click");
    await flushPromises();
    expect(search.emitted("update:modelValue").at(-1)).toEqual([null]);
    expect(renderError).not.toHaveBeenCalled();
    expect(search.find("input").element.value).toBe("");
  }

  test("clearing the real field restores rows and allows another case-insensitive search", async () => {
    const { wrapper, search, renderError } = await mountCron();
    expect(taskNames(wrapper)).toEqual(["Alpha task", "Beta task", "Delta task", "Gamma task"]);

    await search.find("input").setValue("  aLpHa  ");
    expect(taskNames(wrapper)).toEqual(["Alpha task", "Gamma task"]);

    await clickSearchClear(search, renderError);
    expect(taskNames(wrapper)).toEqual(["Alpha task", "Beta task", "Delta task", "Gamma task"]);

    await search.find("input").setValue(" GAMMA ");
    expect(taskNames(wrapper)).toEqual(["Gamma task"]);
  });

  test("clearing the search preserves the active no-delivery-target filter", async () => {
    const { wrapper, search, renderError } = await mountCron();
    const noDeliveryTarget = wrapper.find('.task-filter-bar input[type="checkbox"]');
    await noDeliveryTarget.setValue(true);
    expect(taskNames(wrapper)).toEqual(["Beta task", "Delta task"]);

    await search.find("input").setValue(" beta ");
    expect(taskNames(wrapper)).toEqual(["Beta task"]);

    await clickSearchClear(search, renderError);
    expect(noDeliveryTarget.element.checked).toBe(true);
    expect(taskNames(wrapper)).toEqual(["Beta task", "Delta task"]);
  });
});

describe("DailyQuote locale retention", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 0, 2, 12));
  });

  test.each([
    [2, "まず動かし、次に正しくし、そして速くする。", "Kent Beck"],
    [3, "単純さは効率の魂である。", "Austin Freeman"],
  ])("Japanese day %i renders the original quote and author", async (day, text, author) => {
    vi.setSystemTime(new Date(2026, 0, day, 12));
    await initI18n("ja-JP");
    const wrapper = mount(DailyQuote);
    expect(wrapper.find(".quote-text").text()).toBe(`"${text}"`);
    expect(wrapper.find(".quote-author").text()).toBe(`— ${author}`);
  });

  test.each([
    ["en-US", "First, solve the problem. Then, write the code.", "John Johnson"],
    ["zh-CN", "先解决问题，再写代码。", "约翰·约翰逊"],
    ["ru-RU", "Сначала реши проблему. Потом пиши код.", "Джон Джонсон"],
    ["unknown-locale", "First, solve the problem. Then, write the code.", "John Johnson"],
  ])("%s preserves its existing quote or English fallback", async (locale, text, author) => {
    await initI18n(locale);
    const wrapper = mount(DailyQuote);
    expect(wrapper.find(".quote-text").text()).toBe(`"${text}"`);
    expect(wrapper.find(".quote-author").text()).toBe(`— ${author}`);
  });

  test("changing the current locale updates an already mounted login quote", async () => {
    await initI18n("en-US");
    const wrapper = mount(DailyQuote);
    expect(wrapper.find(".quote-author").text()).toBe("— John Johnson");

    await useI18n().setLocale("ja-JP");
    await flushPromises();
    expect(wrapper.find(".quote-text").text()).toBe('"まず動かし、次に正しくし、そして速くする。"');
    expect(wrapper.find(".quote-author").text()).toBe("— Kent Beck");
  });
});
