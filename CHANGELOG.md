# Changelog

All notable changes to this fork are documented as **one file per version**
under [`changelogs/`](./changelogs/). This root file is an index only; it does
not duplicate the per-version notes. The repository currently publishes no
PyPI package or GitHub release assets, so the `changelogs/` directory is the
authoritative release record for this branch.

> 本仓库的所有变更以**每个版本一个文件**的形式记录在 [`changelogs/`](./changelogs/) 下。本文件仅作索引，不重复各版本的完整说明。当前 fork 不发布 PyPI 包或 GitHub Release 资产，`changelogs/` 目录是本分支权威的版本记录。

## Where the notes live / 说明文件位置

- Per-version entries: [`changelogs/`](./changelogs/) — spanning `v3.4.0`
  through the current `v4.27.x` series.
- Each entry is **bilingual**: English first, followed by a `## 中文` section
  that mirrors the same categories.

## Section conventions / 分节约定

Each entry follows a [Keep a Changelog](https://keepachangelog.com/)-style
structure, extended with two fork-specific sections so readers can tell
fork behavior apart from upstream merges:

- **Added / Changed / Fixed / Documentation** — standard categories.
- **Fork Adaptations** — fork-specific behavior retained on top of the
  corresponding upstream change.
- **Fork Deviations** — upstream changes intentionally **not** applied to this
  fork, with the upstream PR/issue reference and the reason.

> 每条记录在标准 Added/Changed/Fixed/Documentation 之外，额外包含 **Fork 适配**（在上游改动之上保留的 fork 行为）与 **Fork 差异**（有意不采纳的上游改动，附上游 PR/issue 编号与理由）两节，便于区分 fork 行为与上游合并内容。

## Recent releases / 近期版本

### v4.27.x

- [v4.27.5](./changelogs/v4.27.5.md)
- [v4.27.4](./changelogs/v4.27.4.md)
- [v4.27.3](./changelogs/v4.27.3.md)
- [v4.27.2](./changelogs/v4.27.2.md)
- [v4.27.1](./changelogs/v4.27.1.md)

### v4.26.x

- [v4.26.7](./changelogs/v4.26.7.md)
- [v4.26.6](./changelogs/v4.26.6.md)
- [v4.26.5](./changelogs/v4.26.5.md)
- [v4.26.4](./changelogs/v4.26.4.md)
- [v4.26.3](./changelogs/v4.26.3.md)
- [v4.26.2](./changelogs/v4.26.2.md)
- [v4.26.1](./changelogs/v4.26.1.md)
- `v4.26.0` beta pre-releases — see the [`changelogs/`](./changelogs/) directory.

> Full history — including the `v3.4.x` series, earlier `v4.x` releases, and
> all beta pre-releases — lives in [`changelogs/`](./changelogs/).
>
> 完整历史（含 `v3.4.x` 系列、早期 `v4.x` 版本及全部 beta 预发布）见 [`changelogs/`](./changelogs/) 目录。

## Relationship to upstream / 与上游的关系

This repository is a modernized fork of AstrBot. Changelog entries merge
upstream changes and then record what the fork kept (`Fork Adaptations`) or
declined (`Fork Deviations`). When upstream behavior and this fork disagree,
the behavior described in these notes follows **this repository**, not
upstream historical behavior. See [CONTRIBUTING.md](./CONTRIBUTING.md) for the
contribution scope and [`upstream-sync.yaml`](./upstream-sync.yaml) for the
upstream merge rules.

> 本仓库是 AstrBot 的现代化 fork。每条记录会合并上游改动，并标注 fork 保留（Fork 适配）或拒绝（Fork 差异）的内容。当上游与本 fork 行为不一致时，以**本仓库**为准，而非上游历史行为。贡献范围见 [CONTRIBUTING.md](./CONTRIBUTING.md)，上游合并规则见 [`upstream-sync.yaml`](./upstream-sync.yaml)。
