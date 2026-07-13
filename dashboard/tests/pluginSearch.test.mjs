import assert from "node:assert/strict";
import test from "node:test";

import {
  buildSearchQuery,
  getPluginSearchFields,
  matchesPluginSearch,
} from "../src/utils/pluginSearch.mjs";

const plugin = {
  name: "weather-tools",
  display_name: "Weather Tools",
  desc: "Weather forecasts",
  author: "Example Author",
  repo: "https://github.com/example-owner/astrbot-plugin-weather.git/",
};

test("plugin search excludes repository URL infrastructure", () => {
  for (const term of ["github", "http", "https", "//"]) {
    assert.equal(matchesPluginSearch(plugin, buildSearchQuery(term)), false);
  }
});

test("plugin search keeps the repository owner and name searchable", () => {
  const repositoryUrls = [
    "https://github.com/example-owner/astrbot-plugin-weather.git/",
    "//github.com/example-owner/astrbot-plugin-weather?source=market",
    "github.com/example-owner/astrbot-plugin-weather#readme",
    "https://gitlab.com/example-owner/astrbot-plugin-weather",
  ];

  for (const repo of repositoryUrls) {
    const candidate = { ...plugin, repo };
    assert.equal(
      matchesPluginSearch(
        candidate,
        buildSearchQuery("example-owner/astrbot-plugin-weather"),
      ),
      true,
    );
    assert.ok(
      getPluginSearchFields(candidate).includes(
        "example-owner/astrbot-plugin-weather",
      ),
    );
  }
});

test("plugin search still matches github when it belongs to plugin metadata", () => {
  const githubPlugin = {
    ...plugin,
    name: "github-trending",
    repo: "example-owner/github-trending",
  };

  assert.equal(
    matchesPluginSearch(githubPlugin, buildSearchQuery("github")),
    true,
  );
});
