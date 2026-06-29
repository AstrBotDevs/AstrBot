// Author: elecvoid243
// Date: 2026-06-28
// Spec: docs/superpowers/specs/2026-06-28-dynamic-choice-box-rendering-design.md §2.3 / §3.2 / §7
//
// 测试 parseInteractiveChoice.ts 的纯函数:解包(unwrap) + 校验(validate) + 截断(truncate)
// + 提取(extractAskUserChoiceFromToolCall)。
// 覆盖 spec §3.2 字段约束、§7 错误处理、tool_call 拆解。
import assert from "node:assert/strict";
import test from "node:test";

import {
  extractAskUserChoiceFromToolCall,
  isInteractiveChoicePayload,
  unwrapInteractiveChoice,
  validateInteractiveChoice,
  truncateInteractiveChoice,
} from "../src/composables/parseInteractiveChoice.ts";

// ─── 公共 fixture ─────────────────────────────────────────────
const validOption = { id: "a", label: "GPT-4", description: "更强但更慢", value: "gpt-4" };
const validPart = {
  type: "interactive_choice",
  prompt: "请选择下一步使用的模型:",
  options: [validOption, { id: "b", label: "GPT-4 mini", value: "gpt-4-mini" }],
};

// ─── isInteractiveChoicePayload ──────────────────────────────
test("isInteractiveChoicePayload: 合法 InteractiveChoicePart 返回 true", () => {
  assert.equal(isInteractiveChoicePayload(validPart), true);
});

test("isInteractiveChoicePayload: 缺 type 字段返回 false", () => {
  assert.equal(isInteractiveChoicePayload({ prompt: "x", options: [validOption] }), false);
});

test("isInteractiveChoicePayload: type 不是 interactive_choice 返回 false", () => {
  assert.equal(isInteractiveChoicePayload({ type: "plain", text: "hi" }), false);
  assert.equal(isInteractiveChoicePayload({ type: "tool_call" }), false);
});

test("isInteractiveChoicePayload: 非对象(null / string / array)返回 false", () => {
  assert.equal(isInteractiveChoicePayload(null), false);
  assert.equal(isInteractiveChoicePayload("string"), false);
  assert.equal(isInteractiveChoicePayload([1, 2]), false);
});

// ─── unwrapInteractiveChoice ──────────────────────────────────
test("unwrapInteractiveChoice: plain + JSON 字符串前缀 { 解包为 InteractiveChoicePart", () => {
  const part = { type: "plain", text: JSON.stringify(validPart) };
  const result = unwrapInteractiveChoice(part);
  assert.deepEqual(result, validPart);
});

test("unwrapInteractiveChoice: 原生 interactive_choice part 透传", () => {
  const result = unwrapInteractiveChoice(validPart);
  assert.deepEqual(result, validPart);
});

test("unwrapInteractiveChoice: 普通 plain 文本不改动", () => {
  const part = { type: "plain", text: "hello world" };
  assert.deepEqual(unwrapInteractiveChoice(part), part);
});

test("unwrapInteractiveChoice: plain 但 JSON.parse 失败保留原 part(见 spec §7)", () => {
  const part = { type: "plain", text: '{ "type": "interactive_choice", "broken' };
  assert.deepEqual(unwrapInteractiveChoice(part), part);
});

test("unwrapInteractiveChoice: plain 但解析后 type 不是 interactive_choice 保留原 part", () => {
  const part = { type: "plain", text: '{"type":"other","foo":1}' };
  assert.deepEqual(unwrapInteractiveChoice(part), part);
});

test("unwrapInteractiveChoice: plain 但 text 不以 { 开头保留原 part", () => {
  const part = { type: "plain", text: "not json" };
  assert.deepEqual(unwrapInteractiveChoice(part), part);
});

test("unwrapInteractiveChoice: 非 plain / 非 interactive_choice 原样返回(图片等不重写)", () => {
  const imagePart = { type: "image", url: "http://x" };
  assert.deepEqual(unwrapInteractiveChoice(imagePart), imagePart);
});

// ─── validateInteractiveChoice ────────────────────────────────
test("validateInteractiveChoice: 合法 part 返回 true", () => {
  assert.equal(validateInteractiveChoice(validPart), true);
});

test("validateInteractiveChoice: 缺 prompt 返回 false", () => {
  assert.equal(validateInteractiveChoice({ type: "interactive_choice", options: [validOption] }), false);
});

test("validateInteractiveChoice: prompt 为空字符串返回 false", () => {
  assert.equal(validateInteractiveChoice({ type: "interactive_choice", prompt: "", options: [validOption] }), false);
});

test("validateInteractiveChoice: 缺 options 返回 false", () => {
  assert.equal(validateInteractiveChoice({ type: "interactive_choice", prompt: "x" }), false);
});

test("validateInteractiveChoice: options 只有一个元素返回 false(spec §3.2 至少 2 个)", () => {
  assert.equal(
    validateInteractiveChoice({ type: "interactive_choice", prompt: "x", options: [validOption] }),
    false,
  );
});

test("validateInteractiveChoice: options 元素缺 id 返回 false", () => {
  const bad = { type: "interactive_choice", prompt: "x", options: [{ label: "x", value: "y" }] };
  assert.equal(validateInteractiveChoice(bad), false);
});

test("validateInteractiveChoice: options 元素缺 label 返回 false", () => {
  const bad = { type: "interactive_choice", prompt: "x", options: [{ id: "a", value: "y" }] };
  assert.equal(validateInteractiveChoice(bad), false);
});

test("validateInteractiveChoice: options 元素缺 value 返回 false", () => {
  const bad = { type: "interactive_choice", prompt: "x", options: [{ id: "a", label: "y" }] };
  assert.equal(validateInteractiveChoice(bad), false);
});

test("validateInteractiveChoice: id 重复返回 false(spec §3.2)", () => {
  const bad = {
    type: "interactive_choice",
    prompt: "x",
    options: [
      { id: "a", label: "A", value: "1" },
      { id: "a", label: "B", value: "2" },
    ],
  };
  assert.equal(validateInteractiveChoice(bad), false);
});

test("validateInteractiveChoice: id 为空字符串返回 false", () => {
  const bad = {
    type: "interactive_choice",
    prompt: "x",
    options: [
      { id: "", label: "A", value: "1" },
      { id: "b", label: "B", value: "2" },
    ],
  };
  assert.equal(validateInteractiveChoice(bad), false);
});

// ─── truncateInteractiveChoice ───────────────────────────────
test("truncateInteractiveChoice: prompt 超 200 字截断", () => {
  const long = "a".repeat(300);
  const result = truncateInteractiveChoice({ type: "interactive_choice", prompt: long, options: [validOption] });
  assert.equal(result.prompt.length, 200);
});

test("truncateInteractiveChoice: title 超 30 字截断", () => {
  const result = truncateInteractiveChoice({ ...validPart, title: "a".repeat(50) });
  assert.equal(result.title.length, 30);
});

test("truncateInteractiveChoice: option.label 超 30 字截断", () => {
  const opt = { ...validOption, label: "a".repeat(60) };
  const result = truncateInteractiveChoice({ ...validPart, options: [opt] });
  assert.equal(result.options[0].label.length, 30);
});

test("truncateInteractiveChoice: option.description 超 200 字截断", () => {
  const opt = { ...validOption, description: "a".repeat(300) };
  const result = truncateInteractiveChoice({ ...validPart, options: [opt] });
  assert.equal(result.options[0].description.length, 200);
});

test("truncateInteractiveChoice: input_placeholder 超 60 字截断", () => {
  const result = truncateInteractiveChoice({ ...validPart, input_placeholder: "a".repeat(100) });
  assert.equal(result.input_placeholder.length, 60);
});

test("truncateInteractiveChoice: value 不截断", () => {
  const longValue = "a".repeat(1000);
  const result = truncateInteractiveChoice({
    ...validPart,
    options: [{ ...validOption, value: longValue }],
  });
  assert.equal(result.options[0].value.length, 1000);
});

test("truncateInteractiveChoice: 短字段不动", () => {
  const result = truncateInteractiveChoice(validPart);
  assert.equal(result, validPart);  // 不可变:如果未截断,返回原对象
});

// ════════════════════════════════════════════════════════════════
// 端到端: 真实插件输出 → dashboard pipeline
// ════════════════════════════════════════════════════════════════
//
// 模拟 astrbot_plugin_ask_user/ask_user_choice_tool.py 真实输出。
// 关键 case:
// 1. 工具返回的 JSON 字符串(被 framework 包成 Plain {type:"text",data:{text:<json>}},
//    dashboard 转为 {type:"plain",text:<json>}) → 完整端到端 unwrap+validate+truncate 链
// 2. 真实插件的 description=null(LLM 不传或传 None 时,(x or "")[:200] or None → null)
// 3. 真实插件的软错误("错误:..." 不以 { 开头 → 保持原 plain,不重写)

// ─── 真实插件输出 fixture ───────────────────────────────────
function simulateAskUserChoiceTool(prompt, options, title, input_placeholder) {
  // 镜像 ask_user_choice_tool.py:188-200 的拼装逻辑
  const payload = { type: "interactive_choice", prompt, options };
  if (title) payload.title = title;
  if (input_placeholder) payload.input_placeholder = input_placeholder;
  return JSON.stringify(payload, null, 0);  // 模拟 ensure_ascii=False 的紧凑形式
}

test("E2E 真实插件输出: 完整选项 + description=null 的 JSON 字符串", () => {
  // 镜像 ask_user_choice_tool.py:160-177:description 为 null 时 (opt.get('description') or '')[:200] or None → null
  const pluginJson = JSON.stringify({
    type: "interactive_choice",
    prompt: "请选择模型:",
    options: [
      { id: "a", label: "GPT-4", description: null, value: "gpt-4" },
      { id: "b", label: "GPT-4 mini", value: "gpt-4-mini" },
    ],
  });

  // framework 包成 Plain → dashboard 转为 MessagePart
  const plainPart = { type: "plain", text: pluginJson };

  // 完整 pipeline
  const unwrapped = unwrapInteractiveChoice(plainPart);
  assert.equal(unwrapInteractiveChoice.name === "unwrapInteractiveChoice" || typeof unwrapped === "object", true);
  assert.equal(isInteractiveChoicePayload(unwrapped), true);
  assert.equal(validateInteractiveChoice(unwrapped), true);
  const truncated = truncateInteractiveChoice(unwrapped);
  assert.equal(truncated.type, "interactive_choice");
  assert.equal(truncated.prompt, "请选择模型:");
  assert.equal(truncated.options.length, 2);
  // description=null 保留为 null(v-if 会隐藏该 <span>)
  assert.equal(truncated.options[0].description, null);
  assert.equal(truncated.options[1].description, undefined);  // 缺省字段不出现
});

test("E2E 真实插件输出: title + input_placeholder + 全描述", () => {
  const pluginJson = simulateAskUserChoiceTool(
    "选择操作",
    [
      { id: "del", label: "删除文件", description: "不可逆", value: "delete" },
      { id: "cancel", label: "取消", value: "cancel" },
    ],
    "操作确认",
    "或输入自定义操作",
  );
  const plainPart = { type: "plain", text: pluginJson };
  const unwrapped = unwrapInteractiveChoice(plainPart);
  const result = truncateInteractiveChoice(unwrapped);

  assert.equal(result.title, "操作确认");
  assert.equal(result.input_placeholder, "或输入自定义操作");
  assert.equal(result.options[0].description, "不可逆");
});

test("E2E 真实插件软错误: '错误:...' 不以 { 开头,保留原 plain", () => {
  // ask_user_choice_tool.py:108 返回 "错误:prompt 必填且不能为空。"
  const errPart = { type: "plain", text: "错误:prompt 必填且不能为空。" };
  const result = unwrapInteractiveChoice(errPart);
  // 错误不是 JSON,不重写
  assert.deepEqual(result, errPart);
  // validate 也不动它
  assert.equal(validateInteractiveChoice(result), false);
});

test("E2E 真实插件超长 prompt: 工具层已截到 200,前端再截是 no-op", () => {
  // 假设 LLM 传了 5000 字符 prompt,工具层截到 200 后打包
  const longPrompt = "a".repeat(5000);
  const truncatedPrompt = longPrompt.slice(0, 200);  // 镜像 ask_user_choice_tool.py:182
  const pluginJson = JSON.stringify({
    type: "interactive_choice",
    prompt: truncatedPrompt,
    options: [
      { id: "a", label: "A", value: "a" },
      { id: "b", label: "B", value: "b" },
    ],
  });
  const plainPart = { type: "plain", text: pluginJson };
  const result = truncateInteractiveChoice(unwrapInteractiveChoice(plainPart));
  // 截断后仍为 200 字符(JSON.parse 已建新对象,引用必然变,只校验内容)
  assert.equal(result.prompt.length, 200);
  assert.equal(result.type, "interactive_choice");
  // truncate 自身判断:prompt 已经是 200(等于上限,不超)→ mutated=false → 返回 unwrap 后的对象
  // unwrap 后的对象 = 不可变(no-op 路径)的 truncate 输出
  // 注意:与"短字段不动"那个 test 不可变语义不同(那个是直接传 InteractiveChoicePart)
  const result2 = truncateInteractiveChoice(result);
  assert.equal(result2, result);  // 二次 truncate 无变化时返回同一引用
});

test("E2E 真实插件超长 description: 工具层已截到 200,前端再截是 no-op", () => {
  const longDesc = "x".repeat(500);
  const truncatedDesc = longDesc.slice(0, 200);  // 镜像 ask_user_choice_tool.py:175
  const pluginJson = JSON.stringify({
    type: "interactive_choice",
    prompt: "选",
    options: [
      { id: "a", label: "A", description: truncatedDesc, value: "a" },
      { id: "b", label: "B", value: "b" },
    ],
  });
  const plainPart = { type: "plain", text: pluginJson };
  const result = truncateInteractiveChoice(unwrapInteractiveChoice(plainPart));
  assert.equal(result.options[0].description.length, 200);
});

test("E2E 真实插件极端: 10 options + 缺 description,全部通过", () => {
  // 工具层 _OPTIONS_MAX=10,这是 v1 边界
  const pluginJson = JSON.stringify({
    type: "interactive_choice",
    prompt: "选一个",
    options: Array.from({ length: 10 }, (_, i) => ({
      id: `opt${i}`,
      label: `Option ${i}`,
      value: `val${i}`,
      // description 故意不传(LLM 忽略)
    })),
  });
  const plainPart = { type: "plain", text: pluginJson };
  const unwrapped = unwrapInteractiveChoice(plainPart);
  assert.equal(validateInteractiveChoice(unwrapped), true);
  const result = truncateInteractiveChoice(unwrapped);
  assert.equal(result.options.length, 10);
});

// ════════════════════════════════════════════════════════════════
// 框架二次包装: tool_loop_agent_runner.py 把 tool str 包成 Json({id, ts, result})
// 然后 message_chain_to_storage_message_parts 把 Json 转成 {type:"plain", text: json.dumps({...})}
// 所以 dashboard 看到双层 JSON。这是真实部署时实际看到的数据形态。
// ════════════════════════════════════════════════════════════════

test("框架二次包装: {id, ts, result: '<InteractiveChoicePart JSON>'} → 解包成功", () => {
  // 镜像 tool_loop_agent_runner.py:1264-1273 的产出
  const innerJson = JSON.stringify({
    type: "interactive_choice",
    prompt: "请选择模型:",
    options: [
      { id: "a", label: "GPT-4", description: "更强但更慢", value: "gpt-4" },
      { id: "b", label: "GPT-4 mini", value: "gpt-4-mini" },
    ],
  });
  const wrappedJson = JSON.stringify({
    id: "call_abc123",
    ts: 1719654321.123,
    result: innerJson,
  });
  const plainPart = { type: "plain", text: wrappedJson };

  const unwrapped = unwrapInteractiveChoice(plainPart);
  assert.equal(isInteractiveChoicePayload(unwrapped), true);
  assert.equal(validateInteractiveChoice(unwrapped), true);
  assert.equal(unwrapped.prompt, "请选择模型:");
  assert.equal(unwrapped.options.length, 2);
  assert.equal(unwrapped.options[0].value, "gpt-4");
});

test("框架二次包装: result 字段是普通文本(非 JSON),不误解包", () => {
  // 假设 LLM 没用 ask_user_choice,调了其他工具,result 是 "天气晴朗" 这种纯文本
  const wrappedJson = JSON.stringify({
    id: "call_xyz",
    ts: 1719654321.0,
    result: "今天天气晴朗",
  });
  const plainPart = { type: "plain", text: wrappedJson };
  // 不应解包成 InteractiveChoicePart(因 result 不是 JSON)
  assert.equal(isInteractiveChoicePayload(unwrapInteractiveChoice(plainPart)), false);
});

test("框架二次包装: result 是损坏的 JSON,不爆错", () => {
  const wrappedJson = JSON.stringify({
    id: "call_xyz",
    ts: 1719654321.0,
    result: '{ "type": "interactive_choice", "broken',
  });
  const plainPart = { type: "plain", text: wrappedJson };
  // 不应 throw,应保留原 plain
  const result = unwrapInteractiveChoice(plainPart);
  assert.equal(result, plainPart);
});

test("框架二次包装: result 是合法 JSON 但不是 InteractiveChoicePart,不解包", () => {
  // 比如 result 是 {"type":"other",...} 或 {"foo":1}
  const wrappedJson = JSON.stringify({
    id: "call_xyz",
    ts: 1719654321.0,
    result: JSON.stringify({ type: "tool_result", other: "data" }),
  });
  const plainPart = { type: "plain", text: wrappedJson };
  assert.equal(isInteractiveChoicePayload(unwrapInteractiveChoice(plainPart)), false);
});

test("框架二次包装: result 字段缺失,不误判", () => {
  const wrappedJson = JSON.stringify({ id: "call_xyz", ts: 1719654321.0 });
  const plainPart = { type: "plain", text: wrappedJson };
  assert.equal(unwrapInteractiveChoice(plainPart), plainPart);
});

test("框架二次包装: 完整 pipeline(unwrap → validate → truncate)端到端", () => {
  const innerJson = JSON.stringify({
    type: "interactive_choice",
    prompt: "选择操作",
    title: "操作确认",
    options: [
      { id: "del", label: "删除", description: "不可逆", value: "delete" },
      { id: "cancel", label: "取消", value: "cancel" },
    ],
    input_placeholder: "或输入...",
  });
  const wrappedJson = JSON.stringify({
    id: "call_full",
    ts: 1719654321.0,
    result: innerJson,
  });
  const plainPart = { type: "plain", text: wrappedJson };

  const unwrapped = unwrapInteractiveChoice(plainPart);
  const validated = validateInteractiveChoice(unwrapped);
  assert.equal(validated, true);
  const truncated = truncateInteractiveChoice(unwrapped);
  assert.equal(truncated.title, "操作确认");
  assert.equal(truncated.input_placeholder, "或输入...");
  assert.equal(truncated.options[0].description, "不可逆");
});

// ════════════════════════════════════════════════════════════════
// 提取:从 tool_call part 的 tool_calls[] 中拆出 ask_user_choice 工具
// 这是 SSE 路径下 messageBlocks → InteractiveChoiceBox 渲染的唯一通路。
// ════════════════════════════════════════════════════════════════

test("extractAskUserChoiceFromToolCall: 镜像 SSE 实际形状(单 ask_user_choice 工具)", () => {
  // 模拟 useMessages.finishToolCall 写入的 part 结构
  const result = JSON.stringify({
    type: "interactive_choice",
    prompt: "请选择模型:",
    options: [
      { id: "a", label: "GPT-4", description: "更强但更慢", value: "gpt-4" },
      { id: "b", label: "GPT-4 mini", value: "gpt-4-mini" },
    ],
  });
  const part = {
    type: "tool_call",
    tool_calls: [
      {
        id: "call_xyz",
        name: "ask_user_choice",
        arguments: { prompt: "请选择模型:", options: [] },
        result,
        ts: 1719654321.0,
        finished_ts: 1719654321.5,
      },
    ],
  };
  const { remainingPart, extractedChoices } = extractAskUserChoiceFromToolCall(part);
  // 单 ask_user_choice,没有其他工具 → remainingPart 应为 null
  assert.equal(remainingPart, null);
  assert.equal(extractedChoices.length, 1);
  assert.equal(isInteractiveChoicePayload(extractedChoices[0]), true);
  assert.equal(extractedChoices[0].prompt, "请选择模型:");
  assert.equal(extractedChoices[0].options.length, 2);
});

test("extractAskUserChoiceFromToolCall: 多工具中混有 ask_user_choice,只拆 choice", () => {
  const part = {
    type: "tool_call",
    tool_calls: [
      { id: "t1", name: "get_weather", result: "晴天" },
      {
        id: "t2",
        name: "ask_user_choice",
        result: JSON.stringify({
          type: "interactive_choice",
          prompt: "选一个",
          options: [
            { id: "a", label: "A", value: "a" },
            { id: "b", label: "B", value: "b" },
          ],
        }),
      },
      { id: "t3", name: "search_web", result: "results" },
    ],
  };
  const { remainingPart, extractedChoices } = extractAskUserChoiceFromToolCall(part);
  // ask_user_choice 拆出
  assert.equal(extractedChoices.length, 1);
  assert.equal(extractedChoices[0].prompt, "选一个");
  // 剩余 2 个其他工具保留在 tool_call part
  assert.notEqual(remainingPart, null);
  assert.equal(remainingPart.tool_calls.length, 2);
  assert.equal(remainingPart.tool_calls[0].name, "get_weather");
  assert.equal(remainingPart.tool_calls[1].name, "search_web");
});

test("extractAskUserChoiceFromToolCall: 多个 ask_user_choice 都拆出", () => {
  const part = {
    type: "tool_call",
    tool_calls: [
      {
        id: "c1",
        name: "ask_user_choice",
        result: JSON.stringify({
          type: "interactive_choice",
          prompt: "第一个",
          options: [
            { id: "a", label: "A", value: "a" },
            { id: "b", label: "B", value: "b" },
          ],
        }),
      },
      {
        id: "c2",
        name: "ask_user_choice",
        result: JSON.stringify({
          type: "interactive_choice",
          prompt: "第二个",
          options: [
            { id: "x", label: "X", value: "x" },
            { id: "y", label: "Y", value: "y" },
          ],
        }),
      },
    ],
  };
  const { remainingPart, extractedChoices } = extractAskUserChoiceFromToolCall(part);
  assert.equal(remainingPart, null);
  assert.equal(extractedChoices.length, 2);
  assert.equal(extractedChoices[0].prompt, "第一个");
  assert.equal(extractedChoices[1].prompt, "第二个");
});

test("extractAskUserChoiceFromToolCall: ask_user_choice result 不是 JSON,保留在 tool_calls", () => {
  const part = {
    type: "tool_call",
    tool_calls: [
      { id: "c1", name: "ask_user_choice", result: "错误:参数非法" },  // 软错误字符串
    ],
  };
  const { remainingPart, extractedChoices } = extractAskUserChoiceFromToolCall(part);
  assert.equal(extractedChoices.length, 0);
  assert.equal(remainingPart.tool_calls.length, 1);
  assert.equal(remainingPart.tool_calls[0].name, "ask_user_choice");
});

test("extractAskUserChoiceFromToolCall: ask_user_choice result 是损坏 JSON,不爆错", () => {
  const part = {
    type: "tool_call",
    tool_calls: [
      { id: "c1", name: "ask_user_choice", result: '{ "type": "interactive_choice", "broken' },
    ],
  };
  const { remainingPart, extractedChoices } = extractAskUserChoiceFromToolCall(part);
  assert.equal(extractedChoices.length, 0);
  assert.equal(remainingPart.tool_calls.length, 1);
});

test("extractAskUserChoiceFromToolCall: ask_user_choice result 是合法 JSON 但非 choice,保留", () => {
  const part = {
    type: "tool_call",
    tool_calls: [
      { id: "c1", name: "ask_user_choice", result: JSON.stringify({ type: "other", foo: 1 }) },
    ],
  };
  const { remainingPart, extractedChoices } = extractAskUserChoiceFromToolCall(part);
  assert.equal(extractedChoices.length, 0);
  assert.equal(remainingPart.tool_calls.length, 1);
});

test("extractAskUserChoiceFromToolCall: 非法 choice(缺 options)被 validate 拒,保留", () => {
  // 模拟 plugin 软错误被 wrapper 重新包装成合法 JSON 但内容不合法
  const part = {
    type: "tool_call",
    tool_calls: [
      {
        id: "c1",
        name: "ask_user_choice",
        result: JSON.stringify({ type: "interactive_choice", prompt: "x" }),  // 缺 options
      },
    ],
  };
  const { remainingPart, extractedChoices } = extractAskUserChoiceFromToolCall(part);
  assert.equal(extractedChoices.length, 0);
  assert.equal(remainingPart.tool_calls.length, 1);
});

test("extractAskUserChoiceFromToolCall: 非 tool_call part 原样返回", () => {
  const part = { type: "plain", text: "hello" };
  const { remainingPart, extractedChoices } = extractAskUserChoiceFromToolCall(part);
  assert.equal(remainingPart, part);
  assert.equal(extractedChoices.length, 0);
});

test("extractAskUserChoiceFromToolCall: tool_call part 但无 tool_calls 数组,原样", () => {
  const part = { type: "tool_call" };
  const { remainingPart, extractedChoices } = extractAskUserChoiceFromToolCall(part);
  assert.equal(remainingPart, part);
  assert.equal(extractedChoices.length, 0);
});

test("extractAskUserChoiceFromToolCall: 截断管道也走(超长 prompt 拆出后被截到 200)", () => {
  const longPrompt = "a".repeat(500);
  const part = {
    type: "tool_call",
    tool_calls: [
      {
        id: "c1",
        name: "ask_user_choice",
        result: JSON.stringify({
          type: "interactive_choice",
          prompt: longPrompt,
          options: [
            { id: "a", label: "A", value: "a" },
            { id: "b", label: "B", value: "b" },
          ],
        }),
      },
    ],
  };
  const { extractedChoices } = extractAskUserChoiceFromToolCall(part);
  assert.equal(extractedChoices.length, 1);
  assert.equal(extractedChoices[0].prompt.length, 200);
});