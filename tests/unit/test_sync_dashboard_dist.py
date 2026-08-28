from pathlib import Path

from scripts.sync_dashboard_dist import embed_docs_help, sync_dashboard_dist


def test_sync_dashboard_dist_copies_docs_into_dashboard_and_data_help(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    dashboard_dist = repo / "dashboard" / "dist"
    docs_dist = repo / "docs" / ".vitepress" / "dist"
    data_dist = repo / "data" / "dist"
    dashboard_dist.mkdir(parents=True)
    docs_dist.mkdir(parents=True)
    (dashboard_dist / "index.html").write_text("dash", encoding="utf-8")
    (docs_dist / "faq.html").write_text("faq", encoding="utf-8")

    src, dst = sync_dashboard_dist(repo_root=repo, src=dashboard_dist, dst=data_dist)

    assert src == dashboard_dist.resolve()
    assert dst == data_dist.resolve()
    assert (dashboard_dist / "help" / "faq.html").read_text(encoding="utf-8") == "faq"
    assert (data_dist / "help" / "faq.html").read_text(encoding="utf-8") == "faq"
    assert (data_dist / "index.html").read_text(encoding="utf-8") == "dash"


def test_embed_docs_help_skips_missing_docs_build(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    assert embed_docs_help(dist_dir, repo_root=tmp_path) is None
    assert not (dist_dir / "help").exists()
