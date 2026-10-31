"""Bounded event reads and mutation failure accounting."""

import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location(
    "project_events",
    Path(__file__).resolve().parents[1] / "scripts/sync_github_project.py",
)
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


class EventTests(unittest.TestCase):
    def setUp(self):
        self.page = {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}
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
        self.issue = {
            "__typename": "Issue",
            "id": "I",
            "number": 1,
            "state": "OPEN",
            "labels": [],
            "projectItems": [],
            "timelineItems": [],
        }
        self.pr = {
            "__typename": "PullRequest",
            "id": "PR",
            "number": 2,
            "state": "OPEN",
            "body": "Refs #1",
            "url": "https://github.com/AstrBotDevs/AstrBot/pull/2",
            "projectItems": [],
            "closingIssuesReferences": [],
        }

    def test_issue_event_reads_only_subject_and_one_hop(self):
        issue = {
            **self.issue,
            "timelineItems": [
                {
                    "source": {
                        "__typename": "PullRequest",
                        "number": 2,
                        "repository": {"nameWithOwner": "AstrBotDevs/AstrBot"},
                    }
                }
            ],
        }
        with patch.object(sync, "read_subject", side_effect=[issue, self.pr]) as read:
            candidates, tracked, linked = sync.event_snapshot(
                "P", "AstrBotDevs/AstrBot", 1, {}
            )
        self.assertEqual({x["number"] for x in candidates}, {1, 2})
        self.assertEqual(linked[1], [self.pr])
        self.assertEqual(read.call_count, 2)
        self.assertEqual(tracked, {})

    def test_pr_edit_refreshes_old_and_new_issue_references(self):
        pr = {**self.pr, "body": "Refs #3"}
        third = {**self.issue, "id": "I3", "number": 3}
        event = {"changes": {"body": {"from": "Refs #1"}}}
        old_pr = {**self.pr, "id": "PR4", "number": 4, "body": "Refs #1"}
        old_issue = {
            **self.issue,
            "timelineItems": [
                {
                    "source": {
                        "__typename": "PullRequest",
                        "number": 4,
                        "repository": {"nameWithOwner": "AstrBotDevs/AstrBot"},
                    }
                }
            ],
        }
        with patch.object(
            sync, "read_subject", side_effect=[pr, old_issue, third, old_pr]
        ):
            candidates, _, linked = sync.event_snapshot(
                "P", "AstrBotDevs/AstrBot", 2, event
            )
        self.assertEqual({x["number"] for x in candidates}, {1, 2, 3, 4})
        self.assertEqual(linked[1], [old_pr])
        self.assertEqual(linked[3], [pr])

    def test_pr_edit_recovers_old_custom_ref_from_project_link_field(self):
        pr = {**self.pr, "body": "Refs #3"}
        old_pr = {**self.pr, "id": "PR4", "number": 4, "body": "Refs #1"}
        old_issue = {
            **self.issue,
            "projectItems": [
                {
                    "project": {"id": "P"},
                    "fieldValues": [
                        {
                            "field": {"name": "实现关联"},
                            "text": "https://github.com/AstrBotDevs/AstrBot/pull/4",
                        }
                    ],
                }
            ],
        }
        third = {**self.issue, "id": "I3", "number": 3}
        with patch.object(
            sync, "read_subject", side_effect=[pr, old_issue, third, old_pr]
        ):
            candidates, _, linked = sync.event_snapshot(
                "P",
                "AstrBotDevs/AstrBot",
                2,
                {"changes": {"body": {"from": "Refs #1"}}},
            )
        self.assertEqual({item["number"] for item in candidates}, {1, 2, 3, 4})
        self.assertEqual(linked[1], [old_pr])

    def test_event_path_reads_no_full_release_connection(self):
        with (
            patch.object(sync, "event_snapshot", return_value=([self.issue], {}, {})),
            patch.object(
                sync, "connection", side_effect=[self.fields, []]
            ) as connection,
            patch.object(sync.subprocess, "run", return_value=Mock(stdout="a" * 40)),
        ):
            sync.reconcile("P", "AstrBotDevs/AstrBot", subject=1)
        queries = [call.args[0] for call in connection.call_args_list]
        for forbidden in (
            "issues(first:",
            "pullRequests(first:",
            "items(first:",
            "releases(first:",
        ):
            self.assertFalse(any(forbidden in query for query in queries))
        queries = [call.args[0] for call in connection.call_args_list]
        self.assertFalse(any("issues(first:" in query for query in queries))
        self.assertFalse(any("pullRequests(first:" in query for query in queries))
        self.assertFalse(any("items(first:" in query for query in queries))

    def test_subject_reads_never_scan_repository_or_project_connections(self):
        node = {**self.issue, "issueState": "OPEN"}
        with (
            patch.object(
                sync,
                "graphql",
                return_value={"repository": {"issueOrPullRequest": node}},
            ) as api,
            patch.object(sync, "connection", return_value=[]),
        ):
            sync.read_subject("AstrBotDevs/AstrBot", 1)
        query = api.call_args.args[0]
        for forbidden in (
            "issues(first:",
            "pullRequests(first:",
            "items(first:",
            "releases(first:",
        ):
            self.assertNotIn(forbidden, query)
        self.assertIn("issueOrPullRequest(number:", query)

    def test_apply_failure_reports_confirmed_unknown_and_unattempted(self):
        plan = [
            {
                "content": "C",
                "item": "I",
                "number": 1,
                "changes": {"发布版本": "v1", "发布说明": "r", "实现关联": "pr"},
            }
        ]
        fields = {name: {"id": name} for name in plan[0]["changes"]}
        with (
            patch.object(sync, "graphql", side_effect=[{}, RuntimeError("secret")]),
            patch("sys.stdout", new_callable=io.StringIO) as output,
        ):
            with self.assertRaises(RuntimeError):
                sync.apply_plan("P", fields, plan, apply=True)
        messages = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(messages[0]["plan"], plan)
        self.assertEqual(messages[-1]["confirmed"], 1)
        self.assertEqual(messages[-1]["unknown"], 1)
        self.assertEqual(messages[-1]["unattempted"], 1)
        self.assertEqual(messages[-1]["field"], "发布说明")
        self.assertNotIn("secret", output.getvalue())


if __name__ == "__main__":
    unittest.main()
