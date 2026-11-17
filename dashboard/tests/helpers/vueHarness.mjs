import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import { parse, compileScript, compileTemplate } from "vue/compiler-sfc";
import ts from "typescript";
import * as vue from "vue";

const require = createRequire(import.meta.url);

export function loadSource(url, imports = {}, globals = {}, renderTemplate = false) {
  const source = readFileSync(url, "utf8");
  const descriptor = url.pathname.endsWith(".vue") ? parse(source).descriptor : null;
  const compiled = descriptor ? compileScript(descriptor, { id: "test-component" }) : null;
  let script = compiled?.content || source;
  if (renderTemplate) {
    const template = compileTemplate({ source: descriptor.template.content,
      filename: url.pathname, id: "test-component",
      compilerOptions: { bindingMetadata: compiled.bindings, hoistStatic: false } });
    if (template.errors.length) throw new Error(template.errors.join("\n"));
    script += "\n" + template.code;
  }
  const output = ts.transpileModule(script, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(output, {
    exports: module.exports,
    require: (name) =>
      name in imports ? imports[name] : name === "vue" ? vue : require(name),
    console,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    ...globals,
  });
  if (renderTemplate) module.exports.default.render = module.exports.render;
  return module.exports;
}

export function mountTemplate(component, props = {}, provides = {}) {
  const node = (type, text = "") => ({ type, text, props: {}, children: [], parent: null });
  const renderer = vue.createRenderer({
    createElement: type => node(type), createText: text => node("text", text),
    createComment: text => node("comment", text),
    insert(child, parent, anchor) {
      if (child.parent) child.parent.children.splice(child.parent.children.indexOf(child), 1);
      child.parent = parent;
      const index = anchor ? parent.children.indexOf(anchor) : -1;
      if (index < 0) parent.children.push(child); else parent.children.splice(index, 0, child);
    },
    remove(child) { child.parent?.children.splice(child.parent.children.indexOf(child), 1); child.parent = null; },
    setText(child, text) { child.text = text; },
    setElementText(child, text) { child.text = text; child.children = []; },
    patchProp(child, key, oldValue, value) { child.props[key] = value; },
    parentNode: child => child.parent, nextSibling: child => child.parent?.children[child.parent.children.indexOf(child) + 1],
  });
  const root = node("root");
  const app = renderer.createApp(component, props);
  for (const [key, value] of Object.entries(provides)) app.provide(key, value);
  for (const [name, tag] of [["VBtn", "button"], ["VIcon", "i"], ["VSwitch", "input"], ["VDivider", "hr"]]) {
    app.component(name, { setup: (_, { attrs, slots }) => () => vue.h(tag, attrs, slots.default?.()) });
  }
  const instance = app.mount(root);
  const findAll = predicate => {
    const result = [];
    const visit = current => { if (predicate(current)) result.push(current); current.children.forEach(visit); };
    visit(root);
    return result;
  };
  return { root, findAll, state: instance.$.setupState, stop: () => app.unmount() };
}

export function mountSetup(component, props) {
  const renderer = vue.createRenderer({
    createElement: () => ({}),
    createText: () => ({}),
    createComment: () => ({}),
    insert() {},
    remove() {},
    setText() {},
    setElementText() {},
    patchProp() {},
    parentNode: () => null,
    nextSibling: () => null,
  });
  const app = renderer.createApp({ ...component, render: () => null }, props);
  const instance = app.mount({});
  return { state: instance.$.setupState, stop: () => app.unmount() };
}
