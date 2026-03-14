import sys
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


def load_upload_module():
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "upload_doc_images_to_r2.py"
    )
    spec = spec_from_file_location("upload_doc_images_to_r2", script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module from {script_path}")
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class UploadDocImagesToR2Test(unittest.TestCase):
    def test_run_rclone_upload_uses_argument_list_without_shell(self):
        module = load_upload_module()

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            with (
                patch.object(module.shutil, "which", return_value="/usr/bin/rclone"),
                patch.object(module.subprocess, "run") as mock_run,
            ):
                module.run_rclone_upload(
                    root,
                    "r2:docs-bucket/assets",
                    ["guide/image.png"],
                    dry_run=False,
                )

        args, kwargs = mock_run.call_args
        files_from_path = args[0][5]
        self.assertEqual(
            args[0],
            [
                "rclone",
                "copy",
                str(root),
                "r2:docs-bucket/assets",
                "--files-from",
                files_from_path,
                "--create-empty-src-dirs",
            ],
        )
        self.assertTrue(kwargs["check"])
        self.assertIs(kwargs.get("shell"), False)


if __name__ == "__main__":
    unittest.main()
