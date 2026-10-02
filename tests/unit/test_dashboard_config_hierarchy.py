"""Check frontend ownership against the authoritative backend core schema."""

import ast
import json
import shutil
import subprocess
import unittest
from pathlib import Path


class ConfigHierarchyCoverageTest(unittest.TestCase):
    def test_all_backend_fields_have_exactly_one_frontend_owner(self):
        """Verify every backend record survives regrouping exactly once and unchanged."""
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for frontend configuration validation")
        root = Path(__file__).resolve().parents[2]
        source = ast.parse(
            (root / "astrbot/core/config/default.py").read_text(encoding="utf-8")
        )

        def literal(value):
            """Read literal metadata without importing the application runtime.

            Args:
                value: AST node from the backend configuration module.

            Returns:
                JSON-compatible metadata; runtime defaults use a placeholder.
            """
            if isinstance(value, ast.Constant):
                return value.value
            if isinstance(value, ast.Dict):
                return {
                    literal(key): literal(item)
                    for key, item in zip(value.keys, value.values)
                    if key is not None
                }
            if isinstance(value, (ast.List, ast.Tuple)):
                return [literal(item) for item in value.elts]
            return None

        metadata = {}
        for statement in source.body:
            if (
                isinstance(statement, ast.Assign)
                and isinstance(statement.targets[0], ast.Name)
                and statement.targets[0].id
                in {"CONFIG_METADATA_3", "CONFIG_METADATA_3_SYSTEM"}
            ):
                metadata.update(literal(statement.value))
        program = """
            import assert from 'node:assert/strict';
            import { readFileSync } from 'node:fs';
            import { buildConfigHierarchy } from './dashboard/src/utils/configHierarchy.mjs';
            const metadata = JSON.parse(readFileSync(0, 'utf8'));
            const before = structuredClone(metadata);
            const hierarchy = buildConfigHierarchy(metadata);
            assert.deepEqual(metadata, before);
            console.log(JSON.stringify(hierarchy));
        """
        result = subprocess.run(
            [node, "--input-type=module", "-e", program],
            input=json.dumps(metadata),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
            cwd=root,
        )
        hierarchy = json.loads(result.stdout)
        # Descriptions identify each source record even when runners share selectors.
        original = {}
        for section_key, section in metadata.items():
            for group_key, group in section["metadata"].items():
                for field, item in group["items"].items():
                    identity = (
                        field,
                        item.get("description"),
                        json.dumps(item.get("condition", {}), sort_keys=True),
                    )
                    original.setdefault(identity, []).append(
                        (section_key, group_key, group, item)
                    )
        self.assertTrue(original, "Backend metadata must contain configuration records")
        for section_key, section in hierarchy.items():
            for group in section["metadata"].values():
                for field, item in group["items"].items():
                    candidates = [
                        entry
                        for entries in original.values()
                        for entry in entries
                        if field in entry[2]["items"]
                        and entry[3].get("description") == item.get("description")
                    ]
                    matching = None
                    for entry in candidates:
                        expected = {
                            **entry[2].get("condition", {}),
                            **entry[3].get("condition", {}),
                        }
                        if section_key == "message_group" or field.startswith(
                            ("provider_stt_settings.", "provider_tts_settings.")
                        ):
                            expected.pop("provider_settings.enable", None)
                        if item.get("condition") == expected:
                            matching = entry
                            break
                    self.assertIsNotNone(matching, field)
                    self.assertEqual(
                        {
                            key: value
                            for key, value in item.items()
                            if key != "condition"
                        },
                        {
                            key: value
                            for key, value in matching[3].items()
                            if key != "condition"
                        },
                    )
                    original_identity = (
                        field,
                        matching[3].get("description"),
                        json.dumps(matching[3].get("condition", {}), sort_keys=True),
                    )
                    original[original_identity].remove(matching)
        self.assertFalse(any(original.values()))


if __name__ == "__main__":
    unittest.main()
