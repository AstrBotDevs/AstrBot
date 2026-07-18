// Author: elecvoid243, 2026-07-18
// codemirrorLanguages unit tests: the extension->key map is pure;
// loadLanguage tests use the real language packs (parser-only code,
// no DOM needed) and verify LanguageSupport instances + caching.
import { describe, expect, it } from "vitest";
import { LanguageSupport } from "@codemirror/language";
import {
  languageKeyForPath,
  loadLanguage,
} from "@/utils/codemirrorLanguages";

describe("languageKeyForPath", () => {
  it("maps core extensions to their language keys", () => {
    expect(languageKeyForPath("a/b/main.py")).toBe("python");
    expect(languageKeyForPath("x.TS")).toBe("typescript");
    expect(languageKeyForPath("comp.tsx")).toBe("tsx");
    expect(languageKeyForPath("comp.jsx")).toBe("jsx");
    expect(languageKeyForPath("data.json")).toBe("json");
    expect(languageKeyForPath("ci.yml")).toBe("yaml");
    expect(languageKeyForPath("run.sh")).toBe("shell");
    expect(languageKeyForPath("App.vue")).toBe("html");
    expect(languageKeyForPath("icon.svg")).toBe("xml");
    expect(languageKeyForPath("README.md")).toBe("markdown");
    expect(languageKeyForPath("q.sql")).toBe("sql");
    expect(languageKeyForPath("lib.rs")).toBe("rust");
    expect(languageKeyForPath("main.go")).toBe("go");
    expect(languageKeyForPath("a.c")).toBe("cpp");
    expect(languageKeyForPath("a.hpp")).toBe("cpp");
    expect(languageKeyForPath("fix.patch")).toBe("diff");
  });

  it("returns null for unmapped or extension-less paths", () => {
    expect(languageKeyForPath(".gitignore")).toBeNull();
    expect(languageKeyForPath("notes.ini")).toBeNull();
    expect(languageKeyForPath("Makefile")).toBeNull();
    expect(languageKeyForPath("")).toBeNull();
  });
});

describe("loadLanguage", () => {
  it("loads a real LanguageSupport and caches the promise", async () => {
    const a = loadLanguage("python");
    const b = loadLanguage("python");
    expect(a).toBe(b); // same cached promise
    const support = await a;
    expect(support).toBeInstanceOf(LanguageSupport);
  });

  it("loads StreamLanguage-backed keys (shell/diff)", async () => {
    await expect(loadLanguage("shell")).resolves.toBeInstanceOf(
      LanguageSupport,
    );
    await expect(loadLanguage("diff")).resolves.toBeInstanceOf(
      LanguageSupport,
    );
  });
});
