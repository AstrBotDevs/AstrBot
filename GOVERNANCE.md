# Governance / 项目治理

## Project status / 项目状态

This repository is a modernized fork of AstrBot, maintained by a small team.
It continuously merges upstream changes and then selectively **adapts** or
**declines** them to keep the fork's behavior coherent. The merge rules live
in [`upstream-sync.yaml`](upstream-sync.yaml); each kept or skipped upstream
change is recorded in [`upstream-decisions.jsonl`](upstream-decisions.jsonl)
and reflected in the per-version changelog's _Fork Adaptations_ and _Fork
Deviations_ sections.

> 本仓库是 AstrBot 的现代化 fork，由小团队维护。仓库持续合并上游改动，并有选择地**采纳**或**拒绝**，以保持 fork 行为一致。合并规则见 [`upstream-sync.yaml`](upstream-sync.yaml)；每次保留或跳过的上游改动记录在 [`upstream-decisions.jsonl`](upstream-decisions.jsonl)，并体现在各版本 changelog 的 _Fork 适配_ 与 _Fork 差异_ 小节。

## Roles / 角色

- **Lead maintainer / 主维护者 — @BegoniaHe.** Final say on merges, scope, and
  upstream sync; triages security reports; owns the per-version notes in
  [`changelogs/`](changelogs/).
- **Maintainer / 维护者 — @YUZHEthefool.** Reviews and merges PRs; helps shape
  scope and fork deviations.
- **Contributors / 贡献者.** Anyone who opens issues or PRs. See
  [CONTRIBUTING.md](CONTRIBUTING.md).

> Roles and code ownership are also listed in [.github/CODEOWNERS](.github/CODEOWNERS).
> Update both files together when ownership changes.
>
> 角色与代码归属同时在 [.github/CODEOWNERS](.github/CODEOWNERS) 中列出；归属变更时请两处同步更新。

## Decision-making / 决策流程

| Change type / 变更类型                        | Process / 流程                                                                                                                                                                          |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Docs, tests, small fixes / 文档、测试、小修复 | Maintainer review → merge / 维护者评审后合并                                                                                                                                            |
| New features / 新功能                         | Open an Issue to discuss **first**; reach consensus among maintainers; then PR / **先开 Issue 讨论**；维护者达成共识后再提 PR                                                           |
| Breaking changes / 破坏性变更                 | Maintainer agreement; update [CONTRIBUTING.md](CONTRIBUTING.md); note in changelog / 维护者一致；更新 CONTRIBUTING；changelog 注明                                                      |
| Upstream merge / 上游合并                     | Follow `upstream-sync.yaml`; record keeps/skips in `upstream-decisions.jsonl` and the changelog / 按 `upstream-sync.yaml` 处理；保留/跳过记录入 `upstream-decisions.jsonl` 与 changelog |
| Security / 安全                               | Follow [SECURITY.md](SECURITY.md); private until fixed / 按 SECURITY.md 处理，修复前保持私密                                                                                            |

Decisions aim for consensus. The lead maintainer breaks ties and decides
scope. PR titles use English Conventional Commits (see [CONTRIBUTING.md](CONTRIBUTING.md)).

> 决策以达成共识为目标；主维护者在僵局与范围问题上做最终裁定。PR 标题使用英文 Conventional Commits（见 [CONTRIBUTING.md](CONTRIBUTING.md)）。

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
