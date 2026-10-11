import assert from "node:assert/strict";
import test from "node:test";

import {
  LIMITED_SHIKI_SUPPORTED_LANGUAGES,
  createHighlighter,
  normalizeLimitedShikiLanguage,
} from "../src/utils/shikiLimitedBundle.js";

const languageCases = {
  c: ["c", "h"],
  cpp: ["cpp", "c++", "cc", "cxx", "h++", "hh", "hpp"],
  csharp: ["csharp", "cs"],
  dart: ["dart"],
  go: ["go", "golang"],
  kotlin: ["kotlin", "kt", "kts"],
  lua: ["lua"],
  php: ["php"],
  r: ["r"],
  ruby: ["ruby"],
  rust: ["rust", "rs"],
  scala: ["scala"],
  swift: ["swift"],
};

test("normalizes aliases for the expanded language set", () => {
  for (const [language, aliases] of Object.entries(languageCases)) {
    assert.equal(normalizeLimitedShikiLanguage(language), language);
    for (const alias of aliases) {
      assert.equal(normalizeLimitedShikiLanguage(alias), language, alias);
    }
    assert.ok(LIMITED_SHIKI_SUPPORTED_LANGUAGES.has(language), language);
  }

  assert.equal(normalizeLimitedShikiLanguage("unknown-language"), "text");
  assert.equal(normalizeLimitedShikiLanguage("c extra"), "c");
  assert.equal(normalizeLimitedShikiLanguage("rust:rust"), "rust");
});

test("highlights every expanded language with Shiki tokens", async () => {
  const highlighter = await createHighlighter({ themes: ["github-light"] });
  const samples = {
    c: "int main() { return 0; }",
    cpp: "std::vector<int> values;",
    csharp: "public class Sample {}",
    dart: "void main() {}",
    go: "package main\nfunc main() {}",
    kotlin: "fun main() {}",
    lua: "local value = 1",
    php: "<?php echo 'ok';",
    r: "value <- 1",
    ruby: "puts 'ok'",
    rust: "fn main() {}",
    scala: "object Main extends App {}",
    swift: "let value = 1",
  };

  for (const [language, code] of Object.entries(samples)) {
    assert.equal(highlighter.getLanguage(language)?.name, language, language);
    const html = highlighter.codeToHtml(code, {
      lang: language,
      theme: "github-light",
    });
    assert.match(html, /<span[^>]+style=/, language);
  }
});