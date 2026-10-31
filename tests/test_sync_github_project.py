"""Network-free transport and entrypoint tests for Project synchronization."""

import importlib.util
import io
import json
import os
import re
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/sync_github_project.py"


class SyncProjectTests(unittest.TestCase):
    def test_main_reports_sync_failures_without_raw_details(self):
        failures = [
            RuntimeError("secret stalled cursor"),
            ValueError("secret invalid ref"),
            urllib.error.URLError("secret transport"),
            TimeoutError("secret timeout"),
            OSError("secret missing git"),
        ]
        for failure in failures:
            with (
                self.subTest(failure=failure),
                patch.dict(
                    os.environ,
                    {"ASTRBOT_PROJECT_ID": "P", "ASTRBOT_PROJECT_TOKEN": "secret"},
                    clear=True,
                ),
                patch.object(self.module, "reconcile", side_effect=failure),
                patch("sys.stdout", new_callable=io.StringIO) as output,
            ):
                with self.assertRaises(SystemExit) as caught:
                    self.module.main([])
                self.assertIn("Project synchronization failed", str(caught.exception))
                self.assertNotIn("secret", str(caught.exception))
                self.assertEqual(output.getvalue(), "")

    def setUp(self):
        spec = importlib.util.spec_from_file_location("sync_github_project", SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_graphql_uses_variables_and_timeout(self):
        with (
            patch.dict(os.environ, {"ASTRBOT_PROJECT_TOKEN": "secret"}),
            patch.object(
                self.module.urllib.request,
                "urlopen",
                return_value=io.StringIO('{"data": {"ok": true}}'),
            ) as urlopen,
        ):
            self.assertEqual(
                self.module.graphql("query", {"value": '"untrusted"'}), {"ok": True}
            )
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.github.com/graphql")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(
            json.loads(request.data),
            {"query": "query", "variables": {"value": '"untrusted"'}},
        )
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 30)

    def test_graphql_errors_do_not_leak_response(self):
        for body in [
            '{"errors": [{"message": "secret"}], "data": {}}',
            '{"data": null}',
            "not JSON",
            "[]",
            "null",
        ]:
            with (
                self.subTest(body=body),
                patch.dict(os.environ, {"ASTRBOT_PROJECT_TOKEN": "secret"}),
                patch.object(
                    self.module.urllib.request,
                    "urlopen",
                    return_value=io.StringIO(body),
                ),
            ):
                with self.assertRaises(RuntimeError) as error:
                    self.module.graphql("query", {})
                self.assertNotIn("secret", str(error.exception))

    def test_transport_errors_do_not_leak_credentials(self):
        for error in [urllib.error.URLError("secret"), TimeoutError("secret")]:
            with (
                self.subTest(error=error),
                patch.dict(os.environ, {"ASTRBOT_PROJECT_TOKEN": "secret"}),
                patch.object(self.module.urllib.request, "urlopen", side_effect=error),
            ):
                with self.assertRaises(RuntimeError) as caught:
                    self.module.graphql("query", {})
                self.assertNotIn("secret", str(caught.exception))

    def test_missing_project_is_disabled(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(self.module, "reconcile") as reconcile,
        ):
            self.module.main([])
        reconcile.assert_not_called()

    def test_configured_project_requires_token(self):
        with patch.dict(os.environ, {"ASTRBOT_PROJECT_ID": "P"}, clear=True):
            with self.assertRaisesRegex(ValueError, "ASTRBOT_PROJECT_TOKEN"):
                self.module.main([])

    def test_default_preview_and_explicit_apply(self):
        env = {"ASTRBOT_PROJECT_ID": "P", "ASTRBOT_PROJECT_TOKEN": "secret"}
        for args, apply in [([], False), (["--apply"], True)]:
            with (
                self.subTest(args=args),
                patch.dict(os.environ, env, clear=True),
                patch.object(self.module, "reconcile", return_value=[]) as reconcile,
            ):
                self.module.main(args)
                self.assertIs(reconcile.call_args.kwargs["apply"], apply)

    def test_status_map_and_legacy_names(self):
        env = {
            "ASTRBOT_PROJECT_ID": "P",
            "ASTRBOT_PROJECT_TOKEN": "secret",
            "ASTRBOT_PROJECT_STATUS_MAP": '{"Needs verification": "待验证"}',
            "ASTRBOT_PROJECT_STATUS_OPEN": "待安排",
            "ASTRBOT_PROJECT_STATUS_DONE": "已完成",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(self.module, "reconcile", return_value=[]) as api,
        ):
            self.module.main([])
        names = api.call_args.kwargs["status_names"]
        self.assertEqual(names["Todo"], "待安排")
        self.assertEqual(names["Done"], "已完成")
        self.assertEqual(names["Needs verification"], "待验证")

    def test_invalid_status_map_never_reconciles(self):
        for value in [
            "[]",
            '{"Typo":"x"}',
            '{"Done":"Todo"}',
            '{"Done":1}',
            '{"Done":" "}',
        ]:
            env = {
                "ASTRBOT_PROJECT_ID": "P",
                "ASTRBOT_PROJECT_TOKEN": "secret",
                "ASTRBOT_PROJECT_STATUS_MAP": value,
            }
            with (
                self.subTest(value=value),
                patch.dict(os.environ, env, clear=True),
                patch.object(self.module, "reconcile") as api,
            ):
                with self.assertRaises(ValueError):
                    self.module.main([])
                api.assert_not_called()

    def test_supported_events_and_subjects(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.json"
            env = {
                "ASTRBOT_PROJECT_ID": "P",
                "ASTRBOT_PROJECT_TOKEN": "secret",
                "GITHUB_EVENT_PATH": str(path),
                "GITHUB_REPOSITORY": "AstrBotDevs/AstrBot",
                "GITHUB_REF": "refs/heads/master",
                "ASTRBOT_DEFAULT_BRANCH": "master",
            }
            for name, action, key in [
                ("issues", "opened", "issue"),
                ("issues", "labeled", "issue"),
                ("issues", "closed", "issue"),
                ("issues", "reopened", "issue"),
                ("pull_request_target", "closed", "pull_request"),
                ("pull_request_target", "edited", "pull_request"),
                ("pull_request_target", "synchronize", "pull_request"),
                ("schedule", None, None),
                ("workflow_dispatch", None, None),
            ]:
                event = {
                    "repository": {
                        "full_name": "AstrBotDevs/AstrBot",
                        "default_branch": "master",
                    },
                    "action": action,
                }
                if name == "schedule":
                    event = {}
                if key:
                    event[key] = {"number": 42, "state": "outdated"}
                path.write_text(json.dumps(event), encoding="utf-8")
                with (
                    self.subTest(name=name, action=action),
                    patch.dict(
                        os.environ, {**env, "GITHUB_EVENT_NAME": name}, clear=True
                    ),
                    patch.object(
                        self.module, "reconcile", return_value=[]
                    ) as reconcile,
                ):
                    self.module.main([])
                    self.assertEqual(
                        reconcile.call_args.kwargs["subject"], 42 if key else None
                    )
                    self.assertFalse(reconcile.call_args.kwargs["apply"])

    def test_untrusted_context_never_reconciles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.json"
            for name, action, repo, number, ref in [
                (
                    "pull_request",
                    "opened",
                    "AstrBotDevs/AstrBot",
                    42,
                    "refs/heads/master",
                ),
                ("issues", "deleted", "AstrBotDevs/AstrBot", 42, "refs/heads/master"),
                ("issues", "opened", "attacker/fork", 42, "refs/heads/master"),
                ("issues", "opened", "AstrBotDevs/AstrBot", True, "refs/heads/master"),
                ("issues", "opened", "AstrBotDevs/AstrBot", 0, "refs/heads/master"),
                ("issues", "opened", "AstrBotDevs/AstrBot", "42", "refs/heads/master"),
                (
                    "release",
                    "published",
                    "AstrBotDevs/AstrBot",
                    42,
                    "refs/heads/master",
                ),
                ("push", None, "AstrBotDevs/AstrBot", 42, "refs/heads/master"),
                (
                    "workflow_dispatch",
                    None,
                    "AstrBotDevs/AstrBot",
                    42,
                    "refs/heads/untrusted",
                ),
                (
                    "release",
                    "published",
                    "AstrBotDevs/AstrBot",
                    42,
                    "refs/heads/master",
                ),
                ("push", None, "AstrBotDevs/AstrBot", 42, "refs/heads/master"),
            ]:
                path.write_text(
                    json.dumps(
                        {
                            "repository": {
                                "full_name": repo,
                                "default_branch": "master",
                            },
                            "action": action,
                            "issue": {"number": number},
                        }
                    ),
                    encoding="utf-8",
                )
                env = {
                    "ASTRBOT_PROJECT_ID": "P",
                    "ASTRBOT_PROJECT_TOKEN": "secret",
                    "GITHUB_EVENT_NAME": name,
                    "GITHUB_EVENT_PATH": str(path),
                    "GITHUB_REPOSITORY": "AstrBotDevs/AstrBot",
                    "GITHUB_REF": ref,
                }
                with (
                    self.subTest(name=name, action=action, number=number, ref=ref),
                    patch.dict(os.environ, env, clear=True),
                    patch.object(self.module, "reconcile") as reconcile,
                ):
                    with self.assertRaises(ValueError):
                        self.module.main([])
                    reconcile.assert_not_called()

    def test_schedule_uses_configured_default_branch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.json"
            path.write_text("{}", encoding="utf-8")
            env = {
                "ASTRBOT_PROJECT_ID": "P",
                "ASTRBOT_PROJECT_TOKEN": "secret",
                "ASTRBOT_DEFAULT_BRANCH": "development",
                "GITHUB_EVENT_NAME": "schedule",
                "GITHUB_EVENT_PATH": str(path),
                "GITHUB_REPOSITORY": "AstrBotDevs/AstrBot",
                "GITHUB_REF": "refs/heads/development",
            }
            with (
                patch.dict(os.environ, env, clear=True),
                patch.object(self.module, "reconcile", return_value=[]) as reconcile,
            ):
                self.module.main([])
            reconcile.assert_called_once()


class WorkflowSecurityTests(unittest.TestCase):
    def test_sync_job_requires_environment_before_any_steps(self):
        workflow = (
            SCRIPT.parents[1] / ".github/workflows/project-sync.yml"
        ).read_text()
        job = workflow.split("  sync:\n", 1)[1]
        self.assertIn("    environment: project-sync\n", job.split("    steps:", 1)[0])
        self.assertIn(
            "ASTRBOT_PROJECT_TOKEN: ${{ secrets.ASTRBOT_PROJECT_ENV_TOKEN }}", job
        )
        self.assertNotIn("secrets.ASTRBOT_PROJECT_TOKEN", job)

    def test_both_workflows_pin_all_actions_to_full_commit_ids(self):
        for name in ("project-sync.yml", "project-sync-tests.yml"):
            workflow = (SCRIPT.parents[1] / ".github/workflows" / name).read_text()
            actions = re.findall(r"uses:\s+([^\s#]+)", workflow)
            self.assertEqual(len(actions), 2)
            for action in actions:
                with self.subTest(workflow=name, action=action):
                    self.assertRegex(
                        action, r"^actions/(checkout|setup-python)@[0-9a-f]{40}$"
                    )


if __name__ == "__main__":
    unittest.main()
