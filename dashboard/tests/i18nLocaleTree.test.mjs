import { expect, test, vi } from "vitest";
import { readLocaleTree } from "../scripts/i18n-locale-tree.mjs";

test.each(["'", '"'])("locale loading preserves namespaces with %s quotes and multiline imports", (quote) => {
  const bundle = { title: "Run tools", nested: { action: "Start" } };
  const read = vi.fn(() => bundle);
  const source = `
    import toolUse
      from ${quote}./features/tool-use.json${quote};
    // Neither a comment nor formatting changes the runtime namespace.
    export default ({
      features: { ${quote}tool-use${quote}: toolUse },
      toolUse,
    } as const);
  `;
  expect(readLocaleTree(source, read)).toEqual({ features: { "tool-use": bundle }, toolUse: bundle });
  expect(read).toHaveBeenCalledTimes(2);
  expect(read).toHaveBeenCalledWith("./features/tool-use.json");
});

test("an unresolved bundle fails the checker instead of silently dropping its keys", () => {
  expect(() => readLocaleTree("export default { features: missingBundle };", vi.fn())).toThrow(
    "unresolved locale import missingBundle",
  );
  expect(() => readLocaleTree("export default { ...otherBundle };", vi.fn())).toThrow("unsupported locale property");
});
