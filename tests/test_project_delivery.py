"""Network-free tests for full Project delivery reconciliation."""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location(
    "project_delivery",
    Path(__file__).resolve().parents[1] / "scripts/sync_github_project.py",
)
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {"node": {"createdAt": "2026-10-01T00:00:00Z"}}
        api = patch.object(sync, "graphql", return_value=self.metadata)
        api.start()
        self.addCleanup(api.stop)
        self.fields = [
            {
                "name": name,
                "id": name,
                "options": [{"name": value, "id": value} for value in values],
            }
            for name, values in [
                ("Status", sync.STATUS_OPTIONS),
                ("交付进度", sync.DELIVERY_OPTIONS),
            ]
        ] + [
            {"name": name, "id": name, "dataType": "TEXT"}
            for name in ("实现关联", "发布版本", "发布说明")
        ]
        self.page = {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}
        self.issue = {
            "__typename": "Issue",
            "id": "ISSUE",
            "number": 1,
            "state": "OPEN",
            "labels": self.page,
        }

    def test_snapshot_preview_apply_and_second_run_idempotence(self):
        for apply in (False, True):
            with (
                self.subTest(apply=apply),
                patch.object(
                    sync,
                    "connection",
                    side_effect=[self.fields, [], [dict(self.issue)], [], [], []],
                ),
                patch.object(
                    sync.subprocess, "run", return_value=Mock(stdout="a" * 40)
                ),
                patch.object(
                    sync,
                    "graphql",
                    return_value={
                        **self.metadata,
                        "addProjectV2ItemById": {"item": {"id": "I"}},
                    },
                ) as api,
            ):
                plan = sync.reconcile("P", "AstrBotDevs/AstrBot", apply=apply)
                self.assertEqual(
                    plan[0]["changes"], {"Status": "Todo", "交付进度": "未关联实现"}
                )
                self.assertEqual(api.call_count, 4 if apply else 1)
                self.assertTrue(api.call_args_list[0].args[0].startswith("query"))
        item = {
            "id": "I",
            "content": self.issue,
            "isArchived": False,
            "fieldValues": self.page,
        }
        values = [
            {"field": {"name": key}, "name": value}
            for key, value in plan[0]["changes"].items()
        ]
        with (
            patch.object(
                sync,
                "connection",
                side_effect=[
                    self.fields,
                    [item],
                    [dict(self.issue)],
                    [],
                    [],
                    [],
                    values,
                ],
            ),
            patch.object(sync.subprocess, "run", return_value=Mock(stdout="a" * 40)),
            patch.object(sync, "graphql", return_value=self.metadata) as api,
        ):
            self.assertEqual(sync.reconcile("P", "AstrBotDevs/AstrBot", apply=True), [])
            api.assert_called_once()
            self.assertTrue(api.call_args.args[0].startswith("query"))

    def test_snapshot_skips_archived_draft_foreign_and_old_closed(self):
        archived = {"id": "I", "content": self.issue, "isArchived": True}
        foreign = {
            "id": "F",
            "content": {"__typename": "Issue", "id": "FOREIGN"},
            "isArchived": False,
        }
        draft = {
            "id": "D",
            "content": {"__typename": "DraftIssue", "id": "DRAFT"},
            "isArchived": False,
        }
        closed = {
            **self.issue,
            "id": "OLD",
            "number": 2,
            "state": "CLOSED",
            "closedAt": "2026-09-30T23:59:59Z",
        }
        with (
            patch.object(
                sync,
                "connection",
                side_effect=[
                    self.fields,
                    [archived, foreign, draft],
                    [self.issue, closed],
                    [],
                    [],
                ],
            ),
            patch.object(sync.subprocess, "run", return_value=Mock(stdout="a" * 40)),
            patch.object(sync, "graphql", return_value=self.metadata) as api,
        ):
            self.assertEqual(sync.reconcile("P", "AstrBotDevs/AstrBot", apply=True), [])
            api.assert_called_once()
            self.assertTrue(api.call_args.args[0].startswith("query"))

    def test_reconciliation_explicitly_scans_closed_issues_and_merged_prs(self):
        with (
            patch.object(
                sync, "connection", side_effect=[self.fields, [], [], [], []]
            ) as read,
            patch.object(sync.subprocess, "run", return_value=Mock(stdout="a" * 40)),
        ):
            self.assertEqual(sync.reconcile("P", "AstrBotDevs/AstrBot"), [])
        self.assertEqual(read.call_args_list[2].kwargs["states"], ["OPEN", "CLOSED"])
        self.assertEqual(
            read.call_args_list[3].kwargs["states"], ["OPEN", "CLOSED", "MERGED"]
        )

    def test_invalid_field_configuration_fails_before_other_reads_or_writes(self):
        for fields in [
            self.fields[:-1],
            [{**self.fields[0], "options": []}, *self.fields[1:]],
            [*self.fields, self.fields[0]],
            [{**self.fields[0], "options": []}, *self.fields[1:]],
        ]:
            with (
                self.subTest(fields=fields),
                patch.object(sync, "connection", return_value=fields) as read,
                patch.object(sync, "graphql") as api,
            ):
                with self.assertRaises(ValueError):
                    sync.reconcile("P", "AstrBotDevs/AstrBot", apply=True)
                self.assertEqual(read.call_count, 1)
                api.assert_not_called()

    def test_late_read_failure_never_partially_applies_plan(self):
        second = {**self.issue, "id": "SECOND", "number": 2}
        with (
            patch.object(
                sync,
                "connection",
                side_effect=[
                    self.fields,
                    [],
                    [dict(self.issue), second],
                    [],
                    [],
                    [],
                    RuntimeError("read failed"),
                ],
            ),
            patch.object(sync.subprocess, "run", return_value=Mock(stdout="a" * 40)),
            patch.object(sync, "graphql", return_value=self.metadata) as api,
        ):
            with self.assertRaisesRegex(RuntimeError, "read failed"):
                sync.reconcile("P", "AstrBotDevs/AstrBot", apply=True)
            api.assert_called_once()
            self.assertTrue(api.call_args.args[0].startswith("query"))

    def test_closed_subject_is_added_using_current_state(self):
        closed = {
            **self.issue,
            "state": "CLOSED",
            "stateReason": "NOT_PLANNED",
            "labels": [],
        }
        with (
            patch.object(sync, "connection", return_value=self.fields),
            patch.object(sync, "event_snapshot", return_value=([closed], {}, {})),
            patch.object(sync.subprocess, "run", return_value=Mock(stdout="a" * 40)),
        ):
            plan = sync.reconcile("P", "AstrBotDevs/AstrBot", subject=1)
        self.assertEqual(plan[0]["changes"]["Status"], "Cancelled")

    def test_initial_connection_page_avoids_network_and_continues_pagination(self):
        initial = {"nodes": [1], "pageInfo": {"hasNextPage": True, "endCursor": "NEXT"}}
        with patch.object(
            sync, "graphql", return_value={"page": {**self.page, "nodes": [2]}}
        ) as api:
            self.assertEqual(
                sync.connection("query", ("page",), initial=initial), [1, 2]
            )
            self.assertEqual(api.call_args.args[1]["cursor"], "NEXT")
        with patch.object(sync, "graphql") as api:
            self.assertEqual(sync.connection("query", ("page",), initial=self.page), [])
            api.assert_not_called()

    def test_multiple_implementations_need_all_commits_in_release(self):
        issue = {"__typename": "Issue", "state": "OPEN", "labels": []}
        prs = [
            {"state": "MERGED", "mergeCommit": {"oid": char * 40}, "url": char}
            for char in ("a", "b")
        ]
        releases = [
            {
                "tagName": "v1",
                "publishedAt": "2026-01-01",
                "url": "r",
                "isDraft": False,
                "isPrerelease": False,
            }
        ]
        with patch.object(
            sync,
            "ancestor",
            side_effect=lambda commit, ref: ref == "c" * 40 or commit == "a" * 40,
        ):
            desired = sync.delivery(issue, {}, prs, releases, "c" * 40)
        self.assertEqual(desired["发布版本"], "")
        self.assertEqual(desired["Status"], "Needs verification")

    def test_open_implementation_prevents_released_delivery(self):
        issue = {"__typename": "Issue", "state": "OPEN", "labels": []}
        merged = {"state": "MERGED", "mergeCommit": {"oid": "a" * 40}, "url": "merged"}
        opened = {"state": "OPEN", "url": "open"}
        releases = [
            {
                "tagName": "v1",
                "publishedAt": "2026-01-01",
                "url": "r",
                "isDraft": False,
                "isPrerelease": False,
            }
        ]
        with patch.object(sync, "ancestor", return_value=True):
            desired = sync.delivery(issue, {}, [merged, opened], releases, "c" * 40)
        self.assertEqual(desired["发布版本"], "")
        self.assertEqual(desired["交付进度"], "尚未合入")

    def test_unreachable_merged_commit_is_not_reported_as_delivered(self):
        issue = {"__typename": "Issue", "state": "OPEN", "labels": []}
        pr = {"state": "MERGED", "mergeCommit": {"oid": "a" * 40}, "url": "pr"}
        with patch.object(sync, "ancestor", return_value=False):
            desired = sync.delivery(issue, {}, [pr], [], "c" * 40)
        self.assertEqual(desired["交付进度"], "尚未合入")

    def test_closed_issue_referenced_by_implementation_is_candidate(self):
        closed = {**self.issue, "state": "CLOSED", "number": 42, "id": "CLOSED"}
        pr = {
            "__typename": "PullRequest",
            "id": "PR",
            "number": 9,
            "state": "MERGED",
            "body": "Closes #42",
            "url": "pr",
            "mergeCommit": {"oid": "a" * 40},
            "closingIssuesReferences": self.page,
        }
        with (
            patch.object(
                sync,
                "connection",
                side_effect=[self.fields, [], [closed], [pr], [], [], []],
            ),
            patch.object(sync.subprocess, "run", return_value=Mock(stdout="a" * 40)),
            patch.object(sync, "ancestor", return_value=True),
        ):
            plan = sync.reconcile("P", "AstrBotDevs/AstrBot")
        self.assertEqual({entry["number"] for entry in plan}, {9, 42})

    def test_git_ancestry_errors_fail_closed(self):
        sync.ancestor.cache_clear()
        with patch.object(sync.subprocess, "run", return_value=Mock(returncode=128)):
            with self.assertRaises(RuntimeError):
                sync.ancestor("a" * 40, "refs/tags/missing")
        with self.assertRaises(ValueError):
            sync.ancestor("--bad-option", "refs/tags/v1")

    def test_missing_recovery_boundary_fails_before_mutations(self):
        for metadata in (
            {"node": None},
            {"node": {}},
            {"node": {"createdAt": "invalid"}},
        ):
            with (
                self.subTest(metadata=metadata),
                patch.object(sync, "connection", return_value=self.fields) as read,
                patch.object(sync, "graphql", return_value=metadata) as api,
            ):
                with self.assertRaisesRegex(ValueError, "creation time"):
                    sync.reconcile("P", "AstrBotDevs/AstrBot", apply=True)
                self.assertEqual(read.call_count, 1)
                api.assert_called_once()
                self.assertTrue(api.call_args.args[0].startswith("query"))

    def test_closed_recovery_includes_exact_boundary_but_excludes_older_items(self):
        for closed_at, expected in [
            ("2026-10-01T00:00:00Z", {1}),
            ("2026-09-30T23:59:59Z", set()),
        ]:
            issue = {**self.issue, "state": "CLOSED", "closedAt": closed_at}
            pages = [self.fields, [], [issue], [], []]
            if expected:
                pages.append([])
            with (
                self.subTest(closed_at=closed_at),
                patch.object(sync, "connection", side_effect=pages),
                patch.object(
                    sync.subprocess, "run", return_value=Mock(stdout="a" * 40)
                ),
            ):
                plan = sync.reconcile("P", "AstrBotDevs/AstrBot")
            self.assertEqual({entry["number"] for entry in plan}, expected)

    def test_reference_lines_ignore_incidental_and_foreign_mentions(self):
        body = (
            "Mention #9 in passing\nRefs #12, #13\nFixes: AstrBotDevs/AstrBot#14\n"
            "Closes https://github.com/AstrBotDevs/AstrBot/issues/15\n"
            "Refs other/repo#12\nRefs https://github.com/other/repo/issues/16\n"
            "```\nRefs #99\n```\n"
        )
        self.assertEqual(sync.references(body, "AstrBotDevs/AstrBot"), {12, 13, 14, 15})
        self.assertEqual(
            sync.references(
                "Fixes #12, and see #99 for context", "AstrBotDevs/AstrBot"
            ),
            {12, 99},
        )

    def test_decision_separates_acceptance_from_delivery(self):
        issue = {"__typename": "Issue", "state": "OPEN", "labels": []}
        for current, linked, expected in [
            ({}, [], "Todo"),
            ({"Status": "In progress"}, [], "In progress"),
            ({"Status": "Done"}, [], "Todo"),
            ({}, [{"state": "OPEN"}], "In progress"),
            ({}, [{"state": "MERGED"}], "Needs verification"),
            ({}, [{"state": "OPEN"}, {"state": "MERGED"}], "In progress"),
        ]:
            with self.subTest(current=current, linked=linked):
                self.assertEqual(
                    sync.decide(issue, current, linked)["Status"], expected
                )
        issue.update(state="CLOSED", stateReason="NOT_PLANNED")
        self.assertEqual(sync.decide(issue, {}, [])["Status"], "Cancelled")
        issue["stateReason"] = "COMPLETED"
        self.assertEqual(sync.decide(issue, {}, [])["Status"], "Done")

    def test_reopened_terminal_issues_reset_before_linked_pr_inference(self):
        issue = {"__typename": "Issue", "state": "OPEN", "labels": []}
        for terminal in ("Done", "Cancelled", "Closed unmerged"):
            for state in ("OPEN", "MERGED"):
                with self.subTest(terminal=terminal, state=state):
                    self.assertEqual(
                        sync.decide(issue, {"Status": terminal}, [{"state": state}])[
                            "Status"
                        ],
                        "Todo",
                    )

    def test_full_scan_recovers_closed_items_without_their_event_subject(self):
        issue = {
            **self.issue,
            "state": "CLOSED",
            "closedAt": "2026-10-02T00:00:00Z",
            "stateReason": "COMPLETED",
        }
        pr = {
            "__typename": "PullRequest",
            "id": "PR",
            "number": 2,
            "state": "CLOSED",
            "closedAt": "2026-10-02T00:00:00Z",
            "url": "pr",
        }
        with (
            patch.object(
                sync,
                "connection",
                side_effect=[self.fields, [], [dict(issue)], [pr], [], []],
            ),
            patch.object(sync.subprocess, "run", return_value=Mock(stdout="a" * 40)),
        ):
            plan = sync.reconcile("P", "AstrBotDevs/AstrBot")
        self.assertEqual({entry["number"] for entry in plan}, {1, 2})
        self.assertEqual(plan[0]["changes"]["Status"], "Done")
        self.assertEqual(plan[1]["changes"]["Status"], "Closed unmerged")

    def test_explicit_labels_and_unmerged_pr(self):
        issue = {
            "__typename": "Issue",
            "state": "OPEN",
            "labels": ["status:needs-info"],
        }
        self.assertEqual(
            sync.decide(issue, {}, [{"state": "MERGED"}])["Status"], "Todo"
        )
        issue["labels"] = ["status:needs-verification"]
        self.assertEqual(sync.decide(issue, {}, [])["Status"], "Needs verification")
        pr = {"__typename": "PullRequest", "state": "CLOSED"}
        self.assertEqual(sync.decide(pr, {}, [])["Status"], "Closed unmerged")

    def test_release_requires_mainline_and_actual_tag_ancestry(self):
        merged = {
            "__typename": "PullRequest",
            "state": "MERGED",
            "mergeCommit": {"oid": "a" * 40},
            "url": "https://github.com/a/b/pull/1",
        }
        releases = [
            {
                "tagName": "v1",
                "url": "release1",
                "publishedAt": "2026-01-01",
                "isDraft": False,
                "isPrerelease": False,
            },
            {
                "tagName": "v2",
                "url": "release2",
                "publishedAt": "2026-02-01",
                "isDraft": False,
                "isPrerelease": False,
            },
        ]
        with patch.object(sync, "ancestor", side_effect=[True, False, True]):
            desired = sync.delivery(merged, {}, [], releases, "b" * 40)
        self.assertEqual(desired["发布版本"], "v2")
        self.assertEqual(desired["发布说明"], "release2")
        self.assertEqual(desired["交付进度"], "已发布")
        with patch.object(sync, "ancestor", return_value=False) as ancestor:
            self.assertEqual(
                sync.delivery(merged, {}, [], releases, "b" * 40)["发布版本"], ""
            )
            self.assertEqual(ancestor.call_count, 1)

    def test_prerelease_and_draft_are_not_stable_delivery(self):
        merged = {
            "__typename": "PullRequest",
            "state": "MERGED",
            "mergeCommit": {"oid": "a" * 40},
            "url": "pr",
        }
        releases = [
            {
                "tagName": "v1",
                "publishedAt": "2026-01-01",
                "isDraft": draft,
                "isPrerelease": pre,
            }
            for draft, pre in [(True, False), (False, True)]
        ]
        with patch.object(sync, "ancestor", return_value=True):
            desired = sync.delivery(merged, {}, [], releases, "b" * 40)
        self.assertEqual(desired["交付进度"], "已合入待发布")
        self.assertEqual(desired["发布版本"], "")

    def test_pagination_rejects_stalled_cursor(self):
        data = {
            "page": {
                "nodes": [],
                "pageInfo": {"hasNextPage": True, "endCursor": "same"},
            }
        }
        with patch.object(sync, "graphql", return_value=data):
            with self.assertRaisesRegex(RuntimeError, "cursor"):
                sync.connection("query", ("page",))

    def test_dry_run_does_not_mutate_and_apply_skips_equal_fields(self):
        plan = [
            {
                "content": "C",
                "item": "I",
                "number": 1,
                "changes": {"发布版本": "", "Status": "Done"},
            }
        ]
        fields = {
            "发布版本": {"id": "V"},
            "Status": {"id": "S", "options": [{"name": "Done", "id": "D"}]},
        }
        with patch.object(sync, "graphql", return_value={}) as api:
            sync.apply_plan("P", fields, plan, apply=False)
            api.assert_not_called()
            sync.apply_plan("P", fields, plan, apply=True)
        self.assertEqual(api.call_count, 2)
        self.assertIn("clearProjectV2ItemFieldValue", api.call_args_list[0].args[0])
        self.assertEqual(
            api.call_args_list[1].args[1]["value"], {"singleSelectOptionId": "D"}
        )


if __name__ == "__main__":
    unittest.main()
