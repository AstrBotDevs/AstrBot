from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


def load_sync_module():
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "sync_docs_to_wiki.py"
    )
    spec = spec_from_file_location("sync_docs_to_wiki", script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module from {script_path}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SyncDocsHelpersTest(unittest.TestCase):
    def test_page_name_for_nested_markdown_source(self):
        module = load_sync_module()

        self.assertEqual(
            module.page_name_for_source("zh/deploy/astrbot/docker.md"),
            "zh-deploy-astrbot-docker",
        )

    def test_strip_frontmatter_removes_leading_block(self):
        module = load_sync_module()

        source = "---\nlayout: home\n---\n\n# Title\n"

        self.assertEqual(module.strip_frontmatter(source), "# Title\n")

    def test_module_does_not_expose_removed_wrapper_helpers(self):
        module = load_sync_module()

        self.assertFalse(hasattr(module, "get_link_resolver"))
        self.assertFalse(hasattr(module, "resolve_source_path"))
        self.assertFalse(hasattr(module, "compute_managed_files"))
        self.assertFalse(hasattr(module, "MANAGED_FILENAMES"))
        self.assertFalse(hasattr(module, "find_candidates_by_suffix"))

    def test_module_exposes_consolidated_helper_names(self):
        module = load_sync_module()

        self.assertTrue(hasattr(module, "prepare_candidate_path"))
        self.assertTrue(hasattr(module, "resolve_link_path"))
        self.assertTrue(hasattr(module, "LANG_CONFIG"))
        self.assertTrue(hasattr(module, "Segment"))
        self.assertTrue(hasattr(module, "iter_segments"))

    def test_parse_doc_target_returns_base_and_anchor(self):
        module = load_sync_module()

        self.assertEqual(
            module.parse_doc_target("/deploy/guide#intro"),
            ("/deploy/guide", "#intro"),
        )
        self.assertIsNone(module.parse_doc_target("https://example.com/guide"))
        self.assertIsNone(module.parse_doc_target("../images/diagram.png"))
        self.assertIsNone(module.parse_doc_target("#intro"))

    def test_iter_markdown_links_handles_whitespace_before_target(self):
        module = load_sync_module()

        links = list(module.iter_markdown_links("See [Guide]\n(guide.md).\n"))

        self.assertEqual([link.target for link in links], ["guide.md"])

    def test_iter_segments_splits_text_inline_and_fenced_code(self):
        module = load_sync_module()

        segments = list(
            module.iter_segments(
                "Start [Guide](/guide) `code [Guide](/guide)`\n\n```md\n[Guide](/guide)\n```\nTail\n"
            )
        )

        self.assertEqual(
            [(segment.kind, segment.text) for segment in segments],
            [
                ("text", "Start [Guide](/guide) "),
                ("inline_code", "`code [Guide](/guide)`"),
                ("text", "\n\n"),
                ("code_block", "```md\n[Guide](/guide)\n```"),
                ("text", "\nTail\n"),
            ],
        )

    def test_rewrite_links_handles_absolute_same_language_links(self):
        module = load_sync_module()

        resolver = module.LinkResolver(Path(__file__).resolve().parents[1])

        content = "See [Docker](/deploy/astrbot/docker).\n"

        self.assertEqual(
            module.rewrite_links(
                content,
                source_path="zh/what-is-astrbot.md",
                resolver=resolver,
            ),
            "See [Docker](zh-deploy-astrbot-docker).\n",
        )

    def test_rewrite_links_handles_relative_links(self):
        module = load_sync_module()

        resolver = module.LinkResolver(Path(__file__).resolve().parents[1])

        content = "Use [Dify](../agent-runners/dify.md).\n"

        self.assertEqual(
            module.rewrite_links(
                content,
                source_path="zh/providers/dify.md",
                resolver=resolver,
            ),
            "Use [Dify](zh-providers-agent-runners-dify).\n",
        )

    def test_rewrite_links_handles_rewritten_root_paths(self):
        module = load_sync_module()

        resolver = module.LinkResolver(Path(__file__).resolve().parents[1])

        content = "See [Connecting Model Services](/config/providers/start).\n"

        self.assertEqual(
            module.rewrite_links(
                content,
                source_path="zh/what-is-astrbot.md",
                resolver=resolver,
            ),
            "See [Connecting Model Services](zh-providers-start).\n",
        )

    def test_rewrite_links_handles_internal_links_with_parentheses(self):
        module = load_sync_module()

        with TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "docs"
            (source_root / "zh").mkdir(parents=True)
            (source_root / "zh" / "index.md").write_text(
                "See [Guide](/guide(test)).\n",
                encoding="utf-8",
            )
            (source_root / "zh" / "guide(test).md").write_text(
                "# Guide\n",
                encoding="utf-8",
            )
            resolver = module.LinkResolver(source_root)

            self.assertEqual(
                module.rewrite_links(
                    "See [Guide](/guide(test)).\n",
                    source_path="zh/index.md",
                    resolver=resolver,
                ),
                "See [Guide](zh-guide(test)).\n",
            )

    def test_rewrite_links_leaves_local_asset_links_unchanged(self):
        module = load_sync_module()

        with TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "docs"
            (source_root / "zh" / "use").mkdir(parents=True)
            (source_root / "zh" / "images").mkdir(parents=True)
            (source_root / "zh" / "use" / "guide.md").write_text(
                "# Guide\n", encoding="utf-8"
            )
            (source_root / "zh" / "images" / "diagram.png").write_bytes(b"png")
            resolver = module.LinkResolver(source_root)

            content = "![Diagram](../images/diagram.png)\n"

            self.assertEqual(
                module.rewrite_links(
                    content,
                    source_path="zh/use/guide.md",
                    resolver=resolver,
                ),
                content,
            )

    def test_rewrite_links_skips_fenced_code_blocks(self):
        module = load_sync_module()

        with TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "docs"
            (source_root / "zh").mkdir(parents=True)
            (source_root / "zh" / "index.md").write_text("# Home\n", encoding="utf-8")
            (source_root / "zh" / "guide.md").write_text("# Guide\n", encoding="utf-8")
            resolver = module.LinkResolver(source_root)

            content = "```md\n[Guide](/guide)\n```\n\nSee [Guide](/guide).\n"

            self.assertEqual(
                module.rewrite_links(
                    content,
                    source_path="zh/index.md",
                    resolver=resolver,
                ),
                "```md\n[Guide](/guide)\n```\n\nSee [Guide](zh-guide).\n",
            )

    def test_rewrite_links_skips_inline_code(self):
        module = load_sync_module()

        with TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "docs"
            (source_root / "zh").mkdir(parents=True)
            (source_root / "zh" / "index.md").write_text("# Home\n", encoding="utf-8")
            (source_root / "zh" / "guide.md").write_text("# Guide\n", encoding="utf-8")
            resolver = module.LinkResolver(source_root)

            content = "Use `[Guide](/guide)` literally, then See [Guide](/guide).\n"

            self.assertEqual(
                module.rewrite_links(
                    content,
                    source_path="zh/index.md",
                    resolver=resolver,
                ),
                "Use `[Guide](/guide)` literally, then See [Guide](zh-guide).\n",
            )

    def test_link_resolver_resolves_source_paths(self):
        module = load_sync_module()

        with TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "docs"
            (source_root / "zh" / "deploy").mkdir(parents=True)
            (source_root / "zh" / "index.md").write_text("# Home\n", encoding="utf-8")
            (source_root / "zh" / "deploy" / "guide.md").write_text(
                "# Guide\n", encoding="utf-8"
            )

            resolver = module.LinkResolver(source_root)

            self.assertEqual(
                resolver.resolve_markdown_target("/deploy/guide#intro", "zh/index.md"),
                ("zh/deploy/guide.md", "#intro"),
            )

    def test_resolve_link_path_resolves_relative_target(self):
        module = load_sync_module()

        with TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "docs"
            (source_root / "zh" / "providers").mkdir(parents=True)
            (source_root / "zh" / "agent-runners").mkdir(parents=True)
            (source_root / "zh" / "providers" / "dify.md").write_text(
                "# Dify\n",
                encoding="utf-8",
            )
            (source_root / "zh" / "agent-runners" / "dify.md").write_text(
                "# Agent Runner\n",
                encoding="utf-8",
            )

            self.assertEqual(
                module.resolve_link_path(
                    base_target="../agent-runners/dify.md",
                    source_path="zh/providers/dify.md",
                    source_root=source_root,
                    source_pages=module.discover_source_pages(str(source_root)),
                ).resolved_path,
                "zh/agent-runners/dify.md",
            )

    def test_build_home_page_uses_language_config(self):
        module = load_sync_module()

        self.assertIn(
            module.LANG_CONFIG["zh"]["home_intro"], module.build_home_page("zh")
        )
        self.assertIn(
            module.LANG_CONFIG["en"]["home_intro"], module.build_home_page("en")
        )

    def test_prepare_candidate_path_normalizes_suffix_and_alias(self):
        module = load_sync_module()

        self.assertEqual(
            module.prepare_candidate_path(
                module.PurePosixPath("zh/config/providers/../providers/start")
            ),
            module.PurePosixPath("zh/providers/start.md"),
        )

    def test_find_existing_source_path_matches_language_bounded_suffixes(self):
        module = load_sync_module()

        self.assertEqual(
            module.find_existing_source_path(
                candidate=module.PurePosixPath("zh/bar/guide.md"),
                source_root=Path("/tmp/nonexistent"),
                source_pages=(
                    "zh/bar/guide.md",
                    "zh/foo/bar/guide.md",
                    "zh/foobar/guide.md",
                    "en/bar/guide.md",
                ),
            ).ambiguous_matches,
            ("zh/bar/guide.md", "zh/foo/bar/guide.md"),
        )

    def test_build_page_info_returns_page_info_dataclass(self):
        module = load_sync_module()

        with TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "docs"
            (source_root / "zh").mkdir(parents=True)
            (source_root / "zh" / "index.md").write_text(
                "# 中文首页\n", encoding="utf-8"
            )

            resolver = module.LinkResolver(source_root)
            page_info = module.build_page_info(
                source_root=source_root,
                source_path="zh/index.md",
                resolver=resolver,
            )

            self.assertIsInstance(page_info, module.PageInfo)
            self.assertEqual(page_info.page_name, "zh-index")

    def test_build_page_info_uses_display_ready_group(self):
        module = load_sync_module()

        with TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "docs"
            (source_root / "zh" / "agent-runners").mkdir(parents=True)
            (source_root / "zh" / "agent-runners" / "guide.md").write_text(
                "# Guide\n",
                encoding="utf-8",
            )

            resolver = module.LinkResolver(source_root)
            page_info = module.build_page_info(
                source_root=source_root,
                source_path="zh/agent-runners/guide.md",
                resolver=resolver,
            )

            self.assertEqual(page_info.group, "agent runners")

    def test_sync_writes_pages_and_sidebar(self):
        module = load_sync_module()

        with TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "docs"
            wiki_root = Path(temp_dir) / "wiki"
            (source_root / "zh").mkdir(parents=True)
            (source_root / "en").mkdir(parents=True)

            (source_root / "zh" / "index.md").write_text(
                "---\nlayout: home\n---\n\n# 中文首页\n\nSee [Guide](/deploy/guide).\n",
                encoding="utf-8",
            )
            (source_root / "zh" / "deploy").mkdir(parents=True)
            (source_root / "zh" / "deploy" / "guide.md").write_text(
                "# 部署指南\n",
                encoding="utf-8",
            )
            (source_root / "en" / "index.md").write_text(
                "# English Home\n\nSee [Guide](/en/deploy/guide).\n",
                encoding="utf-8",
            )
            (source_root / "en" / "deploy").mkdir(parents=True)
            (source_root / "en" / "deploy" / "guide.md").write_text(
                "# Deployment Guide\n",
                encoding="utf-8",
            )

            module.sync_docs_to_wiki(source_root=source_root, wiki_root=wiki_root)

            self.assertTrue((wiki_root / "Home.md").exists())
            self.assertTrue((wiki_root / "Home-en.md").exists())
            self.assertTrue((wiki_root / "_Sidebar.md").exists())
            self.assertTrue((wiki_root / "zh-index.md").exists())
            self.assertTrue((wiki_root / "en-index.md").exists())
            self.assertIn(
                "[Guide](zh-deploy-guide)",
                (wiki_root / "zh-index.md").read_text(encoding="utf-8"),
            )

    def test_sync_preserves_unknown_wiki_pages(self):
        module = load_sync_module()

        with TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "docs"
            wiki_root = Path(temp_dir) / "wiki"
            (source_root / "zh").mkdir(parents=True)
            (source_root / "en").mkdir(parents=True)

            (source_root / "zh" / "index.md").write_text(
                "# 中文首页\n", encoding="utf-8"
            )
            (source_root / "en" / "index.md").write_text(
                "# English Home\n", encoding="utf-8"
            )

            wiki_root.mkdir(parents=True)
            handwritten = wiki_root / "zh-handwritten.md"
            handwritten.write_text("# Keep me\n", encoding="utf-8")

            module.sync_docs_to_wiki(source_root=source_root, wiki_root=wiki_root)

            self.assertTrue(handwritten.exists())

    def test_find_unresolved_doc_links_reports_ambiguous_matches(self):
        module = load_sync_module()

        with TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "docs"
            (source_root / "zh" / "foo").mkdir(parents=True)
            (source_root / "zh" / "bar").mkdir(parents=True)
            (source_root / "zh" / "index.md").write_text(
                "See [Guide](/guide).\n",
                encoding="utf-8",
            )
            (source_root / "zh" / "foo" / "guide.md").write_text(
                "# Foo\n", encoding="utf-8"
            )
            (source_root / "zh" / "bar" / "guide.md").write_text(
                "# Bar\n", encoding="utf-8"
            )

            unresolved = module.find_unresolved_doc_links(source_root)

            self.assertEqual(
                unresolved,
                [
                    "zh/index.md -> /guide (ambiguous: zh/bar/guide.md, zh/foo/guide.md)",
                ],
            )

    def test_resolver_does_not_match_partial_path_segments(self):
        module = load_sync_module()

        with TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "docs"
            (source_root / "zh" / "foobar").mkdir(parents=True)
            (source_root / "zh" / "index.md").write_text(
                "See [Guide](/bar/guide).\n",
                encoding="utf-8",
            )
            (source_root / "zh" / "foobar" / "guide.md").write_text(
                "# Guide\n",
                encoding="utf-8",
            )

            resolver = module.LinkResolver(source_root)

            self.assertEqual(
                resolver.resolve_markdown_target("/bar/guide", "zh/index.md"),
                (None, ""),
            )

    def test_live_docs_have_no_unresolved_internal_doc_links(self):
        module = load_sync_module()

        unresolved = module.find_unresolved_doc_links(
            source_root=Path(__file__).resolve().parents[1],
        )

        self.assertEqual(unresolved, [])

    def test_check_unresolved_doc_links_raises_for_bad_docs(self):
        module = load_sync_module()

        with TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "docs"
            (source_root / "zh").mkdir(parents=True)
            (source_root / "zh" / "index.md").write_text(
                "See [Missing](/missing).\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                module.check_unresolved_doc_links(source_root)


if __name__ == "__main__":
    unittest.main()
