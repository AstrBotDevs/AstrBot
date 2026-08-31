# Governance / 项目治理

## Project status / 项目状态

This repository is a modernized fork of AstrBot, maintained by a small team
and by agents. It continuously **cherry-picks** upstream commits
(default) and then selectively **adapts** or **skips** them so the fork stays
coherent. A merge of `upstream/master` is reserved for an explicitly justified
bulk sync where per-commit cherry-picks are impractical. The cursor and method
live in [`upstream-sync.yaml`](upstream-sync.yaml); each kept or skipped
upstream change is recorded in
[`upstream-decisions.jsonl`](upstream-decisions.jsonl) and reflected in the
per-version changelog's _Fork Adaptations_ and _Fork Deviations_ sections.

> 本仓库是 AstrBot 的现代化 fork，由小团队与智能体维护。默认对上游提交做**遴选（cherry-pick）**，再有选择地**适配**或**跳过**，以保持 fork 行为一致。仅当逐提交采摘不现实且有明确理由时，才合并 `upstream/master`。游标与方法见 [`upstream-sync.yaml`](upstream-sync.yaml)；每次保留或跳过的上游改动记录在 [`upstream-decisions.jsonl`](upstream-decisions.jsonl)，并体现在各版本 changelog 的 _Fork 适配_ 与 _Fork 差异_ 小节。

## Roles / 角色

- **Lead maintainer / 主维护者 — @BegoniaHe.** Final say on merges, scope, and
  upstream sync; triages security reports; owns the per-version notes in
  [`changelogs/`](changelogs/).
- **Maintainer / 维护者 — @YUZHEthefool.** Reviews and merges PRs; helps shape
  scope and fork deviations.
- **Agents / 智能体.** May write code, run checks, open development Issues and
  PRs, and request review. They must not merge, push `master`, tag, or
  release. See [AI_POLICY.md](AI_POLICY.md).
- **Contributors / 贡献者.** Anyone who opens development issues or PRs. See
  [CONTRIBUTING.md](CONTRIBUTING.md).

> Roles and code ownership are also listed in [.github/CODEOWNERS](.github/CODEOWNERS).
> Update both files together when ownership changes.
>
> 角色与代码归属同时在 [.github/CODEOWNERS](.github/CODEOWNERS) 中列出；归属变更时请两处同步更新。

## Decision-making / 决策流程

| Change type / 变更类型                        | Process / 流程                                                                                                                                                                                                |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Docs, tests, small fixes / 文档、测试、小修复 | Human maintainer review **and** AI-assisted review → merge / 人类维护者评审 **且** 有 AI 辅助评审后合并                                                                                                       |
| New features / 新功能                         | Open a development Issue first; maintainer consensus; then PR / **先开开发 Issue**；维护者达成共识后再提 PR                                                                                                   |
| Breaking changes / 破坏性变更                 | Maintainer agreement; update [CONTRIBUTING.md](CONTRIBUTING.md); note in changelog / 维护者一致；更新 CONTRIBUTING；changelog 注明                                                                            |
| Upstream integration / 上游集成               | Cherry-pick by default per `upstream-sync.yaml`; record keeps/skips in `upstream-decisions.jsonl` and the changelog / 默认按 `upstream-sync.yaml` 遴选；保留/跳过记入 `upstream-decisions.jsonl` 与 changelog |
| Security / 安全                               | Follow [SECURITY.md](SECURITY.md); private until fixed / 按 SECURITY.md 处理，修复前保持私密                                                                                                                  |

A pull request may merge only when a **human maintainer** has reviewed it and
the same PR has a separate **AI-assisted review**. The authoring agent must
not merge. Details: [AI_POLICY.md](AI_POLICY.md).

Decisions aim for consensus. The lead maintainer breaks ties and decides
scope. PR titles use English Conventional Commits (see
[CONTRIBUTING.md](CONTRIBUTING.md)). Commit-message types, description
rules, and AI-assisted footer policy are in CONTRIBUTING.md and
`.agents/shared/conventional-commit/REFERENCE.md`.

> 合入 `master` 需要人类维护者评审，且同一 PR 上另有 AI 辅助评审。作者智能体不得自行合并。细则见 [AI_POLICY.md](AI_POLICY.md)。
>
> 决策以达成共识为目标；主维护者在僵局与范围问题上做最终裁定。PR 标题使用英文 Conventional Commits（见 [CONTRIBUTING.md](CONTRIBUTING.md)）。提交说明的类型、描述规则与 AI 辅助 footer 见 CONTRIBUTING.md 与 `.agents/shared/conventional-commit/REFERENCE.md`。

## Scope / 范围

- Match the **current branch**, not upstream historical behavior.
- Do **not** add or preserve compatibility shims for deprecated APIs, plugin
  formats, or old knowledge-base layouts.
- Python baseline `3.14+`; backend uses `uv`; dashboard uses `pnpm`.

> 范围：以**当前分支**为准，不沿用上游历史行为；**不**为废弃 API、插件格式或旧知识库布局补兼容；Python `3.14+`；后端 `uv`；前端 `pnpm`。

## Changes to this policy / 修改本政策

This governance document changes through the same process as breaking
changes: maintainer agreement, committed with a `docs:` Conventional Commit,
and noted in the changelog.

> 本治理文档按破坏性变更同等流程修改：维护者一致，以 `docs:` Conventional Commit 提交，并在 changelog 中注明。
